"""Source-faithful evidence analysis and human review."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from typing import Any

from .errors import ValidationError
from .ports import ProposalProvider, StorePort


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rights_expired(rights: dict[str, Any]) -> bool:
    value = rights.get("expires_at")
    if value is None:
        return False
    if not isinstance(value, str):
        return True
    try:
        expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    if expiry.tzinfo is None:
        return True
    return expiry <= datetime.now(timezone.utc)


class EvidenceService:
    def __init__(self, store: StorePort, provider: ProposalProvider | None = None):
        self.store = store
        self.provider = provider

    def analyze(self, source_id: str) -> dict[str, Any]:
        source = self.store.get(source_id)
        if source.get("kind") != "source":
            raise ValidationError("record is not a source")
        source_data = source["data"]
        spans = sorted(
            (r for r in self.store.list("span") if r.get("data", {}).get("source_id") == source_id),
            key=lambda r: (r["data"].get("start_char", 0), r["id"]),
        )
        # Deterministic analysis key makes repeat analysis return the same records.
        analysis_key = f"evidence-analysis:{source_id}:v1"
        warnings: list[str] = []
        rights = source_data.get("rights", {})
        if not isinstance(rights, dict) or rights.get("allowed") is not True or _rights_expired(rights):
            reason = "source rights have expired" if isinstance(rights, dict) and _rights_expired(rights) else "source rights do not permit analysis"
            return self._blocked_result(reason)
        if source_data.get("status") in {"BLOCKED", "EXPIRED"}:
            return self._blocked_result(source_data.get("status_reason") or "source is not accessible")
        original = source_data.get("original_text", source_data.get("text", ""))
        if "text" in source_data and source_data.get("text") != original:
            return self._blocked_result("source text alias does not match the immutable original")
        if not spans:
            return self._blocked_result("source has no captured spans; unavailable content was not inferred")
        invalid_spans = [s["id"] for s in spans if not self.verify_span(s["id"])["verified"]]
        if invalid_spans:
            return self._blocked_result("source spans failed independent verification: " + ", ".join(invalid_spans))
        existing_records = {
            kind: {r.get("data", {}).get("analysis_item_key"): r
                   for r in self.store.list(kind)
                   if r.get("data", {}).get("analysis_key") == analysis_key}
            for kind in ("claim", "argument", "interpretation")
        }
        existing_edges = self.store.edges()
        edge_keys = {(e.get("source_id"), e.get("target_id"), e.get("relation")) for e in existing_edges}

        plan_key = f"evidence-plan:{source_id}:v2"
        plan_records = self.store.list("assessment")
        prior_plan = next((r for r in plan_records
                           if r.get("data", {}).get("plan_key") == plan_key
                           and r.get("data", {}).get("source_id") == source_id
                           and r.get("data", {}).get("analysis_key") == analysis_key), None)
        if prior_plan is None:
            proposals: dict[str, Any] | None = None
            plan_warnings: list[str] = []
            legacy = next((r for r in plan_records
                           if r.get("data", {}).get("plan_key") == f"evidence-plan:{source_id}:v1"
                           and r.get("data", {}).get("analysis_key") == analysis_key
                           and r.get("data", {}).get("source_id") in (None, source_id)), None)
            if legacy is not None:
                legacy_proposals = legacy.get("data", {}).get("proposals")
                if legacy_proposals is not None:
                    try:
                        proposals = self._validate_proposals(legacy_proposals, spans)
                    except ValidationError:
                        plan_warnings.append("legacy provider plan failed current source-span validation and was discarded")
                plan_warnings.extend(legacy.get("data", {}).get("warnings", []))
            elif self.provider is not None and rights.get("allow_model", False) is True:
                try:
                    proposed = self.provider.complete("evidence.propose", {
                        "source_id": source_id,
                        "source_title": source_data.get("title"),
                        "spans": [{"id": s["id"], "text": s["data"]["text"]} for s in spans],
                        "schema": "evidence-proposals-v1",
                    })
                    proposals = self._validate_proposals(proposed, spans)
                except Exception as exc:
                    # Provider output is untrusted. Malformed output is discarded as a
                    # whole and cannot make records, instructions, or permissions.
                    plan_warnings.append(f"provider proposals rejected: {type(exc).__name__}")
            elif self.provider is not None and legacy is None:
                plan_warnings.append("provider skipped because rights metadata does not include explicit model-sharing consent")
            prior_plan = self.store.put("assessment", {
                "plan_key": plan_key, "analysis_key": analysis_key,
                "source_id": source_id, "source_refs": [source_id],
                "analysis_kind": "evidence_analysis_plan",
                "mode": "provider_proposal" if proposals is not None else "offline_exact_span",
                "proposals": proposals, "warnings": plan_warnings,
            }, immutable=True, idempotency_key=plan_key)
        plan_edges = self.store.edges(prior_plan["id"])
        if not any(e.get("source_id") == prior_plan["id"] and e.get("target_id") == source_id
                   and e.get("relation") == "DEPENDS_ON" for e in plan_edges):
            self.store.link(prior_plan["id"], source_id, "DEPENDS_ON",
                            data={"role": "source_for_evidence_analysis"})
        proposals = prior_plan["data"].get("proposals")
        warnings.extend(prior_plan["data"].get("warnings", []))

        claims: list[dict[str, Any]] = []
        arguments: list[dict[str, Any]] = []
        interpretations: list[dict[str, Any]] = []
        if proposals is None:
            for span in spans:
                text = span["data"]["text"]
                item_key = f"claim:{span['id']}"
                if item_key in existing_records["claim"]:
                    claims.append(existing_records["claim"][item_key])
                    continue
                # Exact source wording is retained. This is an attributed utterance,
                # not a finding that the proposition is true.
                qualifiers = self._qualifiers(text)
                claim = self.store.put("claim", {
                    "text": text,
                    "quote": text,
                    "source_id": source_id,
                    "span_ids": [span["id"]],
                    "epistemic_type": "SOURCE_ATTRIBUTED_CLAIM",
                    "qualifiers": qualifiers,
                    "speaker": span["data"].get("speaker"),
                    "speaker_uncertain": span["data"].get("speaker_uncertain", True),
                    "review_status": "unreviewed",
                    "analysis_mode": "offline_exact_span",
                    "analysis_key": analysis_key,
                    "analysis_item_key": item_key,
                }, idempotency_key=f"{analysis_key}:{item_key}")
                if (span["id"], claim["id"], "ATTRIBUTES_TO") not in edge_keys:
                    self.store.link(span["id"], claim["id"], "ATTRIBUTES_TO", data={"quote": text})
                claims.append(claim)
            warnings.append("offline extraction preserves exact spans as unreviewed attributed claims; it does not establish empirical truth")
        else:
            warnings.append("provider output is a proposal; source anchoring was checked, but meaning and argument quality remain unreviewed")
            for idx, item in enumerate(proposals["claims"]):
                item_key = f"claim:{idx}"
                if item_key in existing_records["claim"]:
                    claims.append(existing_records["claim"][item_key])
                    continue
                exact_source_wording = item["text"] == item["quote"]
                claim = self.store.put("claim", {
                    "text": item["text"], "quote": item["quote"],
                    "source_id": source_id, "span_ids": item["span_ids"],
                    "epistemic_type": "SOURCE_ATTRIBUTED_CLAIM" if exact_source_wording else "INTERPRETATION",
                    "proposal_type": "exact_quote" if exact_source_wording else "unverified_paraphrase",
                    "qualifiers": item["qualifiers"],
                    # Exact quotation anchoring verifies only the words, not who
                    # said them. Provider-suggested identity is kept separate
                    # from the canonical speaker field until a human/source
                    # annotation establishes attribution.
                    "speaker": None,
                    "speaker_suggestion": item["speaker"],
                    "speaker_uncertain": True,
                    "speaker_attribution_status": "unverified_model_suggestion" if item["speaker"] else "unknown",
                    "review_status": "unreviewed", "analysis_mode": "provider_proposal",
                    "analysis_key": analysis_key, "analysis_item_key": item_key,
                }, idempotency_key=f"{analysis_key}:{item_key}")
                for span_id in item["span_ids"]:
                    relation = "ATTRIBUTES_TO" if exact_source_wording else "INTERPRETS"
                    if (span_id, claim["id"], relation) not in edge_keys:
                        self.store.link(span_id, claim["id"], relation, data={"quote": item["quote"]})
                claims.append(claim)
            for idx, item in enumerate(proposals["arguments"]):
                item_key = f"argument:{idx}"
                if item_key in existing_records["argument"]:
                    arguments.append(existing_records["argument"][item_key])
                    continue
                argument = self.store.put("argument", {
                    **item, "source_id": source_id,
                    "claim_ids": [c["id"] for c in claims if c["data"]["text"] == item["claim"]],
                    "epistemic_type": "INTERPRETATION", "review_status": "unreviewed",
                    "analysis_key": analysis_key, "analysis_item_key": item_key,
                }, idempotency_key=f"{analysis_key}:{item_key}")
                arguments.append(argument)
            for idx, item in enumerate(proposals["interpretations"]):
                item_key = f"interpretation:{idx}"
                if item_key in existing_records["interpretation"]:
                    interpretations.append(existing_records["interpretation"][item_key])
                    continue
                interpretation = self.store.put("interpretation", {
                    **item, "source_id": source_id, "epistemic_type": "INTERPRETATION",
                    "review_status": "unreviewed", "analysis_key": analysis_key,
                    "analysis_item_key": item_key,
                }, idempotency_key=f"{analysis_key}:{item_key}")
                interpretations.append(interpretation)
        return {"claims": claims, "arguments": arguments,
                "interpretations": interpretations, "warnings": warnings,
                "analysis_status": "completed_with_warnings" if warnings else "completed"}

    @staticmethod
    def _blocked_result(warning: str) -> dict[str, Any]:
        return {"claims": [], "arguments": [], "interpretations": [],
                "warnings": [warning], "analysis_status": "blocked"}

    @staticmethod
    def _qualifiers(text: str) -> list[str]:
        lower = text.casefold()
        markers = ("may", "might", "could", "perhaps", "possibly", "often", "sometimes",
                   "usually", "not always", "in some cases", "seems", "apparently", "allegedly")
        return [marker for marker in markers if marker in lower]

    def _validate_proposals(self, response: Any, spans: list[dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(response, dict) or set(response) != {"claims", "arguments", "interpretations"}:
            raise ValidationError("proposal response has an invalid schema")
        if any(not isinstance(response[k], list) for k in response):
            raise ValidationError("proposal collections must be lists")
        span_by_id = {s["id"]: s["data"]["text"] for s in spans}
        safe: dict[str, Any] = {"claims": [], "arguments": [], "interpretations": []}
        for item in response["claims"]:
            required = {"text", "quote", "span_ids", "qualifiers", "speaker"}
            if not isinstance(item, dict) or set(item) != required:
                raise ValidationError("claim proposal has an invalid schema")
            if not all(isinstance(item[k], str) for k in ("text", "quote")) or not item["text"].strip() or not item["quote"]:
                raise ValidationError("claim text and quote must be non-empty strings")
            ids = item["span_ids"]
            if not isinstance(ids, list) or not ids or any(i not in span_by_id for i in ids):
                raise ValidationError("claim proposal cites an unknown span")
            if not any(item["quote"] in span_by_id[i] for i in ids):
                raise ValidationError("claim quotation is not an exact source substring")
            if not isinstance(item["qualifiers"], list) or any(not isinstance(q, str) for q in item["qualifiers"]):
                raise ValidationError("claim qualifiers must be strings")
            if item["speaker"] is not None and not isinstance(item["speaker"], str):
                raise ValidationError("speaker must be a string or null")
            safe["claims"].append(deepcopy(item))

        for item in response["arguments"]:
            fields = {"claim", "grounds", "warrant", "backing", "qualifier", "rebuttal", "span_ids"}
            if not isinstance(item, dict) or set(item) != fields:
                raise ValidationError("argument proposal has an invalid Toulmin schema")
            if not all(isinstance(item[k], str) for k in fields - {"span_ids"}):
                raise ValidationError("Toulmin fields must be strings")
            if not isinstance(item["span_ids"], list) or not item["span_ids"] or any(i not in span_by_id for i in item["span_ids"]):
                raise ValidationError("argument cites an unknown span")
            # A proposal must have at least one exact quote supplied as a claim.
            if not any(c["quote"] in "\n".join(span_by_id[i] for i in item["span_ids"]) for c in safe["claims"]):
                raise ValidationError("argument has no validated source quote")
            safe["arguments"].append(deepcopy(item))

        for item in response["interpretations"]:
            fields = {"reading", "evidence_for", "evidence_against", "span_ids", "label"}
            if not isinstance(item, dict) or set(item) != fields:
                raise ValidationError("interpretation proposal has an invalid schema")
            if not all(isinstance(item[k], str) for k in ("reading", "evidence_for", "evidence_against", "label")):
                raise ValidationError("interpretation fields must be strings")
            if item["label"] not in {"alternative_interpretation", "dissenting_interpretation", "uncertain_interpretation"}:
                raise ValidationError("interpretation label is not allowed")
            if not isinstance(item["span_ids"], list) or not item["span_ids"] or any(i not in span_by_id for i in item["span_ids"]):
                raise ValidationError("interpretation cites an unknown span")
            safe["interpretations"].append(deepcopy(item))
        return safe

    def review(self, claim_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValidationError("review payload must be an object")
        claim = self.store.get(claim_id)
        if claim["kind"] != "claim":
            raise ValidationError("record is not a claim")
        decision = payload.get("status")
        if decision not in {"accepted", "corrected", "disputed", "rejected"}:
            raise ValidationError("status must be accepted, corrected, disputed, or rejected")
        reviewer = payload.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValidationError("reviewer is required")
        note = payload.get("note", "")
        if not isinstance(note, str):
            raise ValidationError("note must be a string")
        correction = payload.get("correction")
        if decision == "corrected" and (not isinstance(correction, str) or not correction.strip()):
            raise ValidationError("a non-empty correction is required for corrected status")
        new_data = deepcopy(claim["data"])
        prior_text = new_data.get("text")
        reviews = list(new_data.get("reviews", []))
        reviews.append({"status": decision, "reviewer": reviewer, "note": note,
                        "correction": correction, "reviewed_at": _now(),
                        "preserved_claim_text": prior_text})
        new_data["reviews"] = reviews
        new_data["review_status"] = decision
        # The original proposal text/quote remains intact; a correction is a
        # separate versioned human assertion in the review history.
        return self.store.put("claim", new_data, record_id=claim_id,
                              expected_version=claim["version"], event_type="claim_review")

    def verify_span(self, span_id: str) -> dict[str, Any]:
        span = self.store.get(span_id)
        if span["kind"] != "span":
            raise ValidationError("record is not a source span")
        data = span["data"]
        source = self.store.get(data.get("source_id", ""))
        rights = source.get("data", {}).get("rights", {})
        if (source.get("data", {}).get("status") in {"BLOCKED", "EXPIRED"}
                or not isinstance(rights, dict) or rights.get("allowed") is not True or _rights_expired(rights)):
            return {"span_id": span_id, "source_id": source["id"], "verified": False,
                    "actual_text": None, "start_char": data.get("start_char"),
                    "end_char": data.get("end_char"), "offset_unit": "unicode_codepoints",
                    "issues": ["source rights do not permit span verification"]}
        original = source["data"].get("original_text", source["data"].get("text", ""))
        if "text" in source["data"] and source["data"].get("text") != original:
            return {"span_id": span_id, "source_id": source["id"], "verified": False,
                    "actual_text": None, "start_char": data.get("start_char"),
                    "end_char": data.get("end_char"), "offset_unit": "unicode_codepoints",
                    "issues": ["source text alias does not match the immutable original"]}
        start, end = data.get("start_char"), data.get("end_char")
        issues: list[str] = []
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or end > len(original):
            issues.append("span offsets are outside the immutable source text")
            actual = None
        else:
            actual = original[start:end]
            if actual != data.get("text"):
                issues.append("span text does not equal the exact source substring")
        digest = hashlib.sha256(data.get("text", "").encode("utf-8")).hexdigest()
        if digest != data.get("content_hash"):
            issues.append("span content hash does not match span text")
        if "start_ms" in data or "end_ms" in data:
            if not isinstance(data.get("start_ms"), int) or not isinstance(data.get("end_ms"), int) or data["start_ms"] < 0 or data["end_ms"] < data["start_ms"]:
                issues.append("transcript time links are invalid")
        return {"span_id": span_id, "source_id": source["id"], "verified": not issues,
                "actual_text": actual, "start_char": start, "end_char": end,
                "offset_unit": "unicode_codepoints", "issues": issues}
