"""Source-scoped theory and mechanism compilation.

This module deliberately treats provider output as a proposal.  It never turns a
source's claim into a tested finding or implies that an offline mechanism was
endorsed by its source.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .errors import NotFound, PermissionDenied, ValidationError
from .ports import ProposalProvider, StorePort


_STOP = {"the", "and", "for", "with", "from", "that", "this", "into", "when",
         "where", "which", "what", "their", "there", "then", "than", "are",
         "was", "were", "have", "has", "will", "can", "may", "might", "not",
         "use", "using", "used", "through", "over", "under", "between"}


def _words(value: Any) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", str(value or "").lower())
            if len(w) > 2 and w not in _STOP}


def _list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _data(record: dict) -> dict:
    return record.get("data", record)


def _source_status(source: dict) -> tuple[bool, str]:
    data = _data(source)
    rights = data.get("rights") or {}
    if not isinstance(rights, dict) or rights.get("allowed") is not True:
        return False, "source rights are missing or not affirmatively allowed"
    if (data.get("poisoned") is True or data.get("quarantined") is True
            or data.get("security_status") in {"poisoned", "quarantined", "denied"}
            or str(data.get("status", "")).upper() in {"BLOCKED", "QUARANTINED", "DELETED", "EXPIRED"}
            or data.get("expired") is True):
        return False, "source is blocked, expired, denied, or quarantined"
    expires_at = rights.get("expires_at") or data.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                return False, "source permission has expired"
        except ValueError:
            return False, "source expiry metadata is invalid"
    return True, "source permitted for local synthesis"


def _source_is_usable(source: dict) -> bool:
    return _source_status(source)[0]


def _source_allows_model(source: dict) -> bool:
    rights = _data(source).get("rights") or {}
    return _source_is_usable(source) and rights.get("allow_model") is True


def _claim_context(store: StorePort, claim_id: str) -> tuple[dict, dict]:
    claim = store.get(claim_id)
    cd = _data(claim)
    if claim.get("kind") not in (None, "claim"):
        raise ValidationError(f"{claim_id} is not a claim")
    sid = cd.get("source_id")
    if not sid:
        raise ValidationError(f"claim {claim_id} has no source_id")
    source = store.get(sid)
    if source.get("kind") not in (None, "source"):
        raise ValidationError(f"claim {claim_id} ancestry is not a source")
    usable, reason = _source_status(source)
    if not usable:
        raise PermissionDenied(f"claim {claim_id} descends from an unusable source: {reason}")
    if cd.get("poisoned") or cd.get("security_status") in {"poisoned", "quarantined", "denied"}:
        raise PermissionDenied(f"claim {claim_id} is quarantined")
    for span_id in _list(cd.get("span_ids")):
        span = store.get(str(span_id))
        sd = _data(span)
        if span.get("kind") != "span" or sd.get("source_id") != sid:
            raise ValidationError(f"claim {claim_id} has an invalid span_ids reference")
    return claim, source


def _provider_call_for_sources(provider: ProposalProvider | None, operation: str,
                               payload: dict, sources: list[dict], *,
                               user_opt_in: bool = False) -> dict:
    # Source grants do not authorize disclosure of user-entered synthesis context.
    # Both the caller's explicit opt-in and every source ancestor are required.
    if (provider is None or user_opt_in is not True
            or any(not _source_allows_model(source) for source in sources)):
        return {}
    return _provider_call(provider, operation, payload)


def _claim_source(store: StorePort, claim_id: str) -> dict:
    return _claim_context(store, claim_id)[1]


def _theory_sources(store: StorePort, theory: dict, seen: set[str] | None = None) -> list[dict]:
    seen = seen or set()
    if theory["id"] in seen:
        raise ValidationError("cyclic theory ancestry")
    seen.add(theory["id"])
    data = _data(theory)
    sources = []
    for cid in _list(data.get("claim_ids")):
        sources.append(_claim_source(store, str(cid)))
    source_refs = _list(data.get("source_ids")) + _list(data.get("source_id"))
    for sid in source_refs:
        source = store.get(str(sid))
        if source.get("kind") != "source" or not _source_is_usable(source):
            raise PermissionDenied(f"theory {theory['id']} has an invalid source_ids reference")
        sources.append(source)
    return _unique_sources(sources)


def _unique_sources(sources: list[dict]) -> list[dict]:
    return list({source["id"]: source for source in sources}.values())


def _source_family_summary(sources: list[dict]) -> tuple[dict[str, list[str]], int]:
    """Report asserted family labels while conservatively estimating distinct origins."""
    families: dict[str, list[str]] = {}
    parents: dict[str, str] = {}

    def find(node: str) -> str:
        parents.setdefault(node, node)
        if parents[node] != node:
            parents[node] = find(parents[node])
        return parents[node]

    def union(left: str, right: str) -> None:
        lroot, rroot = find(left), find(right)
        if lroot != rroot:
            parents[rroot] = lroot

    content_nodes: dict[str, str] = {}
    unknown_node = "unknown-origin"
    for source in sources:
        data = _data(source)
        asserted = data.get("source_family")
        asserted = str(asserted).strip() if asserted is not None else ""
        is_hash_family = asserted.lower().startswith("content:")
        content_hash = data.get("content_hash")
        content_hash = str(content_hash).strip().lower() if content_hash else ""
        if asserted and not is_hash_family:
            family = asserted
            origin_node = f"family:{family}"
        else:
            family = asserted or (f"content:{content_hash}" if content_hash else "unknown-origin")
            origin_node = unknown_node
        families.setdefault(family, []).append(source["id"])
        find(origin_node)
        if content_hash:
            content_node = content_nodes.setdefault(content_hash, f"content-hash:{content_hash}")
            union(origin_node, content_node)

    # Count connected provenance groups. Distinct labels remain asserted groups;
    # identical immutable content joins labels, and unknown/hash-only sources form
    # one conservative group regardless of their content-addressed dedup keys.
    independent_count = len({find(node) for node in parents})
    return families, independent_count


def _mechanism_sources(store: StorePort, mechanism: dict,
                       seen: set[str] | None = None) -> list[dict]:
    """Resolve and validate every source ancestor of a mechanism graph node."""
    if mechanism.get("kind") != "mechanism":
        raise ValidationError("mechanism ancestry must reference mechanisms")
    seen = seen or set()
    if mechanism["id"] in seen:
        raise ValidationError("cyclic mechanism ancestry")
    seen.add(mechanism["id"])
    data = _data(mechanism)
    if data.get("poisoned") or data.get("security_status") in {"poisoned", "quarantined", "denied"}:
        raise PermissionDenied("mechanism ancestry is quarantined")
    sources = []
    for claim_id in _list(data.get("claim_ids")):
        sources.append(_claim_source(store, str(claim_id)))
    for theory_id in _list(data.get("theory_id")):
        theory = store.get(str(theory_id))
        if theory.get("kind") != "theory":
            raise ValidationError("mechanism theory_id must reference a theory")
        sources.extend(_theory_sources(store, theory))
    for parent_id in _list(data.get("source_mechanism_ids")):
        parent = store.get(str(parent_id))
        sources.extend(_mechanism_sources(store, parent, seen))
    for source_id in _list(data.get("source_ids")) + _list(data.get("source_id")):
        source = store.get(str(source_id))
        if source.get("kind") != "source" or not _source_is_usable(source):
            raise PermissionDenied("mechanism source reference is missing, expired, or not permitted")
        sources.append(source)
    seen.remove(mechanism["id"])
    return _unique_sources(sources)


def _provider_call(provider: ProposalProvider | None, operation: str, payload: dict) -> dict:
    if provider is None:
        return {}
    result = provider.complete(operation, payload)
    if not isinstance(result, dict):
        raise ValidationError(f"provider {operation} must return a structured object")
    return result


class TheoryEngine:
    def __init__(self, store: StorePort, provider: ProposalProvider | None = None):
        self.store, self.provider = store, provider

    def build(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("theory payload must be an object")
        claim_ids = list(dict.fromkeys(str(x) for x in _list(payload.get("claim_ids"))))
        if not claim_ids:
            raise ValidationError("theory requires at least one claim_id")
        claims, sources = [], {}
        for cid in claim_ids:
            claim, source = _claim_context(self.store, cid)
            claims.append(claim)
            sources[source["id"]] = source
        user_opt_in = payload.get("allow_model", False)
        if not isinstance(user_opt_in, bool):
            raise ValidationError("allow_model must be a boolean")
        source_ids = sorted(sources)
        provider_payload = {"allow_model": user_opt_in, "claim_ids": claim_ids,
                            "source_ids": source_ids,
                            "source_claims": [{"id": c["id"], "data": _data(c)} for c in claims],
                            "title": payload.get("title"), "scope": payload.get("scope", []),
                            "explanation": payload.get("explanation", "")}
        proposal = _provider_call_for_sources(self.provider, "theory.build", provider_payload,
                                              list(sources.values()), user_opt_in=user_opt_in)
        # Provider may propose interpretation, but cannot add ancestry or source facts.
        allowed = {"explanation", "scope", "counterexamples", "predictions",
                   "alternatives", "preconditions", "failure_conditions", "open_questions",
                   "generalization", "mechanism", "title"}
        proposed = {k: v for k, v in proposal.items() if k in allowed}
        title = _text(payload.get("title") or proposed.get("title"))
        if not title:
            raise ValidationError("theory title is required")
        scope = payload.get("scope", proposed.get("scope", []))
        draft_status = payload.get("draft_status")
        if not _list(scope) or not any(_text(value) for value in _list(scope)):
            if draft_status != "unresolved_draft":
                raise ValidationError("theory requires a nonempty scope or draft_status='unresolved_draft'")
        evidence_for = _list(payload.get("evidence_for"))
        evidence_against = _list(payload.get("evidence_against"))
        # Every cited evidence item must be one of the eligible source claims.
        for item in evidence_for + evidence_against:
            cid = item.get("claim_id") if isinstance(item, dict) else item
            if cid not in claim_ids:
                raise ValidationError("theory evidence must cite an eligible claim_id")
        families, independent_family_count = _source_family_summary(list(sources.values()))
        data = {
            "title": title,
            "claim_ids": claim_ids,
            "scope": scope,
            "draft_status": draft_status or "scoped_candidate",
            "explanation": proposed.get("explanation", payload.get("explanation", "")),
            "counterexamples": proposed.get("counterexamples", payload.get("counterexamples", [])),
            "predictions": proposed.get("predictions", payload.get("predictions", [])),
            "evidence_for": evidence_for,
            "evidence_against": evidence_against,
            "evidence_interpretation": "source-claim orientation only; not independently verified support",
            "source_families": families,
            "source_family_count": len(families),
            "independent_source_family_count": independent_family_count,
            "independence_status": "asserted_family_labels_unverified; unknown_or_hash_only_sources_grouped_conservatively; identical_content_hashes_collapsed",
            "alternatives": proposed.get("alternatives", payload.get("alternatives", [])),
            "preconditions": proposed.get("preconditions", payload.get("preconditions", [])),
            "failure_conditions": proposed.get("failure_conditions", payload.get("failure_conditions", [])),
            "open_questions": proposed.get("open_questions", payload.get("open_questions", [])),
            "epistemic_type": "INTERPRETATION",
            "tested_status": "untested_hypothesis",
            "causal_status": "not_established",
            "provider_proposal": bool(proposal),
        }
        record = self.store.put("theory", data, idempotency_key=payload.get("idempotency_key"))
        for item in evidence_for:
            cid = item.get("claim_id") if isinstance(item, dict) else item
            self.store.link(record["id"], cid, "SUPPORTS", polarity="positive")
        for item in evidence_against:
            cid = item.get("claim_id") if isinstance(item, dict) else item
            self.store.link(record["id"], cid, "CONTRADICTS", polarity="negative")
        for cid in claim_ids:
            if not any((item.get("claim_id") if isinstance(item, dict) else item) == cid
                       for item in evidence_for + evidence_against):
                self.store.link(record["id"], cid, "DEPENDS_ON", polarity="neutral")
        return record

    def mechanism(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("mechanism payload must be an object")
        claim_ids = list(dict.fromkeys(str(x) for x in _list(payload.get("claim_ids"))))
        user_opt_in = payload.get("allow_model", False)
        if not isinstance(user_opt_in, bool):
            raise ValidationError("allow_model must be a boolean")
        for cid in claim_ids:
            _claim_context(self.store, cid)
        theory_id = payload.get("theory_id")
        source_mechanism_ids = list(dict.fromkeys(str(x) for x in _list(payload.get("source_mechanism_ids"))))
        explicit_source_ids = list(dict.fromkeys(str(x) for x in
            (_list(payload.get("source_ids")) + _list(payload.get("source_id")))))
        ancestry_sources = []
        if theory_id:
            theory = self.store.get(str(theory_id))
            if theory.get("kind") != "theory":
                raise ValidationError("theory_id must identify a theory")
            ancestry_sources.extend(_theory_sources(self.store, theory))
        for parent_id in source_mechanism_ids:
            parent = self.store.get(parent_id)
            ancestry_sources.extend(_mechanism_sources(self.store, parent))
        ancestry_sources.extend(_claim_source(self.store, cid) for cid in claim_ids)
        for source_id in explicit_source_ids:
            source = self.store.get(source_id)
            if source.get("kind") != "source" or not _source_is_usable(source):
                raise PermissionDenied("mechanism source_ids must reference permitted source records")
            ancestry_sources.append(source)
        ancestry_sources = _unique_sources(ancestry_sources)
        provider_payload = {"allow_model": user_opt_in, "claim_ids": claim_ids,
            "source_ids": sorted(source["id"] for source in ancestry_sources),
            "theory_id": theory_id, "source_mechanism_ids": source_mechanism_ids,
            "title": payload.get("title"), "problem_state": payload.get("problem_state", ""),
            "intervention": payload.get("intervention", ""), "effects": payload.get("effects", []),
            "boundary_conditions": payload.get("boundary_conditions", []),
            "contraindications": payload.get("contraindications", []),
            "functional_signature": payload.get("functional_signature", []),
            "structural_signature": payload.get("structural_signature", []),
            "source_domain": payload.get("source_domain", "")}
        proposal = _provider_call_for_sources(self.provider, "theory.mechanism", provider_payload,
                                              ancestry_sources, user_opt_in=user_opt_in)
        fields = ("title", "problem_state", "intervention", "effects", "boundary_conditions",
                  "contraindications", "functional_signature", "structural_signature", "source_domain")
        data = {key: proposal.get(key, payload.get(key)) for key in fields}
        if not _text(data.get("title")):
            raise ValidationError("mechanism title is required")
        for key in ("problem_state", "intervention", "effects", "boundary_conditions",
                    "contraindications", "functional_signature", "structural_signature", "source_domain"):
            if data[key] is None:
                data[key] = [] if key not in {"problem_state", "intervention", "source_domain"} else ""
        scope = payload.get("scope", data.get("boundary_conditions", []))
        draft_status = payload.get("draft_status")
        if not _list(scope) or not any(_text(value) for value in _list(scope)):
            if draft_status != "unresolved_draft":
                raise ValidationError("mechanism requires nonempty scope/boundary_conditions or draft_status='unresolved_draft'")
        data.update({"theory_id": theory_id, "claim_ids": claim_ids,
                     "source_mechanism_ids": source_mechanism_ids,
                     "source_ids": explicit_source_ids,
                     "scope": scope, "draft_status": draft_status or "scoped_candidate",
                     # The mechanism is an analyst/provider synthesis even when it
                     # cites claims. The citations preserve ancestry; they do not
                     # turn the synthesis into the source's own statement.
                     "epistemic_type": "TRANSFER_HYPOTHESIS",
                     "tested_status": "untested_hypothesis",
                     "causal_status": "not_established",
                     "source_endorsement": "none_claimed",
                     "provider_proposal": bool(proposal)})
        record = self.store.put("mechanism", data, idempotency_key=payload.get("idempotency_key"))
        for cid in claim_ids:
            self.store.link(record["id"], cid, "DEPENDS_ON", polarity="neutral")
        if theory_id:
            self.store.link(record["id"], str(theory_id), "DEPENDS_ON", polarity="neutral")
        for parent_id in source_mechanism_ids:
            self.store.link(record["id"], parent_id, "DEPENDS_ON", polarity="neutral")
        for source_id in explicit_source_ids:
            self.store.link(record["id"], source_id, "DEPENDS_ON", polarity="neutral")
        return record
