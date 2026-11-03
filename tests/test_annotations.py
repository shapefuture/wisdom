import unittest
from wisdom.composition import Application
from wisdom.errors import ValidationError

class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.app=Application()
        self.src=self.app.ingest.ingest({"title":"Synthetic dialogue","text":"Ada: It may help. Bo: It may not help.",
                 "rights":{"allowed":True,"license":"test-fixture","private":False,"allow_export":True}})
        self.spans=self.app.ingest.spans(self.src["id"])
    def tearDown(self):self.app.close()
    def test_human_dialogue_annotations_anchor_exact_spans(self):
        payload={"kind":"utterance","reviewer":"human","idempotency_key":"turn-1","data":{
            "source_id":self.src["id"],"span_ids":[self.spans[0]["id"]],"turn":0,"speaker":"Ada","speech_act":"assertion"}}
        first=self.app.annotations.record(payload)
        self.assertEqual(first["data"]["text"],self.spans[0]["data"]["text"])
        self.assertTrue(first["data"]["speaker_uncertain"])
        self.app.annotations.record(payload)
        self.assertEqual(len(self.app.store.list("utterance")),1)
    def test_contradiction_preserves_dissent_and_negative_polarity(self):
        analysis=self.app.evidence.analyze(self.src["id"])
        ids=[r["id"] for r in analysis["claims"]]
        result=self.app.annotations.record({"kind":"contradiction","reviewer":"human","data":{
            "claim_ids":ids[:2],"conflict_type":"empirical","reason":"Competing target effects require a comparator."}})
        self.assertEqual(result["data"]["resolution"],"unresolved")
        self.assertTrue(any(e["relation"]=="CONTRADICTS" and e["polarity"]=="negative" for e in self.app.store.edges()))
    def test_unknown_speech_act_and_foreign_anchor_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.app.annotations.record({"kind":"utterance","reviewer":"human","data":{
              "source_id":self.src["id"],"span_ids":[self.spans[0]["id"]],"turn":0,"speech_act":"diagnose_personality"}})

if __name__=="__main__":unittest.main()

