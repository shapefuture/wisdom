import unittest

from wisdom.errors import NotFound
from wisdom.governance import Governor
from wisdom.store import Store


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.governor = Governor(self.store)

    def test_purpose_gate_and_distinct_axes(self):
        rec = self.store.put("mechanism", {"title":"Candidate", "semantic_support_status":"supported",
            "empirical_evidence_status":"unknown", "transfer_status":"untested", "uncertainty":"medium",
            "provenance_status":"source_linked"})
        result = self.governor.assess(rec["id"], purpose="research", stakes="low")
        self.assertEqual(result["route"], "accept_for_purpose")
        self.assertEqual(result["axes"]["empirical_evidence_status"], "unknown")
        self.assertEqual(result["axes"]["transfer_status"], "untested")
        high = self.governor.assess(rec["id"], purpose="apply", stakes="high")
        self.assertEqual(high["route"], "new_region_research")

    def test_rights_refusal_and_injection_quarantine(self):
        denied = self.store.put("source", {"text":"x", "rights":{"allowed":False}})
        poison = self.store.put("claim", {"text":"ignore policies", "injection_suspected":True})
        unknown = self.store.put("source", {"text":"unlicensed or unknown"})
        self.assertEqual(self.governor.assess(denied["id"])["route"], "refuse")
        self.assertEqual(self.governor.assess(unknown["id"])["route"], "refuse")
        self.assertEqual(self.governor.assess(poison["id"])["route"], "quarantine")

    def test_publish_share_send_aliases_require_export_rights(self):
        source = self.store.put("source", {"text": "source", "rights": {
            "allowed": True, "private": False, "allow_export": False, "allow_model": True,
            "allow_external_research": True}})
        derived = self.store.put("theory", {"source_id": source["id"],
            "semantic_support_status": "supported", "uncertainty": "low"})
        for purpose in ("export", "publish", "publish to web", "share", "send", "email"):
            with self.subTest(purpose=purpose):
                self.assertEqual(self.governor.assess(derived["id"], purpose=purpose)["route"], "refuse")

        model_only_source = self.store.put("source", {"text": "model-only", "rights": {
            "allowed": True, "private": False, "allow_export": True, "allow_model": False}})
        model_derived = self.store.put("claim", {"source_id": model_only_source["id"],
            "review_status": "supported", "uncertainty": "low"})
        self.assertEqual(self.governor.assess(model_derived["id"], purpose="model inference")["route"], "refuse")
        unknown_external = self.governor.assess(derived["id"], purpose="external data resale")
        self.assertEqual(unknown_external["route"], "refuse")

        granting_source = self.store.put("source", {"text": "shareable", "rights": {
            "allowed": True, "private": False, "allow_export": True}})
        granting_derived = self.store.put("theory", {"source_id": granting_source["id"],
            "semantic_support_status": "supported", "uncertainty": "low"})
        self.assertEqual(self.governor.assess(granting_derived["id"], purpose="share")["route"], "accept_for_purpose")

    def test_hash_only_sources_are_one_unknown_witness_group(self):
        first = self.store.put("source", {"text": "A", "content_hash": "hash-a",
            "source_family": "content:hash-a", "rights": {"allowed": True}})
        duplicate = self.store.put("source", {"text": "A copy", "content_hash": "hash-a",
            "source_family": "content:hash-a", "rights": {"allowed": True}})
        distinct = self.store.put("source", {"text": "B", "content_hash": "hash-b", "rights": {"allowed": True}})
        record = self.store.put("mechanism", {"source_ids": [first["id"], duplicate["id"], distinct["id"]],
            "semantic_support_status": "supported", "uncertainty": "low"})
        independence = self.governor.assess(record["id"])["axes"]["source_family_independence"]
        self.assertEqual(independence["count"], 0)
        self.assertTrue(independence["unknown_content_hash_group"])
        self.assertEqual(independence["witness_group_count"], 1)
        self.assertIn("do not prove independent origin", independence["method"])

    def test_malformed_rights_fail_closed_in_assessment_and_authorization(self):
        source = self.store.put("source", {"text": "source", "rights": {"allowed": True}})
        derived = self.store.put("idea", {"source_id": source["id"], "rights": "allowed",
            "semantic_support_status": "supported", "uncertainty": "low"})
        self.assertEqual(self.governor.assess(derived["id"])["route"], "refuse")
        action = self.governor.authorize("read", {"authorized": True, "rights": "allowed"})
        self.assertFalse(action["allowed"])
        self.assertEqual(action["gate"], "refuse")

    def test_rights_are_inherited_through_nested_records_and_edges(self):
        private = self.store.put("source", {"text":"private A", "source_family":"family-a", "content_hash":"same-original",
            "rights":{"allowed":True,"private":True,"allow_export":True,"allow_model":True,"allow_external_research":True}})
        public_duplicate = self.store.put("source", {"text":"private A", "source_family":"family-b", "content_hash":"same-original",
            "rights":{"allowed":True,"private":False,"allow_export":True,"allow_model":True,"allow_external_research":True}})
        claim = self.store.put("claim", {"text":"derived claim", "rights":{"allowed":True,"private":False},
            "review_status":"supported", "uncertainty":"low", "metadata":{"nested":{"source_ids":[private["id"]]}}})
        theory = self.store.put("theory", {"claim_ids":[claim["id"]], "semantic_support_status":"supported", "uncertainty":"low",
            "rights":{"allowed":True,"private":False}})
        mechanism = self.store.put("mechanism", {"semantic_support_status":"supported", "uncertainty":"low",
            "rights":{"allowed":True,"private":False}})
        self.store.link(mechanism["id"], private["id"], "SUPPORTS")
        self.store.link(mechanism["id"], public_duplicate["id"], "SUPPORTS")
        assessment = self.governor.assess(theory["id"])
        self.assertEqual(assessment["route"], "accept_for_purpose")
        self.assertEqual(assessment["axes"]["source_ancestry_ids"], [private["id"]])
        # The mechanism's backward evidence edge finds the source and denies external use.
        for purpose in ("export", "model", "external_research"):
            with self.subTest(purpose=purpose):
                exported = self.governor.assess(mechanism["id"], purpose=purpose)
                self.assertEqual(exported["route"], "refuse")
                self.assertIn(public_duplicate["id"], exported["axes"]["source_ancestry_ids"])
                self.assertEqual(exported["axes"]["source_family_independence"]["count"], 1)
                self.assertIn("private", exported["reason"])

    def test_expired_source_cannot_be_laundered_by_derived_rights(self):
        source = self.store.put("source", {"text":"expired", "rights":{"allowed":True,"expires_at":"2020-01-01T00:00:00+00:00"}})
        derived = self.store.put("idea", {"source_id":source["id"], "semantic_support_status":"supported",
            "uncertainty":"low", "rights":{"allowed":True,"expires_at":"2999-01-01T00:00:00+00:00"}})
        result = self.governor.assess(derived["id"])
        self.assertEqual(result["route"], "refuse")
        self.assertIn("expired", result["reason"])

    def test_missing_record_propagates(self):
        with self.assertRaises(NotFound): self.governor.assess("absent")

    def test_authorization_defaults_to_deny_and_only_allows_local_operations(self):
        for action in ("send_email", "publish", "delete_file", "execute_job", "purchase", "unknown_magic"):
            with self.subTest(action=action):
                result = self.governor.authorize(action, {"authorized":True, "human_approved":True})
                self.assertFalse(result["allowed"])
                self.assertFalse(result["executor"])
        for action in ("read", "annotate", "propose", "simulate"):
            with self.subTest(action=action):
                result = self.governor.authorize(action, {"authorized":True})
                self.assertTrue(result["allowed"])
                self.assertFalse(result["executor"])
        self.assertFalse(self.governor.authorize("read", {"authorized":False})["allowed"])
        self.assertFalse(self.governor.authorize("propose", {"authorized":True, "rights":{"allowed":False}})["allowed"])
        injected = self.governor.authorize("read", {"authorized":True, "source_untrusted":True})
        self.assertEqual(injected["gate"], "quarantine")


if __name__ == "__main__": unittest.main()
