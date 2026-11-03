"""Problem diagnosis and conservative mechanism-transfer proposals."""
from __future__ import annotations

from .errors import NotFound, PermissionDenied, ValidationError
from .ports import ProposalProvider, StorePort
from .theory import (
    _claim_context, _data, _list, _mechanism_sources,
    _provider_call_for_sources, _source_allows_model, _source_is_usable,
    _text, _theory_sources, _words,
)


_REFRAMES = [
    ("change_unit", "Could changing the unit of analysis from an individual to the surrounding system alter the maintaining force?"),
    ("change_timing", "Could moving the intervention earlier or later remove the current bottleneck?"),
    ("change_boundary", "Which boundary could be narrowed or widened while preserving the stated desired state?"),
    ("change_objective", "Would a robust or reversible outcome serve the stated goal better than a single optimum?"),
    ("remove_element", "Can the element that creates the stuck condition be removed or made optional?"),
    ("invert_failure", "What reliably produces the opposite of the desired state, and can that condition be reversed?"),
]

_CRITERIA = [
    ("source_fidelity", "Does the idea rely on an unsupported or misread source claim?"),
    ("structural_transfer", "Which target component has no justified source-role mapping?"),
    ("causal_alternative", "Could a different mechanism explain the predicted effect?"),
    ("stakeholders_legitimacy", "Whose interests, vetoes, or values are missing from the dossier?"),
    ("prior_art", "Has relevant prior art been checked, and how narrowly is novelty framed?"),
    ("implementation_harm", "What hidden cost, irreversibility, rights issue, or security risk could defeat this?"),
    ("experiment_design", "Would the proposed test distinguish this idea from its alternatives?"),
    ("system_incentive", "Could model or evaluator incentives make this idea look better than it is?"),
]


def _source_eligible(store: StorePort, mechanism: dict) -> bool:
    try:
        _mechanism_sources(store, mechanism)
        return True
    except (NotFound, PermissionDenied, ValidationError):
        return False


def _problem_sources(store: StorePort, problem: dict) -> list[dict]:
    """Resolve any persisted source ancestry before local or remote use."""
    data = _data(problem)
    sources = []
    for claim_id in _list(data.get("claim_ids")):
        sources.append(_claim_context(store, str(claim_id))[1])
    for source_id in _list(data.get("source_ids")) + _list(data.get("source_id")):
        source = store.get(str(source_id))
        if source.get("kind") != "source" or not _source_is_usable(source):
            raise PermissionDenied("problem source reference is missing, expired, or not permitted")
        sources.append(source)
    for mechanism_id in _list(data.get("source_mechanism_ids")):
        mechanism = store.get(str(mechanism_id))
        sources.extend(_mechanism_sources(store, mechanism))
    for theory_id in _list(data.get("theory_id")):
        theory = store.get(str(theory_id))
        if theory.get("kind") != "theory":
            raise ValidationError("problem theory_id must reference a theory")
        sources.extend(_theory_sources(store, theory))
    return list({source["id"]: source for source in sources}.values())


def _mechanism_match(problem: dict, mechanism: dict) -> dict | None:
    pd, md = _data(problem), _data(mechanism)
    pstruct = _words(pd.get("description")) | _words(pd.get("maintaining_force")) | _words(pd.get("desired_state"))
    f_sig = _words(md.get("functional_signature"))
    s_sig = _words(md.get("structural_signature")) | _words(md.get("problem_state"))
    # These lexical features only identify possible candidates; they are never evidence
    # of causal transfer. Require a nontrivial overlap and expose it for review.
    f_overlap, s_overlap = pstruct & f_sig, pstruct & s_sig
    overlap = f_overlap | s_overlap
    if len(overlap) < 2:
        return None
    return {"functional_overlap": sorted(f_overlap), "structural_overlap": sorted(s_overlap),
            "match_basis": "heuristic lexical signature overlap; requires human review",
            "similarity_is_not_transfer_evidence": True}


