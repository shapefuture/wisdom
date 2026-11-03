from __future__ import annotations

from copy import deepcopy
import hashlib
import unittest

from wisdom.evidence import EvidenceService
from wisdom.ingest import IngestService
from wisdom.errors import Conflict, ValidationError


class MemoryStore:
    """Small StorePort test double; no production storage assumptions."""
    def __init__(self):
        self.records = {}
        self.links = []
        self.keys = {}
        self.next_id = 0

    def put(self, kind, data, *, record_id=None, expected_version=None, immutable=False,
            idempotency_key=None, principal="local-user", event_type=None):
        data = deepcopy(data)
        if idempotency_key and idempotency_key in self.keys:
            old_kind, old_data, old_id = self.keys[idempotency_key]
            if (old_kind, old_data) != (kind, data):
                raise Conflict("idempotency key reused")
            return deepcopy(self.records[old_id]["record"])
        if record_id is None:
            self.next_id += 1
            record_id = f"{kind}-{self.next_id}"
        prior = self.records.get(record_id)
        if prior:
            if prior["immutable"]:
                raise Conflict("immutable")
            if expected_version != prior["record"]["version"]:
                raise Conflict("version changed")
            version = expected_version + 1
            created = prior["record"]["created_at"]
        else:
            version, created = 1, "2026-11-03T00:00:00+00:00"
        envelope = {"id": record_id, "kind": kind, "version": version,
                    "created_at": created, "updated_at": created, "data": data}
        self.records[record_id] = {"record": envelope, "immutable": immutable}
        if idempotency_key:
            self.keys[idempotency_key] = (kind, deepcopy(data), record_id)
        return deepcopy(envelope)

    def get(self, record_id, version=None):
        if record_id not in self.records:
            raise KeyError(record_id)
        return deepcopy(self.records[record_id]["record"])

    def list(self, kind=None):
        rows = [v["record"] for v in self.records.values() if kind is None or v["record"]["kind"] == kind]
        return deepcopy(rows)

    def history(self, record_id):
        return [self.get(record_id)]

    def link(self, source_id, target_id, relation, *, polarity="neutral", data=None):
        row = {"id": f"link-{len(self.links)+1}", "source_id": source_id,
               "target_id": target_id, "relation": relation, "polarity": polarity,
               "data": deepcopy(data or {})}
        self.links.append(row)
        return deepcopy(row)

    def edges(self, record_id=None):
        return deepcopy([e for e in self.links if record_id is None or record_id in {e["source_id"], e["target_id"]}])

    def search(self, query, kinds=None, limit=20):
        return []

    def append_event(self, kind, subject_id, payload, *, principal="local-user", idempotency_key=None):
        return {}

    def events(self):
        return []

    def verify_ledger(self):
        return {"valid": True}

    def purge_source(self, source_id, reason, *, principal="local-user"):
        return {}

    def close(self):
        pass


def source_payload(text, fmt="text", key="src1", rights=None):
    return {"title": "Test source", "uri": "https://example.invalid/item", "text": text,
            "format": fmt, "source_family": "family-a", "author": "Speaker",
            "rights": rights or {"allowed": True, "license": "user-provided", "private": False,
                                 "allow_export": True, "allow_model": False}, "idempotency_key": key}


