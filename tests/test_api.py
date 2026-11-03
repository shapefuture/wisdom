import json
import threading
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from wisdom.api import FoundryServer
from wisdom.composition import Application

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.app=Application()
        self.server=FoundryServer(("127.0.0.1",0),self.app)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base="http://127.0.0.1:"+str(self.server.server_address[1])
        self.token=self.request("GET","/api/session")[1]["csrf_token"]
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.app.close()
    def request(self,method,path,payload=None,headers=None):
        h={"Content-Type":"application/json","X-CSRF-Token":getattr(self,"token",""),**(headers or {})}
        data=json.dumps(payload).encode() if payload is not None else None
        req=Request(self.base+path,data=data,method=method,headers=h)
        try:
            with urlopen(req,timeout=5) as response:
                raw=response.read();ct=response.headers.get("Content-Type","")
                return response.status,json.loads(raw) if "application/json" in ct else raw.decode()
        except HTTPError as e:
            return e.code,json.loads(e.read())
    def post(self,path,payload):
        code,result=self.request("POST",path,payload)
        self.assertEqual(code,200,(path,result))
        return result

    def test_http_source_to_learning_workflow_and_export(self):
        source=self.post("/api/sources",{"title":"Synthetic timing fixture","uri":"https://example.invalid/fixture",
          "text":"Feedback may stabilize a process when measured at different cadences. It does not always work.",
          "format":"text","source_family":"synthetic-1","rights":{"allowed":True,"license":"test-fixture","private":False,"allow_export":True}})
        sid=source["id"]
        analysis=self.post(f"/api/sources/{sid}/analyze",{})
        claims=[r["id"] for r in analysis["claims"]]
        self.assertTrue(claims)
        self.post(f"/api/claims/{claims[0]}/review",{"status":"accepted","reviewer":"test-human","note":"Exact qualification preserved."})
        theory=self.post("/api/theories",{"title":"Conditional feedback cadence","claim_ids":claims,"scope":["measured feedback loops"],
              "explanation":"A provisional reading of the fixture.","counterexamples":["urgent harm"],"predictions":["fewer oscillations"]})
        mechanism=self.post("/api/mechanisms",{"title":"Separate feedback cadences","theory_id":theory["id"],"claim_ids":claims,
             "problem_state":"feedback oscillation","intervention":"separate fast and slow feedback","effects":["test stability"],
             "boundary_conditions":["measured feedback"],"contraindications":["urgent harm"],"functional_signature":["feedback","stabilize"],
             "structural_signature":["cadences","process"],"source_domain":"control systems"})
        problem=self.post("/api/problems",{"title":"Feedback oscillation","description":"A process oscillates under feedback",
              "desired_state":"stabilize process","maintaining_force":"one feedback cadence","domain":"organizations",
              "actors":["team"],"constraints":["human values"],"failed_attempts":["same cadence"],"stakes":"low","stuck_type":"contradiction"})
        forged=self.post(f"/api/problems/{problem['id']}/forge",{"idempotency_key":"forge-e2e"})
        self.assertIn("diagnosis",forged)
        for idea in forged["ideas"]:
            self.assertEqual(idea["data"]["epistemic_type"],"TRANSFER_HYPOTHESIS")
        decision=self.post("/api/decisions",{"question":"Test cadences?","owner":"human","options":["small test","wait"],
              "values":["learning"],"constraints":[],"assumptions":[],"evidence_ids":[theory["id"]],
              "stop_search_when":"A reversible test is ready","stakes":"low"})
        choice=self.post(f"/api/decisions/{decision['id']}/approve",{"choice":"small test","approved_by":"human","reason":"Learn cheaply"})
        self.assertEqual(choice["data"]["approval"]["choice"],"small test")
        prediction=self.post("/api/predictions",{"statement":"Lower variation","metric":"variation","expected":"lower",
              "direction":"negative","horizon":"one week","analysis_plan":"compare with baseline","stop_conditions":["harm"]})
        before=self.app.store.get(prediction["id"])
        self.post("/api/outcomes",{"prediction_id":prediction["id"],"observed":"lower in one fixture",
                                "method":"synthetic test","limitations":["no real participants"]})
        learning=self.post("/api/learning/"+prediction["id"],{})
        self.assertIn("not",learning["data"]["causal_assessment"])
        self.assertEqual(before,self.app.store.get(prediction["id"]))
        packet=self.post("/api/context",{"question":"feedback cadence","budget":2000})
        self.assertTrue(packet["source_evidence"])
        self.assertEqual(packet["permitted_tools"],[])
        status,audit=self.request("GET","/api/audit")
        self.assertEqual(status,200);self.assertEqual(audit["critical_count"],0,audit)
        status,export=self.request("GET","/api/export")
        self.assertEqual(status,200);self.assertTrue(export["records"])
        status,lineage=self.request("GET","/api/lineage/"+theory["id"])
        self.assertEqual(status,200)
        self.assertIn(sid,[r["id"] for r in lineage["nodes"]])

    def test_csrf_origin_host_static_and_payload_boundaries(self):
        status,_=self.request("POST","/api/goals",{"title":"x","human_approved":True},{"X-CSRF-Token":""})
        self.assertEqual(status,403)
        status,_=self.request("GET","/api/session",headers={"Origin":"https://attacker.invalid"})
        self.assertEqual(status,403)
        status,_=self.request("GET","/api/session",headers={"Host":"attacker.invalid"})
        self.assertEqual(status,403)
        status,_=self.request("POST","/api/goals",{},{"Content-Type":"text/plain"})
        self.assertEqual(status,400)
        status,html=self.request("GET","/")
        self.assertEqual(status,200);self.assertIn("Wisdom Foundry",html)
        status,_=self.request("GET","/../.delivery/mission.json")
        self.assertEqual(status,404)
        status,_=self.request("POST","/api/records",{"kind":"prediction","data":{}})
        self.assertEqual(status,404)

    def test_export_and_purge_do_not_leak_source_derived_records(self):
        src=self.post("/api/sources",{"title":"private","text":"Private secret fixture.","rights":{
            "allowed":True,"license":"user-provided","private":True,"allow_export":False}})
        analysis=self.post(f"/api/sources/{src['id']}/analyze",{})
        _,bundle=self.request("GET","/api/export")
        self.assertEqual(bundle["records"],[])
        status,_=self.request("POST",f"/api/sources/{src['id']}/delete",{"confirm":False})
        self.assertEqual(status,403)
        deleted=self.post(f"/api/sources/{src['id']}/delete",{"confirm":True,"reason":"test deletion"})
        self.assertGreater(deleted["deleted_count"],1)
        status,_=self.request("GET","/api/records/"+src["id"])
        self.assertEqual(status,404)
        self.assertFalse(self.app.store.search("secret"))

if __name__=="__main__":unittest.main()