class InventionEngine:
    def __init__(self, store: StorePort, provider: ProposalProvider | None = None):
        self.store, self.provider = store, provider

    def problem(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValidationError("problem payload must be an object")
        title, desc = _text(payload.get("title")), _text(payload.get("description"))
        if not title or not desc:
            raise ValidationError("problem requires title and description")
        user_opt_in = payload.get("allow_model", False)
        if not isinstance(user_opt_in, bool):
            raise ValidationError("allow_model must be a boolean")
        allowed = {"title", "description", "desired_state", "maintaining_force", "actors", "constraints",
                   "failed_attempts", "domain", "stakes", "stuck_type", "goal_ladder", "success_judges",
                   "vetoes", "unknowns", "reversibility", "authority", "contradictions", "idempotency_key"}
        data = {k: payload[k] for k in allowed - {"idempotency_key"} if k in payload}
        data.update({"allow_model": user_opt_in, "epistemic_type": "INTERPRETATION",
                     "dossier_status": "independent_problem_dossier"})
        return self.store.put("problem", data, idempotency_key=payload.get("idempotency_key"))

    def forge(self, problem_id: str, payload: dict | None = None) -> dict:
        options = payload or {}
        problem = self.store.get(problem_id)
        if problem.get("kind") not in (None, "problem"):
            raise ValidationError("problem_id must identify a problem")
        pd = _data(problem)
        problem_sources = _problem_sources(self.store, problem)
        user_opt_in = pd.get("allow_model") is True
        diagnosis_proposal = _provider_call_for_sources(self.provider, "invention.diagnose",
            {"problem_id": problem_id, "allow_model": user_opt_in, "source_ids": sorted(
                source["id"] for source in problem_sources), "problem": pd}, problem_sources,
            user_opt_in=user_opt_in)
        inferred_classes = []
        if pd.get("contradictions"):
            inferred_classes.append({"class": "contradiction", "basis": "problem dossier lists competing demands",
                                     "status": "diagnostic_hypothesis"})
        if pd.get("unknowns") or not pd.get("failed_attempts"):
            inferred_classes.append({"class": "missing_fact_or_attempt_history",
                                     "basis": "unknowns or failed-attempt record is incomplete",
                                     "status": "diagnostic_hypothesis"})
        if pd.get("maintaining_force"):
            inferred_classes.append({"class": "maintaining_force_candidate",
                                     "basis": "user-provided maintaining_force field",
                                     "status": "unverified_user_framing"})
        diagnosis = {
            "stated_problem": pd["description"],
            "desired_state": pd.get("desired_state", ""),
            "maintaining_force": pd.get("maintaining_force", ""),
            "actors": pd.get("actors", []), "constraints": pd.get("constraints", []),
            "failed_attempts": pd.get("failed_attempts", []),
            "stuck_type": pd.get("stuck_type", "unspecified"),
            "relevant_unknowns": pd.get("unknowns", []),
            "diagnostic_hypotheses": diagnosis_proposal.get("diagnostic_hypotheses", inferred_classes),
            "reframings": [{"operator": name, "question": question,
                            "goal_alignment": "unassessed"} for name, question in _REFRAMES],
            "epistemic_type": "TRANSFER_HYPOTHESIS" if diagnosis_proposal else "INTERPRETATION",
            "provider_proposal": bool(diagnosis_proposal),
        }
        candidates = []
        for mechanism in self.store.list("mechanism"):
            if not _source_eligible(self.store, mechanism):
                continue
            match = _mechanism_match(problem, mechanism)
            if match:
                candidates.append((mechanism, match, _mechanism_sources(self.store, mechanism)))
        ideas: list[dict] = []
        for mech, match, _ in candidates:
            md = _data(mech)
            idea = {"title": f"Test adaptation of {md.get('title', 'mechanism')}",
                    "source_mechanism_ids": [mech["id"]],
                    "mappings": {"target_problem": pd.get("description"), "candidate_roles": match},
                    "mapping_status": "unresolved_candidate",
                    "mapping_warning": "Lexical overlap only; structural correspondence is not established.",
                    "component_mappings": [{"source_component": term, "target_component": term,
                                            "basis": "shared signature term; correspondence requires review"}
                                           for term in sorted(set(match["functional_overlap"] + match["structural_overlap"]))],
                    "unmapped_source_components": sorted((_words(md.get("functional_signature"))
                                                         | _words(md.get("structural_signature")))
                                                        - (_words(pd.get("description"))
                                                           | _words(pd.get("maintaining_force"))
                                                           | _words(pd.get("desired_state")))),
                    "mismatches": list(md.get("contraindications", [])) + list(md.get("boundary_conditions", [])),
                    "failure_hypotheses": ["The lexical signature overlap is superficial.",
                                           "A key source-domain precondition may not hold in the target."],
                    "negative_transfer_falsification": [
                        "Reject the transfer if the proposed intervention does not alter the named maintaining force.",
                        "Reject or narrow the transfer if a listed contraindication is present.",
                        "Reject the structural analogy if an unmapped source component is necessary to its operation."],
                    "cheapest_test": "Specify one observable target outcome and a reversible, low-cost test that could falsify the mapping.",
                    "novelty_status": "unchecked", "epistemic_type": "TRANSFER_HYPOTHESIS",
                    "source_endorsement": "none_claimed", "prior_art_status": "unchecked",
                    "transfer_status": "unvalidated"}
            ideas.append(idea)
        # Offer a pair only when both mechanisms have their own distinct functional
        # overlap with the target. This is a proposed interaction, not synergy evidence.
        for index, (left, left_match, _) in enumerate(candidates):
            for right, right_match, _ in candidates[index + 1:]:
                left_f = set(left_match["functional_overlap"])
                right_f = set(right_match["functional_overlap"])
                if len(left_f) >= 2 and len(right_f) >= 2 and left_f.isdisjoint(right_f):
                    ld, rd = _data(left), _data(right)
                    ideas.append({"title": f"Test a sequence combining {ld.get('title', 'mechanism A')} and {rd.get('title', 'mechanism B')}",
                        "source_mechanism_ids": [left["id"], right["id"]],
                        "mappings": {"mechanism_a_contribution": sorted(left_f),
                                     "mechanism_b_contribution": sorted(right_f),
                                     "interaction_hypothesis": "The mechanisms may address distinct target functions when combined; their interaction is unknown."},
                        "mapping_status": "unresolved_candidate",
                        "mismatches": list(ld.get("contraindications", [])) + list(rd.get("contraindications", [])),
                        "failure_hypotheses": ["The two mechanisms interfere when combined.",
                                               "The apparent functional complementarity is lexical only."],
                        "negative_transfer_falsification": ["Test each mechanism alone before comparing the combined sequence.",
                                                             "Reject the pair if the combined version performs no better than its component mechanisms on the target measure."],
                        "cheapest_test": "Compare reversible, bounded trials of A, B, and A+B on the same predefined target measure.",
                        "novelty_status": "unchecked", "epistemic_type": "TRANSFER_HYPOTHESIS",
                        "source_endorsement": "none_claimed", "prior_art_status": "unchecked",
                        "transfer_status": "unvalidated", "interaction_status": "hypothesis_only"})
        model_candidates = [(m, match, sources) for m, match, sources in candidates
                            if all(_source_allows_model(s) for s in sources)]
        model_sources = list(problem_sources)
        model_sources.extend(source for _, _, sources in model_candidates for source in sources)
        model_sources = list({source["id"]: source for source in model_sources}.values())
        provider_payload = {"problem_id": problem_id, "allow_model": user_opt_in,
                            "source_ids": sorted(source["id"] for source in model_sources),
                            "problem": pd, "diagnosis": diagnosis,
                            "candidate_mechanisms": [{"id": m["id"],
                                "source_ids": sorted(source["id"] for source in sources),
                                "data": _data(m)} for m, _, sources in model_candidates]}
        proposal = _provider_call_for_sources(self.provider, "invention.forge", provider_payload,
            model_sources, user_opt_in=user_opt_in)
        for raw in _list(proposal.get("ideas")):
            if not isinstance(raw, dict):
                continue
            title = _text(raw.get("title"))
            if not title:
                continue
            source_ids = [str(x) for x in _list(raw.get("source_mechanism_ids"))]
            eligible_ids = {m["id"] for m, _, _ in model_candidates}
            if any(mid not in eligible_ids for mid in source_ids):
                continue
            # Structured provider text remains a proposal, never evidence or novelty.
            ideas.append({"title": title,
                          "proposal": _text(raw.get("proposal")),
                          "source_mechanism_ids": source_ids,
                          "mappings": raw.get("mappings", {}),
                          "mismatches": _list(raw.get("mismatches")),
                          "failure_hypotheses": _list(raw.get("failure_hypotheses")),
                          "negative_transfer_falsification": _list(raw.get("negative_transfer_falsification")),
                          "cheapest_test": _text(raw.get("cheapest_test")),
                          "novelty_status": "unchecked", "epistemic_type": "TRANSFER_HYPOTHESIS",
                          "source_endorsement": "none_claimed", "prior_art_status": "unchecked",
                          "transfer_status": "unvalidated"})
        contradictions = _list(pd.get("contradictions"))
        contradiction_alternatives = []
        for c in contradictions:
            if isinstance(c, dict):
                a, b = _text(c.get("side_a")), _text(c.get("side_b"))
                if a and b:
                    contradiction_alternatives.append({"title": "Separate competing demands by condition",
                        "proposal": f"Test whether '{a}' and '{b}' can be separated by role, timing, or operating condition.",
                        "source_mechanism_ids": [], "epistemic_type": "TRANSFER_HYPOTHESIS",
                        "novelty_status": "unchecked", "prior_art_status": "unchecked",
                        "cheapest_test": "Identify one condition under which each demand dominates, then test a reversible separation."})
        ideas.extend(contradiction_alternatives)
        if not candidates:
            missing = [{"type": "information_deficit", "question": "Which source mechanism has a justified functional or structural correspondence to this problem?",
                        "reason": "No eligible mechanism met the minimal candidate-matching threshold."}]
        else:
            missing = []
        if not ideas:
            missing = [{"type": "information_deficit", "question": "Which source mechanism has a justified functional or structural correspondence to this problem?",
                        "reason": "No eligible mechanism met the minimal candidate-matching threshold."},
                       {"type": "information_deficit", "question": "What maintaining force, stakeholder veto, or failed-attempt evidence remains unknown?",
                        "reason": "The current dossier does not support a defensible transfer proposal."}]
        elif ideas:
            missing.extend([{"type": "prior_art", "question": "Has claim-level prior art been checked?",
                        "reason": "Novelty status remains unchecked."},
                       {"type": "discriminating_test", "question": "What observation would distinguish each transfer hypothesis from its strongest alternative?",
                        "reason": "No target-domain validation has been recorded."}])
        idea_records = []
        for index, idea in enumerate(ideas):
            idea_key = f"{options['idempotency_key']}:idea:{index}" if options.get("idempotency_key") else None
            record = self.store.put("idea", {**idea, "problem_id": problem_id},
                                    idempotency_key=idea_key)
            self.store.link(record["id"], problem_id,
                            "STRUCTURALLY_MATCHES" if idea.get("source_mechanism_ids") else "DEPENDS_ON",
                            polarity="neutral", data={"transfer_status": "unvalidated",
                                                      "mapping_status": idea.get("mapping_status", "unresolved_candidate")})
            for mechanism_id in idea.get("source_mechanism_ids", []):
                self.store.link(record["id"], mechanism_id, "INSPIRED_BY", polarity="neutral")
            idea_records.append(record)
        return {"problem": problem, "diagnosis": diagnosis, "ideas": idea_records,
                "missing_evidence": missing}

    def discover(self, mechanism_id: str, payload: dict | None = None) -> dict:
        """Search independently entered problem dossiers for future applications."""
        options = payload or {}
        if not isinstance(options, dict):
            raise ValidationError("discover payload must be an object")
        mechanism = self.store.get(mechanism_id)
        if mechanism.get("kind") != "mechanism":
            raise ValidationError("mechanism_id must identify a mechanism")
        if not _source_eligible(self.store, mechanism):
            raise PermissionDenied("mechanism has denied, missing, expired, or poisoned source ancestry")
        mechanism_sources = _mechanism_sources(self.store, mechanism)
        requested_ids = set(str(x) for x in _list(options.get("problem_ids")))
        limit = options.get("limit", 20)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValidationError("limit must be a positive integer")
        problems = []
        for problem in self.store.list("problem"):
            data = _data(problem)
            if requested_ids and problem["id"] not in requested_ids:
                continue
            # Source-derived problems are not the independent target descriptions
            # required for this direction of discovery.
            if any(data.get(field) for field in ("source_id", "source_ids", "claim_ids", "span_ids")):
                continue
            problems.append(problem)
        opportunities = []
        for problem in problems:
            match = _mechanism_match(problem, mechanism)
            if not match:
                continue
            pd, md = _data(problem), _data(mechanism)
            opportunities.append({"problem_id": problem["id"], "problem_title": pd.get("title", ""),
                "title": f"Explore {md.get('title', 'mechanism')} for {pd.get('title', 'an independent problem')}",
                "source_mechanism_ids": [mechanism_id],
                "mappings": {"target_problem": pd.get("description"), "candidate_roles": match},
                "mapping_status": "unresolved_candidate",
                "mapping_warning": "Lexical overlap only; structural correspondence is not established.",
                "mismatches": list(md.get("boundary_conditions", [])) + list(md.get("contraindications", [])),
                "failure_hypotheses": ["The shared terms conceal different functional or structural roles.",
                                       "The mechanism's source-domain conditions do not hold in this problem."],
                "negative_transfer_falsification": ["Reject the opportunity if no component-level mapping can be independently specified.",
                    "Reject or narrow it if any boundary condition or contraindication applies."],
                "cheapest_test": "Have a reviewer map mechanism components to problem components, then identify one reversible test that could falsify the mapping.",
                "novelty_status": "unchecked", "prior_art_status": "unchecked",
                "epistemic_type": "TRANSFER_HYPOTHESIS", "source_endorsement": "none_claimed"})
            if len(opportunities) >= limit:
                break
        opportunities = opportunities[:limit]
        if opportunities:
            unknown = {"status": "unknown_applications_remain", "reason":
                       "This search covered only eligible stored problem dossiers; no global novelty or applicability claim is made."}
            missing = [{"type": "prior_art", "question": "Has prior art been checked for each opportunity?",
                        "reason": "Novelty remains unchecked."}]
        else:
            unknown = {"status": "no_match", "reason":
                       "No eligible independently entered problem dossier matched the mechanism signatures."}
            missing = [{"type": "information_deficit", "question": "Which independently described problem could this mechanism plausibly address?",
                        "reason": "No defensible candidate was found in the available problem observatory."}]
        return {"mechanism": mechanism, "opportunities": opportunities,
                "unknown_applications": unknown, "missing_evidence": missing}

    def red_team(self, idea_id: str) -> dict:
        idea = self.store.get(idea_id)
        if idea.get("kind") not in (None, "idea"):
            raise ValidationError("idea_id must identify an idea")
        d = _data(idea)
        findings = []
        for code, question in _CRITERIA:
            if code == "source_fidelity":
                status = "concern" if not d.get("source_mechanism_ids") else "needs_source_review"
                rationale = "Source ancestry is absent." if not d.get("source_mechanism_ids") else "Citation fidelity requires inspecting original source spans."
            elif code == "structural_transfer":
                status = "concern" if not d.get("mappings") else "unresolved"
                rationale = "No explicit component mapping is recorded." if not d.get("mappings") else "Mapping is a proposal; validate each component and mismatch."
            elif code == "causal_alternative":
                status = "concern" if not d.get("failure_hypotheses") else "unresolved"
                rationale = "No failure hypotheses are recorded." if not d.get("failure_hypotheses") else "Alternative causal explanations remain untested."
            elif code == "stakeholders_legitimacy":
                status = "concern" if not d.get("stakeholders") else "unresolved"
                rationale = "No stakeholder/legitimacy analysis is recorded." if not d.get("stakeholders") else "Stakeholder effects and vetoes require human review."
            elif code == "prior_art":
                status = "unchecked"
                rationale = "Prior art has not been checked; no novelty claim is warranted."
            elif code == "implementation_harm":
                status = "concern" if not d.get("risks") else "unresolved"
                rationale = "Risks, costs, rights, and reversibility are not recorded." if not d.get("risks") else "Recorded risks do not establish safety."
            elif code == "experiment_design":
                status = "concern" if not d.get("cheapest_test") else "unresolved"
                rationale = "No discriminating test is recorded." if not d.get("cheapest_test") else "Test specificity and discriminating power are unverified."
            else:
                status, rationale = "unresolved", "Model/judge incentive effects were not independently evaluated."
            findings.append({"criterion": code, "question": question, "status": status, "finding": rationale})
        return {"idea_id": idea_id, "review_type": "automated_adversarial_checklist",
                "independent_human_review": False, "findings": findings,
                "overall_status": "unvalidated", "novelty_status": "unchecked"}
