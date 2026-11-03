"""Purpose-aware epistemic and rights gates; no action executor is provided."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .errors import NotFound, ValidationError
from .access import ancestry


class Governor:
    """Deterministic record assessment and fail-closed local authorization."""

    _GATES = {"accept_for_purpose", "new_region_research", "quarantine", "refuse"}
    _DEPENDENCY_EDGE_RELATIONS = {
        "DEPENDS_ON", "QUOTES", "INTERPRETS", "INSPIRED_BY", "BACKED_BY", "SUPPORTS",
        "ATTRIBUTES_TO", "TESTS", "PREDICTS", "OBSERVED_AS", "STRUCTURALLY_MATCHES",
        "USES_EVIDENCE", "EVIDENCE_FOR", "DERIVED_FROM",
    }
    _LOCAL_ACTIONS = {"read", "annotate", "propose", "simulate"}
    _EXTERNAL_PURPOSE_RIGHTS = {
        "export": "allow_export", "publish": "allow_export", "publication": "allow_export",
        "share": "allow_export", "sharing": "allow_export", "send": "allow_export",
        "email": "allow_export", "message": "allow_export", "upload": "allow_export",
        "model": "allow_model", "model_inference": "allow_model",
        "external": "allow_external_research", "external_research": "allow_external_research",
    }
    _EXTERNAL_PURPOSE_PREFIXES = (
        "external", "publish", "publication", "share", "sharing", "send", "email",
        "message", "upload", "write", "deploy", "purchase", "schedule", "model",
    )
    _EXTERNAL_PREFIXES = (
        "send", "publish", "delete", "execute", "purchase", "external", "write",
        "upload", "share", "email", "message", "invite", "schedule", "deploy",
    )

    def __init__(self, store):
        self.store = store

    @staticmethod
    def _references(value: Any):
        """Yield canonical record IDs from arbitrarily nested *_id and *_ids fields."""
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(key, str) and key.endswith("_id") and isinstance(item, str):
                    yield item
                elif isinstance(key, str) and key.endswith("_ids") and isinstance(item, (list, tuple, set)):
                    yield from (ref for ref in item if isinstance(ref, str))
                elif key == "source_refs" and isinstance(item, (list, tuple, set)):
                    yield from (ref for ref in item if isinstance(ref, str))
                yield from Governor._references(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from Governor._references(item)

    def _source_ancestry(self, record: dict) -> tuple[list[dict], list[str]]:
        # One traversal enforces the same canonical dependency/cycle rules for serving and assessment.
        try:
            records=ancestry(self.store,record)
            return [r for r in records if r["kind"]=="source"],[]
        except NotFound as exc:
            return [],[str(exc)]

    @staticmethod
    def _expired(rights: dict, data: dict) -> bool:
        expiry = rights.get("expires_at") or data.get("expires_at")
        if not expiry:
            return False
        if not isinstance(expiry, str):
            return True
        try:
            parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return True
            return parsed <= datetime.now(timezone.utc)
        except ValueError:
            return True

    @staticmethod
    def _family_independence(sources: list[dict]) -> dict:
        """Count only explicit families; identical originals and repeated family labels collapse."""
        parent = list(range(len(sources)))

        def root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a, b):
            ra, rb = root(a), root(b)
            if ra != rb:
                parent[rb] = ra

        families: dict[str, int] = {}
        hashes: dict[str, int] = {}
        explicit_family_indices = set()
        hash_fallback_indices = set()
        names = set()

        def explicit_family(data):
            family = data.get("source_family") if isinstance(data, dict) else None
            content_hash = data.get("content_hash") if isinstance(data, dict) else None
            if not isinstance(family, str) or not family.strip():
                return None
            # IngestService encodes its fallback family as content:<hash>. Treat
            # that provenance-free default like any other hash-only fallback.
            if (isinstance(content_hash, str) and
                    family.strip().casefold() == f"content:{content_hash}".casefold()):
                return None
            return family.strip().casefold()

        for i, source in enumerate(sources):
            data = source.get("data", {})
            family = explicit_family(data)
            content_hash = data.get("content_hash") if isinstance(data, dict) else None
            if family:
                names.add(family)
                explicit_family_indices.add(i)
                if family in families:
                    union(i, families[family])
                else:
                    families[family] = i
            elif isinstance(content_hash, str) and content_hash.strip():
                hash_fallback_indices.add(i)
            if isinstance(content_hash, str) and content_hash:
                if content_hash in hashes:
                    union(i, hashes[content_hash])
                else:
                    hashes[content_hash] = i
        explicit_roots = {root(i) for i in explicit_family_indices}
        # Identical hash-only copies are one fallback witness. Distinct hashes
        # still do not establish independent origin, so all unmatched fallback
        # records form one explicitly unknown group rather than multiple families.
        explicit_hashes = {
            source["data"].get("content_hash") for source in sources
            if isinstance(source.get("data"), dict)
            and explicit_family(source["data"])
            and isinstance(source["data"].get("content_hash"), str)
        }
        unknown_fallback = any(
            sources[i].get("data", {}).get("content_hash") not in explicit_hashes
            for i in hash_fallback_indices
        )
        return {
            "count": len(explicit_roots),
            "families": sorted(names),
            "unknown_content_hash_group": unknown_fallback,
            "witness_group_count": len(explicit_roots) + int(unknown_fallback),
            "status": ("explicit_families_and_unknown_hash_fallback" if names and unknown_fallback
                       else "explicit_families_only" if names
                       else "unknown_hash_fallback_only" if unknown_fallback
                       else "unknown"),
            "method": "explicit families count as named groups; hash-only records form at most one unknown group, so hashes deduplicate copies but do not prove independent origin",
        }

    def assess(self, record_id: str, purpose: str = "research", stakes: str = "low") -> dict:
        if not isinstance(purpose, str) or not purpose.strip():
            raise ValidationError("purpose is required")
        if stakes not in {"low", "medium", "high", "critical"}:
            raise ValidationError("stakes must be low, medium, high, or critical")
        record = self.store.get(record_id)
        data = record.get("data") or {}
        sources, missing_refs = self._source_ancestry(record)
        rights = data.get("rights") if isinstance(data, dict) else None
        reasons: list[str] = []

        provenance = data.get("provenance_status", "recorded")
        if record["kind"] == "source":
            provenance = data.get("status", provenance)
        support = data.get("semantic_support_status", data.get("review_status", "unknown"))
        empirical = data.get("empirical_evidence_status", "unknown")
        transfer = data.get("transfer_status", "not_assessed")
        uncertainty = data.get("uncertainty", "unknown")
        authorization = data.get("authorization_status", "not_applicable")

        route = None
        normalized_purpose = re.sub(r"[-\s]+", "_", purpose.strip().casefold())
        rights_flag = self._EXTERNAL_PURPOSE_RIGHTS.get(normalized_purpose)
        external_intent = normalized_purpose.startswith(self._EXTERNAL_PURPOSE_PREFIXES)
        if data.get("injection_suspected") or data.get("poisoning_suspected") or provenance == "untrusted_instruction":
            route = "quarantine"
            reasons.append("untrusted or potentially injected content requires review")

        # Check the record's own restrictions and every recursively referenced original.
        right_bearing = [(record, rights if isinstance(rights, dict) else None)]
        right_bearing.extend((source, source["data"].get("rights") if isinstance(source.get("data"), dict) else None)
                             for source in sources)
        if route is None:
            for subject, policy in right_bearing:
                subject_data = subject.get("data", {})
                is_source = subject.get("kind") == "source"
                if "rights" in subject_data and not isinstance(subject_data.get("rights"), dict):
                    route = "refuse"
                    reasons.append("rights metadata is malformed and cannot affirm permission")
                    break
                if is_source and (not isinstance(policy, dict) or policy.get("allowed") is not True):
                    route = "refuse"
                    reasons.append("a source in this record's lineage lacks affirmative permission")
                    break
                if isinstance(policy, dict) and policy.get("allowed") is False:
                    route = "refuse"
                    reasons.append("rights explicitly refuse this purpose")
                    break
                if is_source and isinstance(policy, dict) and policy.get("allowed") is not True:
                    route = "refuse"
                    reasons.append("source rights are not affirmatively permitted")
                    break
                if self._expired(policy or {}, subject_data):
                    route = "refuse"
                    reasons.append("a source or derived record in this lineage has expired")
                    break
                if is_source and subject_data.get("status", "").upper() in {"BLOCKED", "EXPIRED"}:
                    route = "refuse"
                    reasons.append("a source in this record's lineage is blocked or expired")
                    break
                if external_intent and rights_flag is None:
                    route = "refuse"
                    reasons.append("external-use purpose has no recognized rights mapping")
                    break
                if isinstance(policy, dict) and rights_flag is not None:
                    flag = rights_flag
                    if policy.get("private") is True:
                        route = "refuse"
                        reasons.append("private content cannot be used for this external purpose")
                        break
                    # Originals require affirmative rights. A derived record can add a
                    # stricter veto without having to duplicate its ancestors' grants.
                    if is_source and policy.get(flag) is not True:
                        route = "refuse"
                        reasons.append(f"source rights do not permit {normalized_purpose}")
                        break
                    if not is_source and flag in policy and policy.get(flag) is not True:
                        route = "refuse"
                        reasons.append(f"derived-record rights do not permit {normalized_purpose}")
                        break
            if route is None and missing_refs:
                route = "quarantine"
                reasons.append("record lineage includes unresolved references")

        if route is None and support in {"contradicted", "contested", "unreviewed", "unknown", None}:
            route = "new_region_research"
            reasons.append("semantic support is not resolved for this purpose")
        elif route is None and uncertainty in {"high", "unknown"}:
            route = "new_region_research"
            reasons.append("uncertainty is not resolved for this purpose")
        elif route is None and stakes in {"high", "critical"} and (
                empirical not in {"tested", "supported", "bounded"} or
                transfer in {"untested", "unknown", "not_assessed"}):
            route = "new_region_research"
            reasons.append("higher stakes require purpose-specific evidence and transfer review")
        elif route is None:
            route = "accept_for_purpose"
            reasons.append("available record may be used for the stated purpose within its recorded scope")

        if route not in self._GATES:
            raise RuntimeError("invalid gate")
        return {
            "record_id": record_id,
            "purpose": purpose,
            "stakes": stakes,
            "route": route,
            "allowed": route == "accept_for_purpose",
            "axes": {
                "provenance_status": provenance,
                "semantic_support_status": support,
                "empirical_evidence_status": empirical,
                "transfer_status": transfer,
                "authorization_status": authorization,
                "uncertainty": uncertainty,
                "rights": rights if isinstance(rights, dict) else "not_recorded",
                "source_ancestry_ids": sorted(source["id"] for source in sources),
                "unresolved_references": missing_refs,
                "source_family_independence": self._family_independence(sources),
            },
            "reason": "; ".join(reasons),
        }

    def authorize(self, action: str, context: dict) -> dict:
        """Authorize only explicitly allowlisted local operations; never execute actions."""
        if not isinstance(action, str) or not action.strip():
            raise ValidationError("action is required")
        if not isinstance(context, dict):
            raise ValidationError("context must be an object")
        normalized = re.sub(r"[-\s]+", "_", action.strip().casefold())
        rights = context.get("rights")
        if "rights" in context and not isinstance(rights, dict):
            return {"allowed": False, "reason": "rights context is malformed", "gate": "refuse", "executor": False}
        if isinstance(rights, dict) and rights.get("allowed") is not True:
            return {"allowed": False, "reason": "rights are not affirmatively permitted", "gate": "refuse", "executor": False}
        if context.get("source_untrusted") is True or context.get("injection_suspected") is True:
            return {"allowed": False, "reason": "untrusted source content cannot authorize or direct actions", "gate": "quarantine", "executor": False}
        if normalized in self._LOCAL_ACTIONS:
            if context.get("authorized") is True:
                return {"allowed": True, "reason": "authorized within the allowlisted local operation", "gate": "accept_for_purpose", "executor": False}
            return {"allowed": False, "reason": "authorization scope is not recorded", "gate": "new_region_research", "executor": False}
        if normalized.startswith(self._EXTERNAL_PREFIXES) or context.get("consequential") is True:
            return {"allowed": False, "reason": "external or consequential actions have no executor in this service", "gate": "new_region_research", "executor": False}
        return {"allowed": False, "reason": "action is not in the local-operation allowlist", "gate": "refuse", "executor": False}
