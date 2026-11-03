from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from wisdom.errors import Conflict, NotFound, ValidationError
from wisdom.learning import DecisionService, OutcomeLab
from wisdom.store import Store


class FakeStore:
    """Small StorePort fake that enforces version and immutable semantics."""
    def __init__(self):
        self.records = {}
        self.edges_data = []
        self.next_id = 1

    def put(self, kind, data, *, record_id=None, expected_version=None, immutable=False,
            idempotency_key=None, principal="local-user", event_type=None):
        rid = record_id or f"{kind}-{self.next_id}"
        if record_id is None:
            self.next_id += 1
        old = self.records.get(rid)
        if old:
            if old["immutable"] or immutable:
                raise Conflict("immutable record")
            if expected_version != old["record"]["version"]:
                raise Conflict("version mismatch")
            version = old["record"]["version"] + 1
            created = old["record"]["created_at"]
        else:
            if expected_version is not None:
                raise Conflict("missing record")
            version = 1
            created = datetime.now(timezone.utc).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        envelope = {"id": rid, "kind": kind, "version": version,
                    "created_at": created, "updated_at": now, "data": deepcopy(data)}
        self.records[rid] = {"record": envelope, "immutable": immutable}
        return deepcopy(envelope)

    def get(self, record_id, version=None):
        if record_id not in self.records:
            raise NotFound(record_id)
        record = self.records[record_id]["record"]
        if record["version"] != version and version is not None:
            raise NotFound(record_id)
        return deepcopy(record)

    def list(self, kind=None):
        return [deepcopy(x["record"]) for x in self.records.values()
                if kind is None or x["record"]["kind"] == kind]

    def link(self, source_id, target_id, relation, *, polarity="neutral", data=None):
        edge = {"source_id": source_id, "target_id": target_id, "relation": relation,
                "polarity": polarity, "data": data or {}}
        if edge not in self.edges_data:
            self.edges_data.append(edge)
        return deepcopy(edge)


def seed(store, kind, data=None):
    return store.put(kind, data or {})


class DecisionServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.service = DecisionService(self.store)

    def decision_payload(self):
        return {"question": "Choose a pilot", "owner": "human-1",
                "options": ["pilot A", "pilot B"], "values": ["safety", "time"],
                "constraints": ["budget"], "assumptions": ["staff available"],
                "evidence_ids": [], "stop_search_when": "Evidence is unlikely to change selection",
                "stakes": "moderate"}

    def test_create_and_approve_record_human_choice_only(self):
        decision = self.service.create(self.decision_payload())
        approved = self.service.approve(decision["id"], {"choice": "pilot B", "approved_by": "human-1", "reason": "best fit"})
        self.assertEqual(approved["data"]["approval"], {"choice": "pilot B", "approved_by": "human-1", "reason": "best fit"})
        self.assertNotIn("action", approved["data"])
        self.assertEqual(approved["version"], 2)
        with self.assertRaises(Conflict):
            self.service.approve(decision["id"], {"choice": "pilot A", "approved_by": "human-1"})

    def test_decision_requires_real_referenced_evidence(self):
        payload = self.decision_payload()
        payload["evidence_ids"] = ["missing"]
        with self.assertRaises(NotFound):
            self.service.create(payload)
        claim = seed(self.store, "claim")
        payload["evidence_ids"] = [claim["id"]]
        self.assertEqual(self.service.create(payload)["kind"], "decision")

    def test_voi_is_qualitative_and_never_invents_expected_utility(self):
        result = self.service.voi({"question": "Which pilot?", "investigations": [
            {"question": "Can the pilot meet the deadline?", "could_change_choice": "yes", "search_cost": "low"}
        ]})
        self.assertIsNone(result["quantified_voi"])
        self.assertIn("no calibrated probabilities", result["investigations"][0]["assessment"])


class OutcomeLabTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.lab = OutcomeLab(self.store)

    def prediction_payload(self):
        return {"statement": "The checklist will improve completion", "metric": {"name": "completed", "type": "binary"},
                "metric_type": "binary", "expected": "more completions", "direction": "positive",
                "horizon": "one month", "analysis_plan": "compare against the prespecified baseline",
                "stop_conditions": ["rights concern", "unacceptable burden"], "probability": 0.75}

    def test_prediction_is_timestamped_hashed_immutable_and_linked(self):
        hypothesis = seed(self.store, "idea")
        experiment = self.lab.experiment({"title": "Checklist pilot", "setup": "One team uses checklist",
                                         "comparator": "Matched prior workflow", "measurement": "completion rate",
                                         "stop_conditions": ["harm"], "hypothesis_id": hypothesis["id"]})
        payload = self.prediction_payload()
        payload.update(hypothesis_id=hypothesis["id"], experiment_id=experiment["id"])
        prediction = self.lab.predict(payload)
        data = prediction["data"]
        self.assertEqual(len(data["preregistration_hash"]), 64)
        self.assertTrue(data["registered_at"].endswith("Z"))
        self.assertIn((prediction["id"], hypothesis["id"], "tests_hypothesis"),
                      [(x["source_id"], x["target_id"], x["relation"]) for x in self.store.edges_data])
        with self.assertRaises(Conflict):
            self.store.put("prediction", {**data, "expected": "changed"}, record_id=prediction["id"], immutable=True)

    def test_prediction_rejects_bad_probability_and_orphan_hypothesis(self):
        payload = self.prediction_payload()
        payload["probability"] = 2
        with self.assertRaises(ValidationError):
            self.lab.predict(payload)
        payload["probability"] = 0.5
        payload["hypothesis_id"] = "missing"
        with self.assertRaises(NotFound):
            self.lab.predict(payload)

    def test_prediction_and_outcome_idempotency_survives_generated_timestamps(self):
        payload = {**self.prediction_payload(), "idempotency_key": "pred-key"}
        first = self.lab.predict(payload)
        second = self.lab.predict(payload)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["data"]["preregistration_hash"], second["data"]["preregistration_hash"])
        observation = {"prediction_id": first["id"], "observed": 1, "method": "count",
                       "limitations": ["small sample"], "idempotency_key": "out-key"}
        out1 = self.lab.observe(observation)
        out2 = self.lab.observe(observation)
        self.assertEqual(out1["id"], out2["id"])
        self.assertEqual(len(self.store.list("outcome")), 1)

    def test_real_store_explicit_outcome_timestamp_is_payload_bound(self):
        store = Store()
        try:
            lab = OutcomeLab(store)
            prediction = lab.predict(self.prediction_payload())
            registered = datetime.fromisoformat(prediction["data"]["registered_at"].replace("Z", "+00:00"))
            utc_z = registered.isoformat(timespec="microseconds").replace("+00:00", "Z")
            utc_offset = registered.isoformat(timespec="microseconds")
            payload = {"prediction_id": prediction["id"], "observed": 1, "method": "count",
                       "limitations": ["one site"], "occurred_at": utc_z, "idempotency_key": "timestamp-key"}
            first = lab.observe(payload)
            equivalent = lab.observe({**payload, "occurred_at": utc_offset})
            self.assertEqual(first["id"], equivalent["id"])
            self.assertEqual(first["data"]["occurred_at"], utc_z)

            changed_time = (registered + timedelta(microseconds=1)).isoformat()
            with self.assertRaises(Conflict):
                lab.observe({**payload, "occurred_at": changed_time})
        finally:
            store.close()

    def test_real_store_omitted_timestamp_retry_and_explicit_fields_are_bound(self):
        store = Store()
        try:
            lab = OutcomeLab(store)
            prediction = lab.predict(self.prediction_payload())
            base = {"prediction_id": prediction["id"], "observed": 1, "method": "count",
                    "limitations": ["one site"], "idempotency_key": "generated-time-key"}
            first = lab.observe(base)
            self.assertEqual(first["id"], lab.observe(dict(base))["id"])
            # A caller-supplied timestamp is an explicit field, even if its value
            # happens to equal the service-generated timestamp stored on first write.
            with self.assertRaises(Conflict):
                lab.observe({**base, "occurred_at": first["data"]["occurred_at"]})

            missing_prediction = lab.predict({**self.prediction_payload(), "statement":"missingness case"})
            missing_time = datetime.fromisoformat(missing_prediction["data"]["registered_at"].replace("Z", "+00:00"))
            absent = {"prediction_id": missing_prediction["id"], "observed": 1, "method": "count",
                      "limitations": ["one site"], "idempotency_key": "field-presence-key"}
            lab.observe({**absent, "occurred_at": missing_time.isoformat()})
            with self.assertRaises(Conflict):
                lab.observe({**absent, "occurred_at": missing_time.isoformat(), "missingness": None})
            with self.assertRaises(Conflict):
                lab.observe({**absent, "occurred_at": missing_time.isoformat(), "limitations": ["different limitation"]})
        finally:
            store.close()

    def test_outcomes_are_append_only_time_checked_and_missingness_explicit(self):
        prediction = self.lab.predict(self.prediction_payload())
        registered = datetime.fromisoformat(prediction["data"]["registered_at"].replace("Z", "+00:00"))
        old = (registered - timedelta(seconds=1)).isoformat()
        with self.assertRaises(ValidationError):
            self.lab.observe({"prediction_id": prediction["id"], "observed": 1, "method": "count", "limitations": ["small n"], "occurred_at": old})
        with self.assertRaises(ValidationError):
            self.lab.observe({"prediction_id": prediction["id"], "observed": None, "method": "count", "limitations": ["not measured"]})
        result = self.lab.observe({"prediction_id": prediction["id"], "observed": None, "missingness": "sensor unavailable",
                                  "method": "manual review", "limitations": ["no independent rater"]})
        self.assertIsNone(result["data"]["observed"])
        self.assertEqual(self.lab.learn(prediction["id"])["data"]["status"], "measurement_missing")

    def test_skill_promotion_requires_two_real_observed_prediction_contexts(self):
        store = Store()
        try:
            lab = OutcomeLab(store)
            evidence_ids = []
            for index in range(2):
                prediction = lab.predict({**self.prediction_payload(), "statement": f"Checklist prediction {index}"})
                lab.observe({"prediction_id": prediction["id"], "observed": 1,
                             "method": "predefined rubric", "limitations": ["one team"]})
                evidence_ids.append(lab.learn(prediction["id"])["id"])
            skill_data = {"title": "Checklist handoff", "trigger": "new handoff",
                          "required_authority": "human approval", "prerequisites": ["trained staff"],
                          "procedure": ["review", "confirm"], "contraindications": ["emergency"],
                          "abort_criteria": ["missing owner"]}
            unsupported = lab.skill({**skill_data, "evidence_ids": [evidence_ids[0]]})
            with self.assertRaises(ValidationError):
                lab.promote(unsupported["id"], {"evidence_sufficient": True, "evidence_reviewed_by": "reviewer",
                                                "authorized_by": "owner", "authorization": "approved"})
            skill = lab.skill({**skill_data, "evidence_ids": evidence_ids})
            with self.assertRaises(ValidationError):
                lab.promote(skill["id"], {"evidence_sufficient": True, "evidence_reviewed_by": "reviewer",
                                           "authorized_by": "owner"})
            with self.assertRaises(ValidationError):
                lab.promote(skill["id"], {"evidence_sufficient": False, "evidence_reviewed_by": "reviewer",
                                           "authorized_by": "owner", "authorization": "approved"})
            promoted = lab.promote(skill["id"], {"evidence_sufficient": True, "evidence_reviewed_by": "reviewer",
                                                 "authorized_by": "owner", "authorization": "approved for conditional use"})
            self.assertEqual(promoted["data"]["status"], "promoted_conditional")
            self.assertFalse(promoted["data"]["authorization"]["executable"])
        finally:
            store.close()

    def test_real_store_learning_workflow_string_limitations_retries_and_links(self):
        store = Store()
        try:
            lab = OutcomeLab(store)
            prediction_payload = {**self.prediction_payload(), "idempotency_key": "real-prediction"}
            prediction = lab.predict(prediction_payload)
            retry = lab.predict(prediction_payload)
            self.assertEqual(prediction["id"], retry["id"])
            self.assertEqual(prediction["data"]["preregistration_hash"], retry["data"]["preregistration_hash"])
            original = deepcopy(prediction["data"])
            with self.assertRaises(Conflict):
                store.put("prediction", {**original, "expected": "edited"}, record_id=prediction["id"],
                          expected_version=prediction["version"])

            registered = datetime.fromisoformat(prediction["data"]["registered_at"].replace("Z", "+00:00"))
            past_but_after_registration = (registered + timedelta(microseconds=1)).isoformat()
            outcome_payload = {"prediction_id": prediction["id"], "observed": "completion improved",
                               "method": "operator notes", "limitations": "Single team; unblinded measure.",
                               "occurred_at": past_but_after_registration, "idempotency_key": "real-outcome"}
            outcome = lab.observe(outcome_payload)
            self.assertEqual(outcome["data"]["limitations"], ["Single team; unblinded measure."])
            self.assertEqual(outcome["id"], lab.observe(outcome_payload)["id"])
            self.assertEqual(lab.learn(prediction["id"])["data"]["causal_assessment"].startswith("not established"), True)
            edges_before = len(store.edges())
            learned = lab.learn(prediction["id"])
            self.assertEqual(learned["version"], 1)
            self.assertEqual(len(store.edges()), edges_before)

            with self.assertRaises(ValidationError):
                lab.observe({"prediction_id": prediction["id"], "observed": 0, "method": "count",
                             "limitations": "selection bias", "occurred_at": "2026-11-03T12:00:00"})
            future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            with self.assertRaises(ValidationError):
                lab.observe({"prediction_id": prediction["id"], "observed": 0, "method": "count",
                             "limitations": "selection bias", "occurred_at": future})
            self.assertTrue(store.verify_ledger()["valid"])
        finally:
            store.close()

    def test_learning_compares_without_claiming_causality_and_brier_only_when_valid(self):
        prediction = self.lab.predict(self.prediction_payload())
        self.lab.observe({"prediction_id": prediction["id"], "observed": 1, "method": "predefined rubric",
                          "limitations": ["observational", "selection bias possible"]})
        learning = self.lab.learn(prediction["id"])
        self.assertEqual(learning["data"]["brier_score"], 0.0625)
        self.assertIn("not established", learning["data"]["causal_assessment"])
        self.assertEqual(len(learning["data"]["outcome_ids"]), 1)
        self.assertEqual(len(self.store.list("learning")), 1)
        self.lab.observe({"prediction_id": prediction["id"], "observed": 0, "method": "replication",
                          "limitations": ["single site"]})
        updated = self.lab.learn(prediction["id"])
        self.assertEqual(len(updated["data"]["outcome_ids"]), 2)
        self.assertNotIn("brier_score", updated["data"])
        self.assertEqual(len(self.store.list("learning")), 1)

    def test_skill_requires_conditional_details_and_two_promotion_gates(self):
        outcome = seed(self.store, "outcome", {"observed": "worked once"})
        payload = {"title": "Use the checklist", "trigger": "new handoff", "required_authority": "human approval",
                   "prerequisites": ["trained staff"], "procedure": ["review", "confirm"],
                   "contraindications": ["emergency"], "evidence_ids": [outcome["id"]], "abort_criteria": ["missing owner"]}
        skill = self.lab.skill(payload)
        with self.assertRaises(ValidationError):
            self.lab.promote(skill["id"], {"evidence_sufficient": True, "authorized_by": "owner", "authorization": "ok"})
        with self.assertRaises(ValidationError):
            self.lab.promote(skill["id"], {"evidence_sufficient": False, "evidence_reviewed_by": "reviewer", "authorized_by": "owner", "authorization": "ok"})


if __name__ == "__main__":
    unittest.main()
