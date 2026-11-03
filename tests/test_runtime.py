import json
import os
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from wisdom.composition import Application,ConsentProvider
from wisdom.store import Store
from wisdom.errors import Conflict,PermissionDenied,ValidationError
from wisdom.memory import MemoryService
from wisdom.retrieval import RetrievalService
from wisdom.workflows import WorkflowService
from wisdom.exports import export_bundle
from wisdom.providers import JSONProvider
from wisdom.ports import StorePort

def source(store,text="Feedback may help, but only with a comparator.",**rights):
    return store.put("source",{"title":"Research source","text":text,"original_text":text,"source_family":"family-1","status":"CAPTURED",
                      "rights":{"allowed":True,"private":False,"allow_export":True,"allow_model":False,**rights}},immutable=True)

class RuntimeTests(unittest.TestCase):
    def setUp(self):self.store=Store()
    def tearDown(self):self.store.close()

    def test_context_rights_propagate_through_nested_mechanism_refs(self):
        secret=source(self.store,allow_export=False,private=True)
        mechanism=self.store.put("mechanism",{"title":"Private feedback mechanism","claim_ids":[],"source_id":secret["id"]})
        idea=self.store.put("idea",{"title":"Private feedback design","source_mechanism_ids":[mechanism["id"]]})
        visible=RetrievalService(self.store).search("feedback","fusion")
        self.assertIn(idea["id"],[r["id"] for r in visible])
        hidden=RetrievalService(self.store).compile({"question":"feedback","include_private":False})
        self.assertFalse(hidden["source_evidence"])
        exported=export_bundle(self.store)
        self.assertFalse(any(r["id"]==idea["id"] for r in exported["records"]))

    def test_context_versions_change_after_human_correction(self):
        s=source(self.store)
        claim=self.store.put("claim",{"source_id":s["id"],"text":"Feedback may help.","review_status":"unreviewed"})
        search=RetrievalService(self.store)
        first=search.compile({"question":"feedback","budget":1500})
        self.store.put("claim",{**claim["data"],"review_status":"disputed"},record_id=claim["id"],expected_version=1)
        second=search.compile({"question":"feedback","budget":1500})
        self.assertNotEqual(first["packet_version"],second["packet_version"])
        self.assertEqual(first["permitted_tools"],[])

    def test_historical_context_uses_prior_text_without_future_revisions(self):
        s=source(self.store,text='Original source without the query term.')
        claim=self.store.put('claim',{'source_id':s['id'],'text':'quasar hypothesis before decision'})
        cutoff=datetime.now(timezone.utc).isoformat()
        self.store.put('claim',{'source_id':s['id'],'text':'later revision erased the word'},record_id=claim['id'],expected_version=1)
        packet=RetrievalService(self.store).compile({'question':'quasar','as_of':cutoff,'budget':2000})
        old=[r for r in packet['source_evidence'] if r['id']==claim['id']]
        self.assertTrue(old)
        self.assertEqual(old[0]['version'],1)
        self.assertIn('quasar',old[0]['text'])
        self.assertLessEqual(packet['budget']['estimated_tokens'],2000)

    def test_negative_evidence_is_reopened_even_without_query_terms(self):
        s=source(self.store)
        support=self.store.put('theory',{'title':'quasar theory','claim_ids':[],'source_id':s['id']})
        contrary=self.store.put('claim',{'source_id':s['id'],'text':'A bounded counterexample observed elsewhere.'})
        self.store.link(support['id'],contrary['id'],'CONTRADICTS',polarity='negative')
        packet=RetrievalService(self.store).compile({'question':'quasar','budget':2000})
        self.assertIn(contrary['id'],[r['id'] for r in packet['negative_cases']])

    def test_legacy_private_analysis_plan_remains_restricted_and_purgeable(self):
        s=source(self.store,private=True,allow_export=False)
        plan=self.store.put('assessment',{'analysis_kind':'evidence_analysis_plan','analysis_key':'evidence-analysis:'+s['id']+':v1','proposals':{'private':'secret fragment'}},immutable=True)
        self.assertEqual(export_bundle(self.store)['records'],[])
        self.store.purge_source(s['id'],'test')
        self.assertFalse(self.store.search('secret'))

    def test_trigger_budget_dedup_and_expiry(self):
        memory=MemoryService(self.store)
        trigger=memory.trigger({"title":"Revisit feedback","conditions":[{"signal":"loss","operator":"gte","value":2}],
                   "expires_at":(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
        self.assertEqual(memory.evaluate({"loss":3},0)["notifications"],[])
        self.assertEqual(len(memory.evaluate({"loss":3},1)["notifications"]),1)
        self.assertEqual(memory.evaluate({"loss":3},1)["notifications"],[])
        current=self.store.get(trigger["id"])
        self.store.put("trigger",{**current["data"],"expires_at":"2000-01-01T00:00:00Z"},record_id=trigger["id"],expected_version=current["version"])
        self.assertFalse(memory.evaluate({"loss":4},1)["notifications"])
        self.assertEqual(self.store.get(trigger["id"])["data"]["status"],"expired")

    def test_goals_require_explicit_human_authority(self):
        memory=MemoryService(self.store)
        with self.assertRaises(PermissionDenied):memory.goal({"title":"Maximize engagement"})
        goal=memory.goal({"title":"Understand clearly","human_approved":True})
        self.assertEqual(goal["data"]["epistemic_type"],"NORMATIVE_POSITION")
        with self.assertRaises(ValidationError):memory.trace({"stage":"diagnose_personality","reflection":"bad"})

    def test_workflow_failed_retry_limit_and_exact_idempotency(self):
        flows=WorkflowService(self.store)
        calls=[]
        def operation(payload):
            calls.append(payload["idempotency_key"])
            if len(calls)==1:raise OSError("unavailable")
            return {"completed":True}
        flows.bind("local",operation)
        job=flows.run("local",{"input":"x"},key="job-1")
        self.assertEqual(job["data"]["status"],"failed")
        finished=flows.retry(job["id"])
        self.assertEqual(finished["data"]["status"],"completed")
        self.assertEqual(calls[0],calls[1])
        replay=flows.run("local",{"input":"x"},key="job-1")
        self.assertEqual(replay["id"],job["id"])
        self.assertEqual(len(calls),2)
        with self.assertRaises(Conflict):flows.run("local",{"input":"y"},key="job-1")
        with self.assertRaises(Conflict):flows.retry(job["id"])

    def test_running_live_worker_not_mistaken_for_crash(self):
        job=self.store.put("job",{"status":"running","worker_pid":os.getpid()})
        self.assertEqual(WorkflowService(self.store).recover(),[])
        self.assertEqual(self.store.get(job["id"])["data"]["status"],"running")
        orphan=self.store.put("job",{"status":"running","worker_pid":2147483647})
        recovered=WorkflowService(self.store).recover()
        self.assertEqual(recovered[0]["id"],orphan["id"])

    def test_provider_transport_bounds_and_source_consent(self):
        with self.assertRaises(ValidationError):JSONProvider("http://example.invalid","model","secret")
        class Fake:
            name="fake"
            def __init__(self):self.calls=[]
            def complete(self,op,payload):self.calls.append(payload);return {}
        f=Fake();p=ConsentProvider(self.store,f)
        s=source(self.store,private=True)
        with self.assertRaises(PermissionDenied):p.complete("evidence.propose",{"source_id":s["id"]})
        self.assertEqual(f.calls,[])

    def test_access_honors_derived_vetoes_orphans_and_quarantine(self):
        from wisdom.access import allowed
        s=source(self.store,allow_model=True)
        derived=self.store.put('claim',{'source_id':s['id'],'rights':{'allow_model':False,'allow_export':False}})
        self.assertFalse(allowed(self.store,derived,purpose='model'))
        self.assertFalse(allowed(self.store,derived,purpose='export'))
        orphan=self.store.put('claim',{'source_id':'missing-source'})
        self.assertFalse(allowed(self.store,orphan))
        a=self.store.put('idea',{'rights':{'allowed':True}})
        b=self.store.put('idea',{'source_ids':[a['id']]})
        self.store.link(a['id'],b['id'],'DERIVED_FROM')
        self.assertFalse(allowed(self.store,a))
        private=source(self.store,private=True,allow_external_research=True)
        self.assertFalse(allowed(self.store,private,purpose='external-research'))
        for fields in [{'poisoned':True},{'security_status':'quarantined'},{'status':'expired'}]:
            bad=self.store.put('source',{'rights':{'allowed':True,'allow_model':True},**fields})
            self.assertFalse(allowed(self.store,bad,purpose='model'))

    def test_governor_and_serving_share_cycle_rejection(self):
        from wisdom.governance import Governor
        from wisdom.access import allowed
        fields={'rights':{'allowed':True,'allow_external_research':True},'semantic_support_status':'supported',
                'uncertainty':'low','empirical_evidence_status':'tested','transfer_status':'bounded'}
        a=self.store.put('theory',fields)
        b=self.store.put('theory',{**fields,'source_ids':[a['id']]})
        a=self.store.put('theory',{**fields,'source_ids':[b['id']]},record_id=a['id'],expected_version=1)
        self.assertFalse(allowed(self.store,a,purpose='external_research'))
        assessment=Governor(self.store).assess(a['id'],purpose='external_research')
        self.assertNotEqual(assessment['route'],'accept_for_purpose',assessment)

    def test_typed_provider_rejects_raw_or_mismatched_source_data(self):
        class Sink:
            name='sink'
            def __init__(self):self.calls=[]
            def complete(self,op,payload):self.calls.append(payload);return {'claims':[],'arguments':[],'interpretations':[]}
        sink=Sink();guard=ConsentProvider(self.store,sink)
        with self.assertRaises(PermissionDenied):guard.complete('test.op',{'raw_text':'private'})
        src=Application(store=self.store).ingest.ingest({'title':'Approved fixture','text':'Permitted exact source.',
               'rights':{'allowed':True,'private':False,'license':'fixture','allow_export':True,'allow_model':True}})
        span=self.store.list('span')[-1]
        with self.assertRaises(PermissionDenied):
            guard.complete('evidence.propose',{'source_id':src['id'],'spans':[{'id':span['id'],'text':'private replacement'}]})
        self.assertEqual(sink.calls,[])
        guard.complete('evidence.propose',{'source_id':src['id'],'source_title':'injected title','spans':[{'id':span['id'],'text':span['data']['text']}],'raw_text':'must not pass through'})
        self.assertEqual(sink.calls[0]['source_title'],'Approved fixture')
        self.assertNotIn('raw_text',sink.calls[0])

    def test_configured_provider_path_requires_both_source_and_problem_opt_in(self):
        class Model:
            name='contract-model'
            def __init__(self):self.calls=[]
            def complete(self,op,payload):
                self.calls.append((op,payload))
                if op=='evidence.propose':
                    span=payload['spans'][0]
                    return {'claims':[{'text':span['text'],'quote':span['text'],'span_ids':[span['id']],
                                      'qualifiers':['may'],'speaker':'Unverified person'}],'arguments':[],'interpretations':[]}
                if op=='invention.diagnose':return {'diagnostic_hypotheses':[]}
                if op=='invention.forge':return {'ideas':[]}
                return {}
        model=Model();app=Application(store=self.store,provider=model)
        src=app.ingest.ingest({'title':'Model fixture','text':'Feedback may stabilize a process.',
            'rights':{'allowed':True,'license':'fixture','private':True,'allow_export':False,'allow_model':True}})
        analyzed=app.evidence.analyze(src['id']);claim=analyzed['claims'][0]
        self.assertTrue(claim['data']['speaker_uncertain'])
        self.assertIsNone(claim['data']['speaker'])
        theory=app.theory.build({'title':'Scoped feedback reading','claim_ids':[claim['id']],
            'scope':['measured feedback'],'allow_model':True})
        app.theory.mechanism({'title':'Feedback stabilization','theory_id':theory['id'],'claim_ids':[claim['id']],
            'intervention':'separate feedback cadences','boundary_conditions':['measured feedback'],
            'functional_signature':['feedback','stabilize'],'structural_signature':['process','cadence'],'allow_model':True})
        before=len(model.calls)
        local=app.invention.problem({'title':'Local private problem','description':'feedback process','allow_model':False})
        app.invention.forge(local['id'])
        self.assertEqual(len(model.calls),before)
        approved=app.invention.problem({'title':'Opted-in problem','description':'feedback process','allow_model':True})
        app.invention.forge(approved['id'])
        self.assertEqual({x[0] for x in model.calls},{'evidence.propose','theory.build','theory.mechanism','invention.diagnose','invention.forge'})
        self.assertTrue(self.store.verify_ledger()['valid'])

    def test_store_slot_can_be_rebound_without_consumer_changes(self):
        class Alternative:
            def __init__(self,inner):self.inner=inner
            def __getattr__(self,key):return getattr(self.inner,key)
        alt=Alternative(self.store)
        app=Application(store=alt)
        result=app.ingest.ingest({"title":"Swap contract","text":"Independent component slot.","rights":{
            "allowed":True,"license":"user-provided","private":False,"allow_export":True}})
        self.assertEqual(app.store.get(result["id"])["kind"],"source")
        self.assertTrue(app.store.verify_ledger()["valid"])
        # Underlying connection belongs to setUp, so avoid closing it twice.

if __name__=="__main__":unittest.main()

