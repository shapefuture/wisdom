import unittest

from wisdom.errors import PermissionDenied
from wisdom.invention import InventionEngine, _source_eligible
from wisdom.store import Store
from wisdom.theory import TheoryEngine


class MemoryStore:
    def __init__(self):
        self.records = {}
        self.edges_list = []
        self.n = 0

    def put(self, kind, data, *, record_id=None, expected_version=None, immutable=False,
            idempotency_key=None, principal="local-user", event_type=None):
        self.n += 1
        rid = record_id or f"{kind}-{self.n}"
        rec = {"id": rid, "kind": kind, "version": 1, "data": data}
        self.records[rid] = rec
        return rec

    def get(self, record_id, version=None):
        if record_id not in self.records:
            from wisdom.errors import NotFound
            raise NotFound(record_id)
        return self.records[record_id]

    def list(self, kind=None):
        return [r for r in self.records.values() if kind is None or r["kind"] == kind]

    def link(self, source_id, target_id, relation, *, polarity="neutral", data=None):
        edge = {"source_id": source_id, "target_id": target_id, "relation": relation,
                "polarity": polarity, "data": data or {}}
        self.edges_list.append(edge)
        return edge


class Provider:
    name = "test-provider"

    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def complete(self, operation, payload):
        self.calls.append((operation, payload))
        return self.outputs.get(operation, {})


def add_source_claim(store, source_id, claim_id, family, **rights):
    store.put("source", {"title": source_id, "source_family": family,
                         "rights": {"allowed": True, "private": False, **rights}}, record_id=source_id)
    store.put("claim", {"text": "A feedback loop stabilizes the shared resource.",
                         "source_id": source_id, "span_ids": [],
                         "epistemic_type": "SOURCE_ATTRIBUTED_CLAIM"}, record_id=claim_id)


class TheoryEngineTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        add_source_claim(self.store, "s1", "c1", "family-a")
        add_source_claim(self.store, "s2", "c2", "family-a")
        add_source_claim(self.store, "s3", "c3", "family-b")

    def test_theory_tracks_claims_and_independent_source_families(self):
        engine = TheoryEngine(self.store)
        result = engine.build({"title": "Scoped feedback pattern", "claim_ids": ["c1", "c2", "c3"],
                               "scope": ["shared resource"], "evidence_for": ["c1"],
                               "evidence_against": ["c3"]})
        data = result["data"]
        self.assertEqual(data["independent_source_family_count"], 2)
        self.assertEqual(data["source_families"], {"family-a": ["s1", "s2"], "family-b": ["s3"]})
        self.assertEqual(data["epistemic_type"], "INTERPRETATION")
        self.assertEqual(data["tested_status"], "untested_hypothesis")
        self.assertEqual(data["causal_status"], "not_established")
        theory_id = result["id"]
        self.assertIn((theory_id, "c1", "SUPPORTS"),
                      [(e["source_id"], e["target_id"], e["relation"]) for e in self.store.edges_list])
        self.assertIn((theory_id, "c3", "CONTRADICTS"),
                      [(e["source_id"], e["target_id"], e["relation"]) for e in self.store.edges_list])

    def test_unknown_content_families_are_not_counted_as_independent_origins(self):
        add_source_claim(self.store, "hash-a", "hash-claim-a", "content:aaa")
        add_source_claim(self.store, "hash-b", "hash-claim-b", "content:bbb")
        self.store.records["hash-a"]["data"]["content_hash"] = "aaa"
        self.store.records["hash-b"]["data"]["content_hash"] = "bbb"
        result = TheoryEngine(self.store).build({"title": "Conservative count",
            "claim_ids": ["hash-claim-a", "hash-claim-b"], "scope": ["bounded"]})
        data = result["data"]
        self.assertEqual(data["source_family_count"], 2)
        self.assertEqual(data["independent_source_family_count"], 1)
        self.assertEqual(data["independence_status"],
            "asserted_family_labels_unverified; unknown_or_hash_only_sources_grouped_conservatively; identical_content_hashes_collapsed")

    def test_identical_content_hashes_collapse_across_asserted_family_labels(self):
        add_source_claim(self.store, "duplicate-a", "duplicate-claim-a", "journal-a")
        add_source_claim(self.store, "duplicate-b", "duplicate-claim-b", "journal-b")
        self.store.records["duplicate-a"]["data"]["content_hash"] = "same-original"
        self.store.records["duplicate-b"]["data"]["content_hash"] = "same-original"
        result = TheoryEngine(self.store).build({"title": "Duplicate source count",
            "claim_ids": ["duplicate-claim-a", "duplicate-claim-b"], "scope": ["bounded"]})
        data = result["data"]
        self.assertEqual(data["source_family_count"], 2)
        self.assertEqual(data["independent_source_family_count"], 1)
        self.assertEqual(data["source_families"],
            {"journal-a": ["duplicate-a"], "journal-b": ["duplicate-b"]})

    def test_theory_rejects_unrelated_evidence_and_denied_ancestry(self):
        with self.assertRaises(Exception):
            TheoryEngine(self.store).build({"title": "x", "claim_ids": ["c1"], "evidence_for": ["c3"]})
        self.store.put("source", {"rights": {"allowed": False}, "source_family": "bad"}, record_id="bad")
        self.store.put("claim", {"source_id": "bad", "text": "claim"}, record_id="bad-claim")
        with self.assertRaises(PermissionDenied):
            TheoryEngine(self.store).build({"title": "x", "claim_ids": ["bad-claim"]})

    def test_provider_output_is_a_scoped_proposal(self):
        self.store.records["s1"]["data"]["rights"]["allow_model"] = True
        provider = Provider({"theory.build": {"explanation": "proposed account", "claim_ids": ["evil"],
                                              "tested_status": "validated", "scope": ["small teams"]}})
        result = TheoryEngine(self.store, provider).build({"title": "T", "claim_ids": ["c1"],
                                                           "allow_model": True})
        d = result["data"]
        self.assertEqual(d["claim_ids"], ["c1"])
        self.assertEqual(d["tested_status"], "untested_hypothesis")
        self.assertEqual(d["scope"], ["small teams"])
        self.assertEqual(d["explanation"], "proposed account")

    def test_mechanism_marks_offline_draft_as_transfer_hypothesis(self):
        m = TheoryEngine(self.store).mechanism({"title": "Feedback buffer", "functional_signature": ["stabilize", "resource"],
            "structural_signature": ["actor", "feedback"], "boundary_conditions": ["stable input"]})
        self.assertEqual(m["data"]["epistemic_type"], "TRANSFER_HYPOTHESIS")
        self.assertEqual(m["data"]["source_endorsement"], "none_claimed")
        self.assertEqual(m["data"]["tested_status"], "untested_hypothesis")

    def test_mechanism_provider_requires_user_opt_in_and_canonical_sources(self):
        self.store.records["s1"]["data"]["rights"]["allow_model"] = True
        provider = Provider({"theory.mechanism": {"title": "Provider mechanism"}})
        engine = TheoryEngine(self.store, provider)
        base = {"title": "Mechanism", "claim_ids": ["c1"],
                "boundary_conditions": ["bounded context"], "functional_signature": ["buffer"],
                "structural_signature": ["feedback"]}
        engine.mechanism(base)
        self.assertEqual(provider.calls, [])
        engine.mechanism({**base, "allow_model": True})
        self.assertEqual(len(provider.calls), 1)
        op, payload = provider.calls[0]
        self.assertEqual(op, "theory.mechanism")
        self.assertEqual(payload["source_ids"], ["s1"])

    def test_unresolved_drafts_must_be_explicit(self):
        with self.assertRaises(Exception):
            TheoryEngine(self.store).build({"title": "Unscoped", "claim_ids": ["c1"]})
        draft = TheoryEngine(self.store).build({"title": "Open theory", "claim_ids": ["c1"],
            "draft_status": "unresolved_draft"})
        self.assertEqual(draft["data"]["draft_status"], "unresolved_draft")

    def test_source_grants_alone_do_not_authorize_user_context_sharing(self):
        self.store.records["s1"]["data"]["rights"]["private"] = True
        self.store.records["s1"]["data"]["rights"]["allow_model"] = True
        self.store.records["s1"]["data"]["original_text"] = "sensitive local source"
        provider = Provider({"theory.build": {"explanation": "remote proposal", "scope": ["all"]}})
        result = TheoryEngine(self.store, provider).build({"title": "Local synthesis", "claim_ids": ["c1"],
                                                           "scope": ["local context"]})
        self.assertEqual(result["data"]["explanation"], "")
        self.assertEqual(provider.calls, [])

    def test_theory_provider_requires_explicit_user_opt_in_and_sends_canonical_sources(self):
        self.store.records["s1"]["data"]["rights"]["allow_model"] = True
        provider = Provider({"theory.build": {"explanation": "proposal", "scope": ["small teams"]}})
        engine = TheoryEngine(self.store, provider)
        engine.build({"title": "local by default", "claim_ids": ["c1"], "scope": ["small teams"]})
        self.assertEqual(provider.calls, [])
        engine.build({"title": "opted in", "claim_ids": ["c1"], "scope": ["small teams"],
                      "allow_model": True, "source_ids": ["attacker-selected"]})
        self.assertEqual(len(provider.calls), 1)
        op, payload = provider.calls[0]
        self.assertEqual(op, "theory.build")
        self.assertEqual(payload["source_ids"], ["s1"])
        self.assertNotIn("attacker-selected", payload["source_ids"])

    def test_mechanism_theory_ancestry_obeys_source_rights(self):
        self.store.records["s1"]["data"]["rights"]["private"] = True
        theory = TheoryEngine(self.store).build({"title": "Private theory", "claim_ids": ["c1"],
                                                 "scope": ["local only"]})
        mechanism = TheoryEngine(self.store).mechanism({"title": "Derived mechanism",
            "theory_id": theory["id"], "boundary_conditions": ["only if private source remains permitted"],
            "functional_signature": ["feedback", "stability"], "structural_signature": ["loop", "resource"]})
        child = TheoryEngine(self.store).mechanism({"title": "Child", "source_mechanism_ids": [mechanism["id"]],
            "functional_signature": ["feedback", "resource"], "structural_signature": ["loop", "stability"],
            "boundary_conditions": ["parent conditions apply"]})
        self.assertEqual(child["data"]["source_mechanism_ids"], [mechanism["id"]])
        self.assertTrue(_source_eligible(self.store, child))
        self.store.records["s1"]["data"]["rights"]["allowed"] = False
        self.assertFalse(_source_eligible(self.store, child))

    def test_missing_or_expired_source_rights_fail_closed(self):
        self.store.records["s1"]["data"].pop("rights")
        with self.assertRaises(PermissionDenied):
            TheoryEngine(self.store).build({"title": "T", "claim_ids": ["c1"], "scope": ["local"]})
        self.store.records["s1"]["data"]["rights"] = {"allowed": True, "private": False,
                                                           "expires_at": "2000-01-01T00:00:00Z"}
        with self.assertRaises(PermissionDenied):
            TheoryEngine(self.store).build({"title": "T", "claim_ids": ["c1"], "scope": ["local"]})


class InventionEngineTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.problem = InventionEngine(self.store).problem({
            "title": "Resource keeps oscillating", "description": "A feedback loop causes shared resource allocation to oscillate",
            "desired_state": "stable shared resource", "maintaining_force": "no feedback buffer",
            "actors": ["operators"], "constraints": ["limited time"], "failed_attempts": ["manual correction"],
            "domain": "operations", "contradictions": [{"side_a": "fast response", "side_b": "stable policy"}]})
        self.mechanism = self.store.put("mechanism", {"title": "Feedback buffer", "claim_ids": [],
            "functional_signature": ["stabilizes", "shared", "resource"],
            "structural_signature": ["feedback", "allocation", "loop"],
            "boundary_conditions": ["requires timely signals"], "contraindications": ["stale signals"]})

    def test_forge_maps_mechanism_and_marks_novelty_unchecked(self):
        result = InventionEngine(self.store).forge(self.problem["id"])
        self.assertGreaterEqual(len(result["ideas"]), 2)  # transfer + contradiction alternative
        transfer = result["ideas"][0]["data"]
        self.assertEqual(transfer["source_mechanism_ids"], [self.mechanism["id"]])
        self.assertTrue(transfer["mappings"]["candidate_roles"]["similarity_is_not_transfer_evidence"])
        self.assertIn("stale signals", transfer["mismatches"])
        self.assertEqual(transfer["epistemic_type"], "TRANSFER_HYPOTHESIS")
        self.assertEqual(transfer["novelty_status"], "unchecked")
        self.assertEqual(transfer["prior_art_status"], "unchecked")

    def test_no_match_preserves_information_deficit(self):
        self.store.records[self.mechanism["id"]]["data"]["functional_signature"] = ["photosynthesis", "leaves"]
        self.store.records[self.mechanism["id"]]["data"]["structural_signature"] = ["sunlight", "chlorophyll"]
        problem = InventionEngine(self.store).problem({"title": "Unrelated case",
            "description": "A team struggles with a botanical sunlight schedule", "domain": "gardening"})
        result = InventionEngine(self.store).forge(problem["id"])
        self.assertEqual(result["ideas"], [])
        self.assertTrue(any(i["type"] == "information_deficit" for i in result["missing_evidence"]))

    def test_denied_mechanism_ancestry_is_excluded(self):
        self.store.put("source", {"rights": {"allowed": False}, "source_family": "private"}, record_id="private-source")
        self.store.put("claim", {"source_id": "private-source", "text": "feedback"}, record_id="private-claim")
        bad = self.store.put("mechanism", {"title": "bad", "claim_ids": ["private-claim"],
                            "functional_signature": ["feedback", "shared", "resource"],
                            "structural_signature": ["loop", "allocation"]})
        result = InventionEngine(self.store).forge(self.problem["id"])
        ids = [mid for idea in result["ideas"] for mid in idea["data"].get("source_mechanism_ids", [])]
        self.assertNotIn(bad["id"], ids)

    def test_red_team_returns_eight_labeled_checks_without_claiming_independence(self):
        idea = self.store.put("idea", {"title": "candidate", "epistemic_type": "TRANSFER_HYPOTHESIS"})
        result = InventionEngine(self.store).red_team(idea["id"])
        self.assertEqual(len(result["findings"]), 8)
        self.assertFalse(result["independent_human_review"])
        self.assertEqual(result["novelty_status"], "unchecked")
        self.assertIn("prior_art", [f["criterion"] for f in result["findings"]])

    def test_provider_cannot_inject_unavailable_mechanism_as_source(self):
        provider = Provider({"invention.forge": {"ideas": [{"title": "unsupported", "source_mechanism_ids": ["unknown"]}]}})
        opted_in = InventionEngine(self.store).problem({"title": "Opted-in case",
            "description": "A feedback loop causes shared resource allocation to oscillate",
            "allow_model": True})
        result = InventionEngine(self.store, provider).forge(opted_in["id"])
        self.assertTrue(all("unknown" not in i["data"].get("source_mechanism_ids", []) for i in result["ideas"]))
        self.assertEqual(provider.calls[-1][0], "invention.forge")

    def test_discover_returns_opportunity_candidates_and_explicit_unknowns(self):
        engine = InventionEngine(self.store)
        result = engine.discover(self.mechanism["id"])
        self.assertEqual(result["opportunities"][0]["problem_id"], self.problem["id"])
        self.assertEqual(result["opportunities"][0]["mapping_status"], "unresolved_candidate")
        self.assertEqual(result["unknown_applications"]["status"], "unknown_applications_remain")
        no_match = self.store.put("mechanism", {"title": "Botany", "functional_signature": ["chlorophyll"],
            "structural_signature": ["sunlight"]})
        result = engine.discover(no_match["id"])
        self.assertEqual(result["opportunities"], [])
        self.assertEqual(result["unknown_applications"]["status"], "no_match")

    def test_forge_does_not_send_private_source_candidates_to_provider(self):
        add_source_claim(self.store, "private-source", "private-claim", "private", private=True)
        provider = Provider({"invention.diagnose": {}, "invention.forge": {"ideas": []}})
        mechanism = self.store.put("mechanism", {"title": "private mechanism", "claim_ids": ["private-claim"],
            "functional_signature": ["shared", "resource"], "structural_signature": ["feedback", "loop"],
            "boundary_conditions": ["local only"]})
        opted_in = InventionEngine(self.store).problem({"title": "Opted-in case",
            "description": "A feedback loop causes shared resource allocation to oscillate",
            "allow_model": True})
        InventionEngine(self.store, provider).forge(opted_in["id"])
        forge_calls = [payload for operation, payload in provider.calls if operation == "invention.forge"]
        candidate_ids = {entry["id"] for payload in forge_calls for entry in payload["candidate_mechanisms"]}
        self.assertNotIn(mechanism["id"], candidate_ids)
        self.assertTrue(_source_eligible(self.store, mechanism))

    def test_opted_in_problem_sends_only_model_permitted_source_candidates(self):
        add_source_claim(self.store, "shareable-source", "shareable-claim", "shareable",
                         allow_model=True)
        mechanism = self.store.put("mechanism", {"title": "Shareable", "claim_ids": ["shareable-claim"],
            "functional_signature": ["shared", "resource"], "structural_signature": ["feedback", "loop"],
            "boundary_conditions": ["local only"]})
        problem = InventionEngine(self.store).problem({"title": "Opted-in",
            "description": "A feedback loop causes shared resource allocation to oscillate",
            "allow_model": True})
        provider = Provider({"invention.diagnose": {}, "invention.forge": {"ideas": []}})
        InventionEngine(self.store, provider).forge(problem["id"])
        diagnosis = [payload for op, payload in provider.calls if op == "invention.diagnose"]
        forge = [payload for op, payload in provider.calls if op == "invention.forge"]
        self.assertEqual(diagnosis[0]["problem_id"], problem["id"])
        self.assertEqual(forge[0]["problem_id"], problem["id"])
        candidates = {item["id"]: item for item in forge[0]["candidate_mechanisms"]}
        self.assertIn(mechanism["id"], candidates)
        self.assertEqual(forge[0]["source_ids"], ["shareable-source"])

    def test_problem_model_opt_in_is_boolean_and_defaults_off(self):
        engine = InventionEngine(self.store)
        self.assertIs(self.problem["data"]["allow_model"], False)
        provider = Provider({"invention.diagnose": {}, "invention.forge": {"ideas": []}})
        InventionEngine(self.store, provider).forge(self.problem["id"])
        self.assertEqual(provider.calls, [])
        opted_in = engine.problem({"title": "Permitted", "description": "A distinct user-entered case",
                                   "allow_model": True})
        self.assertIs(opted_in["data"]["allow_model"], True)
        with self.assertRaises(Exception):
            engine.problem({"title": "Not boolean", "description": "A case", "allow_model": "yes"})

    def test_real_store_edges_use_canonical_relations_and_polarities(self):
        store = Store()
        try:
            source = store.put("source", {"title": "Source", "source_family": "f", "original_text": "text",
                "rights": {"allowed": True, "private": True, "allow_model": False}})
            claim = store.put("claim", {"text": "A claim", "source_id": source["id"], "span_ids": []})
            theory = TheoryEngine(store).build({"title": "Theory", "claim_ids": [claim["id"]],
                "scope": ["bounded"] , "evidence_for": [claim["id"]]})
            edge = store.edges(theory["id"])[0]
            self.assertEqual(edge["relation"], "SUPPORTS")
            self.assertEqual(edge["polarity"], "positive")
        finally:
            store.close()

    def test_real_store_private_ancestry_through_theory_forge_and_discover(self):
        store = Store()
        try:
            source = store.put("source", {"title": "Private source", "source_family": "private-family",
                "original_text": "local-only evidence", "rights": {"allowed": True, "private": True,
                "allow_export": False, "allow_model": False}})
            claim = store.put("claim", {"text": "Feedback stabilizes a shared resource.",
                                         "source_id": source["id"], "span_ids": []})
            provider = Provider({"invention.diagnose": {}, "invention.forge": {"ideas": []},
                                 "invention.discover": {"opportunities": []}})
            theory = TheoryEngine(store, provider).build({"title": "Local theory", "claim_ids": [claim["id"]],
                                                           "scope": ["local resource allocation"]})
            mechanism = TheoryEngine(store, provider).mechanism({"title": "Feedback buffer",
                "theory_id": theory["id"], "source_mechanism_ids": [],
                "problem_state": "shared resource allocation oscillates", "intervention": "buffer feedback",
                "effects": ["stability"], "boundary_conditions": ["timely feedback"],
                "functional_signature": ["shared", "resource", "stability"],
                "structural_signature": ["feedback", "allocation", "loop"], "source_domain": "systems"})
            problem = InventionEngine(store).problem({"title": "Allocation oscillation",
                "description": "Feedback loops make shared resource allocation oscillate",
                "desired_state": "stable resource allocation", "maintaining_force": "delayed feedback",
                "allow_model": True})
            invention = InventionEngine(store, provider)
            forged = invention.forge(problem["id"])
            self.assertTrue(forged["ideas"])
            idea = forged["ideas"][0]
            relations = {edge["relation"] for edge in store.edges(idea["id"])}
            self.assertIn("STRUCTURALLY_MATCHES", relations)
            self.assertIn("INSPIRED_BY", relations)
            forge_payloads = [payload for operation, payload in provider.calls if operation == "invention.forge"]
            self.assertTrue(forge_payloads)
            self.assertEqual(forge_payloads[0]["problem_id"], problem["id"])
            self.assertEqual(forge_payloads[0]["candidate_mechanisms"], [])
            self.assertNotIn("local-only evidence", str(forge_payloads))
            self.assertNotIn(mechanism["id"], str(forge_payloads))
            discovered = invention.discover(mechanism["id"])
            self.assertTrue(discovered["opportunities"])
            discovery_payloads = [payload for operation, payload in provider.calls if operation == "invention.discover"]
            self.assertEqual(discovery_payloads, [])
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