class Provider:
    name = "test provider"
    def __init__(self, response):
        self.response = response
        self.calls = 0
    def complete(self, operation, payload):
        self.calls += 1
        return deepcopy(self.response)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.ingest = IngestService(self.store)

    def test_text_ingest_uses_codepoint_offsets_and_is_idempotent(self):
        text = "Café may help.\nNo result is guaranteed!"
        source = self.ingest.ingest(source_payload(text))
        again = self.ingest.ingest(source_payload(text))
        self.assertEqual(source["id"], again["id"])
        spans = self.ingest.spans(source["id"])
        self.assertEqual([s["data"]["text"] for s in spans], ["Café may help.", "No result is guaranteed!"])
        for span in spans:
            self.assertEqual(text[span["data"]["start_char"]:span["data"]["end_char"]], span["data"]["text"])
        self.assertEqual(self.ingest.coverage(source["id"])["status"], "CAPTURED")
        self.assertEqual(source["data"]["text"], source["data"]["original_text"])

    def test_subtitle_spans_keep_exact_text_and_time_links(self):
        text = "WEBVTT\n\n00:00:01.200 --> 00:00:02.400\nHello world.\n\n00:00:03.000 --> 00:00:04.250\nNo, thank you.\n"
        source = self.ingest.ingest(source_payload(text, "vtt"))
        spans = self.ingest.spans(source["id"])
        self.assertEqual([x["data"]["text"] for x in spans], ["Hello world.", "No, thank you."])
        self.assertEqual([(x["data"]["start_ms"], x["data"]["end_ms"]) for x in spans], [(1200, 2400), (3000, 4250)])
        evidence = EvidenceService(self.store)
        self.assertTrue(all(evidence.verify_span(s["id"])["verified"] for s in spans))

    def test_disallowed_or_missing_content_is_blocked_without_spans(self):
        blocked = self.ingest.ingest(source_payload("private passage", rights={"allowed": False, "reason": "denied",
                                                                                "license": "none", "private": True,
                                                                                "allow_export": False, "allow_model": False}))
        empty = self.ingest.ingest(source_payload("", key="empty"))
        self.assertEqual(blocked["data"]["status"], "BLOCKED")
        self.assertNotIn("text", blocked["data"])
        self.assertNotIn("original_text", blocked["data"])
        self.assertEqual(blocked["data"]["content_hash"], hashlib.sha256(b"private passage").hexdigest())
        self.assertEqual(empty["data"]["status"], "BLOCKED")
        self.assertEqual(self.ingest.spans(blocked["id"]), [])
        result = EvidenceService(self.store).analyze(empty["id"])
        self.assertEqual(result["claims"], [])
        self.assertEqual(result["analysis_status"], "blocked")

    def test_offline_analysis_preserves_negation_and_is_idempotent(self):
        source = self.ingest.ingest(source_payload("It does not always work. Perhaps it helps."))
        svc = EvidenceService(self.store)
        result = svc.analyze(source["id"])
        self.assertEqual([c["data"]["text"] for c in result["claims"]], ["It does not always work.", "Perhaps it helps."])
        self.assertEqual(result["claims"][0]["data"]["review_status"], "unreviewed")
        self.assertIn("not always", result["claims"][0]["data"]["qualifiers"])
        self.assertEqual(result["analysis_status"], "completed_with_warnings")
        again = svc.analyze(source["id"])
        self.assertEqual(len(again["claims"]), 2)
        self.assertIn("does not establish empirical truth", " ".join(again["warnings"]))

    def test_provider_quote_must_be_exact_and_invalid_output_falls_back(self):
        payload = source_payload("The answer may change.")
        payload["rights"]["allow_model"] = True
        source = self.ingest.ingest(payload)
        spans = self.ingest.spans(source["id"])
        bad = Provider({"claims": [{"text": "Invented claim", "quote": "fabricated quote", "span_ids": [spans[0]["id"]], "qualifiers": [], "speaker": "Speaker"}], "arguments": [], "interpretations": []})
        result = EvidenceService(self.store, bad).analyze(source["id"])
        self.assertEqual(result["claims"][0]["data"]["analysis_mode"], "offline_exact_span")
        self.assertTrue(any("provider proposals rejected" in w for w in result["warnings"]))

    def test_valid_provider_interpretation_and_toulmin_fields_are_labeled(self):
        payload = source_payload("Because rain fell, the road is wet.")
        payload["rights"]["allow_model"] = True
        source = self.ingest.ingest(payload)
        span = self.ingest.spans(source["id"])[0]
        proposal = Provider({
            "claims": [{"text": "The speaker says the road is wet.", "quote": "the road is wet", "span_ids": [span["id"]], "qualifiers": [], "speaker": None}],
            "arguments": [{"claim": "The speaker says the road is wet.", "grounds": "rain fell", "warrant": "rain can wet roads", "backing": "", "qualifier": "", "rebuttal": "", "span_ids": [span["id"]]}],
            "interpretations": [{"reading": "The speaker offers a causal explanation.", "evidence_for": "Because", "evidence_against": "", "span_ids": [span["id"]], "label": "alternative_interpretation"}],
        })
        result = EvidenceService(self.store, proposal).analyze(source["id"])
        self.assertEqual(result["arguments"][0]["data"]["warrant"], "rain can wet roads")
        self.assertEqual(result["arguments"][0]["data"]["epistemic_type"], "INTERPRETATION")
        self.assertEqual(result["interpretations"][0]["data"]["epistemic_type"], "INTERPRETATION")
        self.assertTrue(result["claims"][0]["data"]["speaker_uncertain"])
        self.assertEqual(result["claims"][0]["data"]["proposal_type"], "unverified_paraphrase")

    def test_exact_model_quote_does_not_verify_a_fabricated_famous_person_attribution(self):
        payload = source_payload("The answer is forty-two.")
        payload["author"] = "Transcript editor; speaker not identified"
        payload["rights"]["allow_model"] = True
        source = self.ingest.ingest(payload)
        span = self.ingest.spans(source["id"])[0]
        provider = Provider({
            "claims": [{"text": span["data"]["text"], "quote": span["data"]["text"],
                        "span_ids": [span["id"]], "qualifiers": [], "speaker": "FamousPerson"}],
            "arguments": [], "interpretations": [],
        })

        result = EvidenceService(self.store, provider).analyze(source["id"])
        claim = result["claims"][0]["data"]
        self.assertEqual(claim["quote"], span["data"]["text"])
        self.assertIsNone(claim["speaker"])
        self.assertEqual(claim["speaker_suggestion"], "FamousPerson")
        self.assertTrue(claim["speaker_uncertain"])
        self.assertEqual(claim["speaker_attribution_status"], "unverified_model_suggestion")
        self.assertEqual(source["data"]["author"], "Transcript editor; speaker not identified")
        self.assertEqual(result["analysis_status"], "completed_with_warnings")

    def test_conflicting_source_author_and_model_speaker_leave_attribution_unresolved(self):
        payload = source_payload("The meeting begins now.")
        payload["author"] = "FamousPerson"
        payload["rights"]["allow_model"] = True
        source = self.ingest.ingest(payload)
        span = self.ingest.spans(source["id"])[0]
        provider = Provider({
            "claims": [{"text": "The meeting begins now.", "quote": "The meeting begins now.",
                        "span_ids": [span["id"]], "qualifiers": [], "speaker": "AnotherPerson"}],
            "arguments": [], "interpretations": [],
        })

        claim = EvidenceService(self.store, provider).analyze(source["id"])["claims"][0]["data"]
        self.assertIsNone(claim["speaker"])
        self.assertEqual(claim["speaker_suggestion"], "AnotherPerson")
        self.assertTrue(claim["speaker_uncertain"])
        self.assertEqual(source["data"]["author"], "FamousPerson")

    def test_provider_requires_explicit_model_sharing_consent(self):
        source = self.ingest.ingest(source_payload("A source utterance."))
        span = self.ingest.spans(source["id"])[0]
        provider = Provider({"claims": [{"text": span["data"]["text"], "quote": span["data"]["text"],
                                          "span_ids": [span["id"]], "qualifiers": [], "speaker": None}],
                            "arguments": [], "interpretations": []})
        result = EvidenceService(self.store, provider).analyze(source["id"])
        self.assertEqual(result["claims"][0]["data"]["analysis_mode"], "offline_exact_span")
        self.assertIn("explicit model-sharing consent", " ".join(result["warnings"]))

    def test_analysis_plan_carries_canonical_source_lineage(self):
        payload = source_payload("Private transcript.")
        payload["rights"].update(private=True, allow_export=False, allow_model=True)
        source = self.ingest.ingest(payload)
        span = self.ingest.spans(source["id"])[0]
        provider = Provider({"claims": [{"text": span["data"]["text"], "quote": span["data"]["text"],
                                          "span_ids": [span["id"]], "qualifiers": [], "speaker": None}],
                            "arguments": [], "interpretations": []})
        EvidenceService(self.store, provider).analyze(source["id"])
        plan = next(r for r in self.store.list("assessment") if r["data"].get("analysis_kind") == "evidence_analysis_plan")
        self.assertEqual(plan["data"]["source_id"], source["id"])
        self.assertEqual(plan["data"]["source_refs"], [source["id"]])
        self.assertTrue(any(edge["source_id"] == plan["id"] and edge["target_id"] == source["id"]
                            and edge["relation"] == "DEPENDS_ON" for edge in self.store.edges()))

    def test_legacy_analysis_plan_is_migrated_only_when_anchored_to_source(self):
        source = self.ingest.ingest(source_payload("Legacy anchor."))
        span = self.ingest.spans(source["id"])[0]
        analysis_key = f"evidence-analysis:{source['id']}:v1"
        proposal = {"claims": [{"text": "Legacy anchor.", "quote": "Legacy anchor.",
                                "span_ids": [span["id"]], "qualifiers": [], "speaker": None}],
                    "arguments": [], "interpretations": []}
        self.store.put("assessment", {"plan_key": f"evidence-plan:{source['id']}:v1",
                                       "analysis_key": analysis_key,
                                       "analysis_kind": "evidence_analysis_plan",
                                       "proposals": proposal, "warnings": []}, immutable=True)
        result = EvidenceService(self.store).analyze(source["id"])
        self.assertEqual(result["claims"][0]["data"]["analysis_mode"], "provider_proposal")
        migrated = [r for r in self.store.list("assessment") if r["data"].get("analysis_kind") == "evidence_analysis_plan"
                    and r["data"].get("source_id") == source["id"]]
        self.assertEqual(len(migrated), 1)
        self.assertEqual(migrated[0]["data"]["plan_key"], f"evidence-plan:{source['id']}:v2")

    def test_default_source_family_is_content_addressed(self):
        payloads = [source_payload("Same text.", key="family-a"),
                    source_payload("Same text.", key="family-b"),
                    source_payload("Different text.", key="family-c")]
        for payload in payloads:
            payload.pop("source_family")
        first, duplicate, other = [self.ingest.ingest(payload) for payload in payloads]
        self.assertEqual(first["data"]["source_family"], duplicate["data"]["source_family"])
        self.assertNotEqual(first["data"]["source_family"], other["data"]["source_family"])

    def test_review_versions_without_rewriting_original_quote(self):
        source = self.ingest.ingest(source_payload("This result is certain."))
        claim = EvidenceService(self.store).analyze(source["id"])["claims"][0]
        corrected = EvidenceService(self.store).review(claim["id"], {
            "status": "corrected", "reviewer": "human", "correction": "The result is uncertain.", "note": "Correction after rereading."})
        self.assertEqual(corrected["version"], 2)
        self.assertEqual(corrected["data"]["text"], "This result is certain.")
        self.assertEqual(corrected["data"]["quote"], "This result is certain.")
        self.assertEqual(corrected["data"]["reviews"][0]["correction"], "The result is uncertain.")

    def test_span_verifier_detects_tampered_offsets_or_text(self):
        source = self.ingest.ingest(source_payload("Anchor here."))
        span = self.ingest.spans(source["id"])[0]
        tampered = dict(span["data"])
        tampered["text"] = "Anchor there."
        tampered["content_hash"] = hashlib.sha256(tampered["text"].encode()).hexdigest()
        # Deliberately corrupt the test store directly to exercise independent
        # verification; the public StorePort correctly makes spans immutable.
        self.store.records[span["id"]]["record"]["data"] = tampered
        verified = EvidenceService(self.store).verify_span(span["id"])
        self.assertFalse(verified["verified"])
        self.assertIn("exact source substring", " ".join(verified["issues"]))

    def test_idempotency_key_binds_denied_content_hash(self):
        self.ingest.ingest(source_payload("first secret", rights={"allowed": False, "license": "none",
                                                                    "private": True, "allow_export": False,
                                                                    "allow_model": False}))
        with self.assertRaises(Conflict):
            self.ingest.ingest(source_payload("different secret", rights={"allowed": False, "license": "none",
                                                                             "private": True, "allow_export": False,
                                                                             "allow_model": False}))

    def test_expired_rights_block_source_and_analysis(self):
        payload = source_payload("Past license.", rights={"allowed": True, "license": "user-provided",
                                                             "private": False, "allow_export": True,
                                                             "allow_model": False,
                                                             "expires_at": "2000-01-01T00:00:00+00:00"})
        source = self.ingest.ingest(payload)
        self.assertEqual(source["data"]["status"], "BLOCKED")
        self.assertNotIn("original_text", source["data"])
        self.assertEqual(EvidenceService(self.store).analyze(source["id"])["claims"], [])

    def test_expired_rights_hide_previously_cached_analysis(self):
        payload = source_payload("Rights can expire.", rights={"allowed": True, "license": "user-provided",
                                                                 "private": False, "allow_export": True,
                                                                 "allow_model": False,
                                                                 "expires_at": "2999-01-01T00:00:00+00:00"})
        source = self.ingest.ingest(payload)
        service = EvidenceService(self.store)
        self.assertTrue(service.analyze(source["id"])["claims"])
        span_id = self.store.list("span")[0]["id"]
        self.store.records[source["id"]]["record"]["data"]["rights"]["expires_at"] = "2000-01-01T00:00:00+00:00"
        result = service.analyze(source["id"])
        self.assertEqual(result["claims"], [])
        self.assertIn("expired", " ".join(result["warnings"]))
        self.assertEqual(self.ingest.spans(source["id"]), [])
        verified = service.verify_span(span_id)
        self.assertFalse(verified["verified"])
        self.assertIsNone(verified["actual_text"])

    def test_source_rights_shape_is_required(self):
        payload = source_payload("Text", rights={"allowed": True})
        with self.assertRaises(ValidationError):
            self.ingest.ingest(payload)

    def test_ingest_replay_repairs_missing_span_after_interruption(self):
        payload = source_payload("First. Second. Third.")
        source = self.ingest.ingest(payload)
        spans = self.ingest.spans(source["id"])
        removed_id = spans[-1]["id"]
        del self.store.records[removed_id]
        self.store.keys = {key: value for key, value in self.store.keys.items() if value[2] != removed_id}
        self.store.links = [edge for edge in self.store.links if edge["target_id"] != removed_id]
        self.ingest.ingest(payload)
        self.assertEqual(len(self.ingest.spans(source["id"])), 3)

    def test_analysis_refuses_cached_results_after_span_reverification_fails(self):
        source = self.ingest.ingest(source_payload("Evidence is exact."))
        service = EvidenceService(self.store)
        first = service.analyze(source["id"])
        span = self.ingest.spans(source["id"])[0]
        self.store.records[span["id"]]["record"]["data"]["text"] = "tampered"
        second = service.analyze(source["id"])
        self.assertTrue(first["claims"])
        self.assertEqual(second["claims"], [])
        self.assertIn("failed independent verification", " ".join(second["warnings"]))

    def test_analysis_replay_repairs_interrupted_offline_claim_batch(self):
        source = self.ingest.ingest(source_payload("One claim. Another claim."))
        service = EvidenceService(self.store)
        initial = service.analyze(source["id"])
        removed = initial["claims"][-1]
        del self.store.records[removed["id"]]
        self.store.keys = {key: value for key, value in self.store.keys.items() if value[2] != removed["id"]}
        self.store.links = [edge for edge in self.store.links if edge["target_id"] != removed["id"]]
        replay = service.analyze(source["id"])
        self.assertEqual(len(replay["claims"]), 2)
        self.assertEqual(len([r for r in self.store.list("claim") if r["data"].get("source_id") == source["id"]]), 2)

    def test_analysis_replay_uses_persisted_provider_proposals(self):
        payload = source_payload("The answer is clear.")
        payload["rights"]["allow_model"] = True
        source = self.ingest.ingest(payload)
        span = self.ingest.spans(source["id"])[0]
        provider = Provider({"claims": [{"text": "The answer is clear.", "quote": "The answer is clear.",
                                          "span_ids": [span["id"]], "qualifiers": [], "speaker": None}],
                            "arguments": [], "interpretations": []})
        service = EvidenceService(self.store, provider)
        initial = service.analyze(source["id"])
        removed = initial["claims"][0]
        del self.store.records[removed["id"]]
        self.store.keys = {key: value for key, value in self.store.keys.items() if value[2] != removed["id"]}
        self.store.links = [edge for edge in self.store.links if edge["target_id"] != removed["id"]]
        replay = service.analyze(source["id"])
        self.assertEqual(len(replay["claims"]), 1)
        self.assertEqual(provider.calls, 1)


if __name__ == "__main__":
    unittest.main()
