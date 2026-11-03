"""Human decision records and append-only outcome learning.

This module intentionally contains no action runner. Decisions record choices;
predictions record what was committed to before evidence arrives; outcomes and
learning records preserve the limits of what observations can establish.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

from .errors import Conflict, NotFound, ValidationError
from .ports import StorePort


_EVIDENCE_KINDS = {
    "source", "span", "claim", "argument", "interpretation", "theory",
    "mechanism", "problem", "idea", "prediction", "experiment", "outcome",
    "learning", "skill",
}
_HYPOTHESIS_KINDS = {
    "claim", "argument", "interpretation", "theory", "mechanism", "problem", "idea",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _canonical_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _required_text(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} must be a non-empty string")
    return value.strip()


def _list(data: dict, key: str, *, allow_empty: bool = True) -> list:
    value = data.get(key)
    if not isinstance(value, list) or (not allow_empty and not value):
        suffix = "" if allow_empty else " and non-empty"
        raise ValidationError(f"{key} must be a list{suffix}")
    return value


def _strings(data: dict, key: str, *, allow_empty: bool = True) -> list[str]:
    values = _list(data, key, allow_empty=allow_empty)
    if any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValidationError(f"{key} must contain only non-empty strings")
    return [v.strip() for v in values]


def _limitations(value: Any) -> list[str]:
    """Accept API-friendly free text or a structured list, storing normalized text."""
    if isinstance(value, str):
        values = [line.strip() for line in value.splitlines() if line.strip()]
        if not values:
            raise ValidationError("limitations must contain at least one meaningful limitation")
        return values
    if isinstance(value, list):
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValidationError("limitations must contain only non-empty strings")
        if not value:
            raise ValidationError("limitations must contain at least one meaningful limitation")
        return [item.strip() for item in value]
    raise ValidationError("limitations must be free text or a list of strings")


def _unique(values: list[str], key: str) -> list[str]:
    if len(set(values)) != len(values):
        raise ValidationError(f"{key} must not contain duplicates")
    return values


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _keyed_id(kind: str, key: str) -> str:
    return f"{kind}:{hashlib.sha256(key.encode('utf-8')).hexdigest()}"


def _record_data(record: dict) -> dict:
    data = record.get("data")
    return data if isinstance(data, dict) else {}


class _LearningBase:
    def __init__(self, store: StorePort):
        self.store = store

    def _ref(self, record_id: Any, allowed: set[str], field: str) -> dict:
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValidationError(f"{field} must be a non-empty record id")
        try:
            record = self.store.get(record_id)
        except NotFound:
            raise
        except Exception as exc:
            # Store implementations may expose their own not-found exception;
            # do not turn unrelated storage failures into validation failures.
            if exc.__class__.__name__ == "NotFound":
                raise
            raise
        if record.get("kind") not in allowed:
            raise ValidationError(f"{field} must reference one of: {', '.join(sorted(allowed))}")
        return record

    def _refs(self, record_ids: Any, allowed: set[str], field: str) -> list[str]:
        if not isinstance(record_ids, list):
            raise ValidationError(f"{field} must be a list of record ids")
        ids = _unique(record_ids, field)
        for record_id in ids:
            self._ref(record_id, allowed, field)
        return ids

    def _link(self, source_id: str, target_id: str, relation: str) -> None:
        self.store.link(source_id, target_id, relation)


class DecisionService(_LearningBase):
    """Create human-owned decision contracts and record human approvals."""

    def create(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("decision payload must be an object")
        data = dict(payload)
        for field in ("question", "owner", "stop_search_when"):
            data[field] = _required_text(data, field)
        data["options"] = _list(data, "options", allow_empty=False)
        if any(not isinstance(x, (str, dict)) for x in data["options"]):
            raise ValidationError("options must contain strings or option objects")
        if any((not x.strip()) if isinstance(x, str) else
               (not isinstance(x.get("label"), str) or not x["label"].strip() or
                ("id" in x and (not isinstance(x["id"], str) or not x["id"].strip())))
               for x in data["options"]):
            raise ValidationError("each option must have a non-empty label and an optional string id")
        identities = [x if isinstance(x, str) else x.get("id", x["label"]) for x in data["options"]]
        if len(set(identities)) != len(data["options"]):
            raise ValidationError("options must be unique")
        data["values"] = _list(data, "values", allow_empty=False)
        data["constraints"] = _strings(data, "constraints")
        data["assumptions"] = _strings(data, "assumptions")
        data["evidence_ids"] = self._refs(data.get("evidence_ids", []), _EVIDENCE_KINDS, "evidence_ids")
        stakes = data.get("stakes")
        if not isinstance(stakes, str) or not stakes.strip():
            raise ValidationError("stakes must be a non-empty qualitative description")
        data["stakes"] = stakes.strip()
        if "approval" in data:
            raise ValidationError("approval can only be added through approve()")
        key = data.pop("idempotency_key", None)
        if key is not None and (not isinstance(key, str) or not key.strip()):
            raise ValidationError("idempotency_key must be a non-empty string")
        return self.store.put("decision", data, idempotency_key=key)

    def approve(self, decision_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("approval payload must be an object")
        current = self.store.get(decision_id)
        if current.get("kind") != "decision":
            raise ValidationError("decision_id must reference a decision")
        data = _record_data(current)
        if data.get("approval"):
            existing = data["approval"]
            if (existing.get("choice") == payload.get("choice") and
                    existing.get("approved_by") == payload.get("approved_by") and
                    existing.get("reason", "") == (payload.get("reason") or "")):
                return current
            raise Conflict("decision already has a recorded approval")
        choice = payload.get("choice")
        options = data.get("options", [])
        choices = [o if isinstance(o, str) else o.get("id", o.get("label")) for o in options]
        labels = [o.get("label") for o in options if isinstance(o, dict)]
        if choice not in choices + labels:
            raise ValidationError("choice must match one of the decision's options")
        approved_by = _required_text(payload, "approved_by")
        approval = {"choice": choice, "approved_by": approved_by}
        if payload.get("reason") is not None:
            if not isinstance(payload["reason"], str):
                raise ValidationError("reason must be a string")
            approval["reason"] = payload["reason"].strip()
        revised = dict(data)
        revised["approval"] = approval
        # The approving human is the event principal; no action is executed.
        updated = self.store.put("decision", revised, record_id=decision_id,
                                 expected_version=current.get("version"),
                                 principal=approved_by, event_type="decision_approved",
                                 idempotency_key=payload.get("idempotency_key"))
        return updated

    def voi(self, payload: dict) -> dict:
        """Return ordinal/qualitative value-of-information considerations."""
        if not isinstance(payload, dict):
            raise ValidationError("VOI payload must be an object")
        question = _required_text(payload, "question")
        candidates = payload.get("investigations", payload.get("candidates", []))
        if not isinstance(candidates, list):
            raise ValidationError("investigations must be a list")
        results = []
        for candidate in candidates:
            if isinstance(candidate, str):
                item = {"question": candidate}
            elif isinstance(candidate, dict):
                item = candidate
            else:
                raise ValidationError("each investigation must be a string or object")
            text = _required_text(item, "question")
            factors = {
                "could_change_choice": item.get("could_change_choice", "unknown"),
                "could_reduce_consequential_risk": item.get("could_reduce_consequential_risk", "unknown"),
                "search_cost": item.get("search_cost", "unknown"),
                "delay_cost": item.get("delay_cost", "unknown"),
            }
            for name, value in factors.items():
                if not isinstance(value, str):
                    raise ValidationError(f"{name} must be a qualitative string")
            results.append({"question": text, "factors": factors,
                            "assessment": "unranked qualitative factors; no calibrated probabilities supplied"})
        return {"decision_question": question, "investigations": results,
                "policy": "prioritize investigations that may change a choice or reduce consequential risk relative to their search, review, and delay costs; otherwise consider a reversible probe or stopping", 
                "quantified_voi": None}


class OutcomeLab(_LearningBase):
    """Preregister predictions, record experiments/outcomes, and distill learning."""

    def predict(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("prediction payload must be an object")
        data = dict(payload)
        for field in ("statement", "metric", "expected", "direction", "horizon", "analysis_plan"):
            if field not in data or data[field] is None or data[field] == "":
                raise ValidationError(f"{field} is required")
        if not isinstance(data["statement"], str) or not data["statement"].strip():
            raise ValidationError("statement must be a non-empty string")
        if not isinstance(data["direction"], str) or not data["direction"].strip():
            raise ValidationError("direction must be a non-empty string")
        if not isinstance(data["analysis_plan"], str) or not data["analysis_plan"].strip():
            raise ValidationError("analysis_plan must be a non-empty string")
        data["stop_conditions"] = _strings(data, "stop_conditions", allow_empty=False)
        if "probability" in data:
            p = data["probability"]
            if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
                raise ValidationError("probability must be a finite number from 0 to 1")
        if data.get("hypothesis_id") is not None:
            self._ref(data["hypothesis_id"], _HYPOTHESIS_KINDS, "hypothesis_id")
        experiment_id = data.get("experiment_id")
        if experiment_id is not None:
            self._ref(experiment_id, {"experiment"}, "experiment_id")
        key = data.pop("idempotency_key", None)
        if key is not None and (not isinstance(key, str) or not key.strip()):
            raise ValidationError("idempotency_key must be a non-empty string")
        if key:
            stable_id = _keyed_id("prediction", key)
            try:
                existing = self.store.get(stable_id)
            except NotFound:
                existing = None
            if existing is not None:
                old_data = dict(_record_data(existing))
                old_data.pop("registered_at", None)
                old_data.pop("preregistration_hash", None)
                if old_data != data:
                    raise Conflict("idempotency key was already used for a different prediction")
                return existing
        data["registered_at"] = _now()
        data["preregistration_hash"] = _canonical_hash(data)
        record = self.store.put("prediction", data, immutable=True,
                               record_id=_keyed_id("prediction", key) if key else None,
                               idempotency_key=key)
        if data.get("hypothesis_id"):
            self._link(record["id"], data["hypothesis_id"], "tests_hypothesis")
        if experiment_id:
            self._link(record["id"], experiment_id, "registered_for")
        return record

    def experiment(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("experiment payload must be an object")
        data = dict(payload)
        for field in ("title", "setup", "measurement", "stop_conditions"):
            if field == "stop_conditions":
                data[field] = _strings(data, field, allow_empty=False)
            else:
                data[field] = _required_text(data, field)
        if "comparator" not in data or data["comparator"] is None or data["comparator"] == "":
            raise ValidationError("comparator is required; use an explicit no-comparator rationale for observational work")
        if not isinstance(data["comparator"], (str, dict)):
            raise ValidationError("comparator must be descriptive text or an object")
        if data.get("hypothesis_id") is not None:
            self._ref(data["hypothesis_id"], _HYPOTHESIS_KINDS, "hypothesis_id")
        if data.get("prediction_id") is not None:
            self._ref(data["prediction_id"], {"prediction"}, "prediction_id")
        data["created_for_testing"] = True
        key = data.pop("idempotency_key", None)
        record = self.store.put("experiment", data, idempotency_key=key)
        if data.get("hypothesis_id"):
            self._link(record["id"], data["hypothesis_id"], "tests_hypothesis")
        if data.get("prediction_id"):
            self._link(data["prediction_id"], record["id"], "uses_experiment")
        return record

    def observe(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("outcome payload must be an object")
        prediction = self._ref(payload.get("prediction_id"), {"prediction"}, "prediction_id")
        if "observed" not in payload:
            raise ValidationError("observed is required; use null with missingness details for unavailable measurements")
        method = _required_text(payload, "method")
        limitations = _limitations(payload.get("limitations"))
        missingness = payload.get("missingness")
        if payload["observed"] is None:
            if not isinstance(missingness, str) or not missingness.strip():
                raise ValidationError("missing observations require a missingness explanation")
        elif missingness is not None:
            if not isinstance(missingness, str) or not missingness.strip():
                raise ValidationError("missingness must be non-empty text when supplied")
        occurred_at_supplied = "occurred_at" in payload
        occurred_at = payload["occurred_at"] if occurred_at_supplied else _now()
        occurred_dt = _timestamp(occurred_at, "occurred_at")
        registered_dt = _timestamp(_record_data(prediction).get("registered_at"), "prediction.registered_at")
        if occurred_dt < registered_dt:
            raise ValidationError("outcome time cannot precede prediction registration")
        if occurred_dt > datetime.now(timezone.utc):
            raise ValidationError("outcome time cannot be in the future")
        data = {"prediction_id": payload["prediction_id"], "observed": payload["observed"],
                "method": method, "limitations": limitations,
                "occurred_at": _canonical_timestamp(occurred_dt)}
        if missingness is not None:
            data["missingness"] = missingness.strip()
        if payload.get("experiment_id") is not None:
            experiment = self._ref(payload["experiment_id"], {"experiment"}, "experiment_id")
            prediction_experiment_id = _record_data(prediction).get("experiment_id")
            experiment_prediction_id = _record_data(experiment).get("prediction_id")
            if prediction_experiment_id and prediction_experiment_id != experiment["id"]:
                raise ValidationError("experiment_id does not match the experiment pre-registered with this prediction")
            if experiment_prediction_id and experiment_prediction_id != prediction["id"]:
                raise ValidationError("experiment is associated with a different prediction")
            data["experiment_id"] = experiment["id"]
        key = payload.get("idempotency_key")
        if key is not None and (not isinstance(key, str) or not key.strip()):
            raise ValidationError("idempotency_key must be a non-empty string")
        stable_id = _keyed_id("outcome", key) if key else None
        if stable_id:
            # Hash the complete caller payload after canonicalizing instants. An omitted
            # occurred_at stays omitted, allowing retries despite a newly generated time;
            # an explicit timestamp remains bound to the key, timezone-equivalently.
            request_payload = {name: value for name, value in payload.items() if name != "idempotency_key"}
            if occurred_at_supplied:
                request_payload["occurred_at"] = _canonical_timestamp(occurred_dt)
            request_payload_hash = _canonical_hash(request_payload)
            data["request_payload_hash"] = request_payload_hash
            try:
                existing = self.store.get(stable_id)
            except NotFound:
                existing = None
            if existing is not None:
                old_data = dict(_record_data(existing))
                old_request_hash = old_data.pop("request_payload_hash", None)
                if old_request_hash is not None:
                    if old_request_hash != request_payload_hash:
                        raise Conflict("idempotency key was already used for a different outcome")
                else:
                    # Compatibility for records written before request hashes existed.
                    old_occurred_at = old_data.pop("occurred_at", None)
                    compared = dict(data)
                    compared.pop("request_payload_hash", None)
                    compared.pop("occurred_at", None)
                    if old_data != compared or (occurred_at_supplied and
                            _canonical_timestamp(_timestamp(old_occurred_at, "stored occurred_at")) != _canonical_timestamp(occurred_dt)):
                        raise Conflict("idempotency key was already used for a different outcome")
                return existing
        record = self.store.put("outcome", data, immutable=True, record_id=stable_id,
                                idempotency_key=key)
        self._link(record["id"], payload["prediction_id"], "observes_prediction")
        if data.get("experiment_id"):
            self._link(record["id"], data["experiment_id"], "observed_in")
        return record

    def learn(self, prediction_id: str) -> dict:
        prediction = self._ref(prediction_id, {"prediction"}, "prediction_id")
        outcomes = [r for r in self.store.list("outcome") if _record_data(r).get("prediction_id") == prediction_id]
        outcomes.sort(key=lambda r: (_record_data(r).get("occurred_at", ""), r.get("id", "")))
        p_data = _record_data(prediction)
        observed = [_record_data(r) for r in outcomes]
        known = [x for x in observed if x.get("observed") is not None]
        causal = "not established by temporal association; compare alternatives and design limitations before causal claims"
        if not outcomes:
            status = "awaiting_observation"
            conclusion = "No outcome observations are recorded."
        elif not known:
            status = "measurement_missing"
            conclusion = "Observations are missing; no prediction comparison is possible."
        else:
            status = "observed"
            conclusion = "Recorded observations are compared descriptively with the registered prediction; this is not proof of causal effect."
        result: dict[str, Any] = {
            "prediction_id": prediction_id,
            "prediction_hash": p_data.get("preregistration_hash"),
            "registered_at": p_data.get("registered_at"),
            "statement": p_data.get("statement"),
            "metric": p_data.get("metric"),
            "expected": p_data.get("expected"),
            "direction": p_data.get("direction"),
            "outcome_ids": [r["id"] for r in outcomes],
            "observations": observed,
            "status": status,
            "comparison": conclusion,
            "uncertainty": "No uncertainty interval is inferred unless the recorded measurement supplies one.",
            "causal_assessment": causal,
            "limitations": sorted({lim for item in observed for lim in item.get("limitations", [])}),
            "anecdote_caution": "A single case may inform a candidate rule but cannot establish a generally effective skill.",
        }
        metric_type = p_data.get("metric_type")
        if isinstance(p_data.get("metric"), dict):
            metric_type = p_data["metric"].get("type", metric_type)
        # Proper scoring is appropriate only for an explicitly declared binary
        # outcome and a numeric observed 0/1 value.
        if metric_type == "binary" and isinstance(p_data.get("probability"), (int, float)) and len(known) == 1:
            values = [x.get("observed") for x in known]
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) and v in (0, 1) for v in values):
                prob = float(p_data["probability"])
                result["brier_score"] = sum((prob - float(v)) ** 2 for v in values) / len(values)
                result["brier_observation_count"] = len(values)
        learning_data = result
        prior = [r for r in self.store.list("learning") if _record_data(r).get("prediction_id") == prediction_id]
        if prior:
            latest = max(prior, key=lambda r: r.get("version", 1))
            previous_data = _record_data(latest)
            if previous_data == learning_data:
                return latest
            previous_outcome_ids = set(previous_data.get("outcome_ids", []))
            record = self.store.put("learning", learning_data, record_id=latest["id"],
                                    expected_version=latest.get("version"))
        else:
            record = self.store.put("learning", learning_data)
            previous_outcome_ids = set()
            self._link(record["id"], prediction_id, "learns_from")
        for outcome in outcomes:
            if outcome["id"] not in previous_outcome_ids:
                self._link(record["id"], outcome["id"], "compares_outcome")
        return record

    def skill(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("skill payload must be an object")
        data = dict(payload)
        for field in ("title", "trigger", "required_authority"):
            data[field] = _required_text(data, field)
        for field in ("prerequisites", "procedure", "contraindications", "abort_criteria"):
            data[field] = _strings(data, field, allow_empty=False)
        data["evidence_ids"] = self._refs(data.get("evidence_ids", []), {"learning", "outcome", "experiment", "prediction", "claim", "interpretation", "theory", "mechanism"}, "evidence_ids")
        if "authorization" in data or "promoted" in data:
            raise ValidationError("skill authorization and promotion are recorded only through promote()")
        data["status"] = "candidate"
        return self.store.put("skill", data, idempotency_key=data.pop("idempotency_key", None))

    def promote(self, skill_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("promotion payload must be an object")
        current = self._ref(skill_id, {"skill"}, "skill_id")
        data = _record_data(current)
        evidence_sufficient = payload.get("evidence_sufficient")
        if not isinstance(evidence_sufficient, bool):
            raise ValidationError("evidence_sufficient must be an explicit boolean")
        if not evidence_sufficient:
            raise ValidationError("skill cannot be promoted without explicit evidence sufficiency")
        reviewer = _required_text(payload, "evidence_reviewed_by")
        evidence_ids = self._refs(data.get("evidence_ids", []), {"learning", "outcome", "experiment", "prediction", "claim", "interpretation", "theory", "mechanism"}, "evidence_ids")
        if not evidence_ids:
            raise ValidationError("skill promotion requires referenced supporting evidence")
        # The reviewer's boolean is a gate, not evidence. Promotion additionally
        # requires service-produced learning records from distinct preregistered
        # prediction contexts with linked, non-missing observations.
        learning_records = [self.store.get(rid) for rid in evidence_ids
                            if self.store.get(rid).get("kind") == "learning"]
        observed_contexts = set()
        for learning_record in learning_records:
            learning_data = _record_data(learning_record)
            prediction_id = learning_data.get("prediction_id")
            if learning_data.get("status") != "observed" or not prediction_id:
                continue
            prediction = self._ref(prediction_id, {"prediction"}, "learning.prediction_id")
            if learning_data.get("prediction_hash") != _record_data(prediction).get("preregistration_hash"):
                continue
            for outcome_id in learning_data.get("outcome_ids", []):
                outcome = self._ref(outcome_id, {"outcome"}, "learning.outcome_ids")
                outcome_data = _record_data(outcome)
                if outcome_data.get("prediction_id") == prediction_id and outcome_data.get("observed") is not None:
                    observed_contexts.add(prediction_id)
                    break
        if len(observed_contexts) < 2:
            raise ValidationError("promotion requires observed learning evidence from at least two distinct predictions")
        authority = _required_text(payload, "authorized_by")
        authorization = payload.get("authorization")
        if not isinstance(authorization, str) or not authorization.strip():
            raise ValidationError("explicit authorization text is required separately from evidence sufficiency")
        revised = dict(data)
        revised["status"] = "promoted_conditional"
        revised["evidence_review"] = {"sufficient": True, "reviewed_by": reviewer,
                                      "evidence_ids": evidence_ids, "reviewed_at": _now()}
        revised["authorization"] = {"authorized_by": authority,
                                    "authorization": authorization.strip(), "authorized_at": _now(),
                                    "executable": False}
        return self.store.put("skill", revised, record_id=skill_id,
                              expected_version=current.get("version"), principal=authority,
                              event_type="skill_promoted")
