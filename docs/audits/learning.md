# WF-AUDIT-LEARN: decisions, learning, and memory review

**Candidate:** `git:40312598dbf10dbc351ca8a3148966d5336dd5ad`
**Verdict:** **Conditional fail: two P1 governance/integrity findings; other reviewed paths pass their stated engineering guards.**
**Scope:** Read-only review of `wisdom/learning.py`, `wisdom/memory.py`, source-to-learning API flow, the frozen service contract, and architecture §§8–9 and 11. No production files or tests were changed.

## Findings

### P1 — Outcome idempotency does not bind a caller-supplied timestamp

At `wisdom/learning.py:363–370`, replay comparison removes `occurred_at` from both the stored outcome and the retry before comparing. That is useful when the service generated the timestamp because the caller omitted it, but it also silently ignores a different timestamp explicitly supplied on retry.

**Probe:** Registered a prediction, submitted outcome key `same` with timestamp T1, then replayed the same key and all other fields with distinct valid timestamp T2. `observe()` returned the original outcome instead of raising `Conflict`; the stored time remained T1. This violates payload-bound idempotency for explicit timestamps and can conceal a conflicting event-time assertion.

**Repair direction:** Preserve whether `occurred_at` was supplied. Ignore the generated timestamp only for retries that omitted it; compare normalized caller-supplied timestamps exactly otherwise.

### P1 — Human authority is recorded as caller-asserted text/boolean, not verified identity

`MemoryService.goal()` trusts `human_approved is True` and stores the caller-provided `owner` (defaulting to `local-user`) at `wisdom/memory.py:21–27`. `DecisionService.approve()` accepts any non-empty `approved_by` and records it as the event principal without comparing it to the decision owner or an authenticated actor at `wisdom/learning.py:185–203`. The API dispatches these payloads directly at `wisdom/api.py:180–184, 197`.

**Probe:** `goal({title: "AI-owned value", human_approved: true, owner: "assistant-generated"})` succeeded. A decision owned by `actual-owner` was approved with `approved_by: "unrelated-caller"`.

The local CSRF/origin checks mitigate cross-site requests; they do not authenticate who submitted a payload. These APIs do not execute actions, so the demonstrated issue is authority and audit integrity rather than an external side effect. Still, a record can claim human ownership or approval without a verified human decision.

**Repair direction:** Bind approvals and goal creation to an authenticated local principal or an explicit human confirmation flow whose identity is established outside the submitted JSON. Reject mismatched owners where the decision contract grants approval to its owner.

### P2 — Skill promotion checks a mechanical floor, not whether the evidence supports the skill

`OutcomeLab.promote()` requires reviewer-supplied `evidence_sufficient=True`, an evidence reviewer, separate authorization text, and two distinct prediction IDs with non-missing observations whose learning hashes match their registered predictions (`wisdom/learning.py:461–505`). It does not test whether observations align with the proposed skill, whether conditions were comparable, or whether the prediction contexts are independent. The returned status is `promoted_conditional` and `authorization.executable` remains false.

**Probe:** Two distinct predictions stated that a procedure would increase a metric; both recorded free-text observations said “metric declined.” With a reviewer assertion of sufficiency and separate authorization text, the service still promoted the skill. This shows the floor verifies record shape and linkage, not support direction or transfer validity.

The implementation is appropriately documented in `docs/contracts.md:44` as an engineering guard, not a scientific sufficiency theorem. Keep the promotion label conditional and non-executable; do not present it as validated behavior. A stronger gate would record the reviewer’s scoped rationale, counterexamples, applicability conditions, and why these cases support this skill despite their observed direction.

The accompanying learning record also does not compute agreement with `expected`/`direction` for general metrics: `learn()` marks any non-missing observation `observed` and emits a generic comparison sentence (`wisdom/learning.py:387–410`). Outside the narrow Brier case, the raw registered forecast and outcome are included, but the field named `comparison` does not report whether they agree. Treat this as a P2 clarity/learning limitation, not measured evidence of system improvement.

## Checks that passed

- **Forecast sealing and temporal checks:** Predictions carry a registration timestamp and preregistration hash and are written immutable. Outcomes before registration, in the future, or with missing observation lacking an explanation are rejected. Recording an outcome did not change the prediction envelope in the HTTP scenario.
- **Outcome and learning behavior:** Same-key ordinary retries replayed. Store-level idempotency conflict behavior is tested; the explicit-timestamp service mismatch is the exception documented above. Learning preserves missingness, limitations, and a causal caution. Brier scoring is limited to a declared binary metric with one valid binary observation.
- **Decision output:** Approvals record a selected existing option and a reason; no action is executed. VOI is qualitative and does not invent calibrated expected utility.
- **Human-owned goal gate:** A missing approval flag is rejected; an explicit flag produces a `NORMATIVE_POSITION` record. The identity limitation above remains.
- **Trigger expiry, deduplication, and attention budget:** Existing tests verify expiry and duplicate suppression. A zero-budget probe returned zero notifications without consuming the later alert; increasing the budget allowed one notification, and a repeated identical signal was suppressed.
- **Linked private trigger data:** A local reminder linked to a private source with export/model sharing disabled could fire. Its notification exposed the trigger’s title/suggestion and opaque linked ID, not source text; the trigger evaluator uses the local `allowed()` check and makes no provider call. This is consistent with private local suggestions, but the specific privacy case is a probe rather than a committed regression test.
- **Source-to-learning flow:** The HTTP scenario traversed source → evidence → theory/mechanism → decision → prediction → outcome → learning and retained source lineage. It was synthetic fixture coverage, not an empirical outcome study.

## Test and probe record

- `python3 -m unittest discover -s tests -v` — **94 tests passed** on the candidate.
- Targeted in-memory probes reproduced the two P1 findings and the skill-floor limitation described above; trigger probes confirmed zero-budget deferral, subsequent one-time delivery, and same-state deduplication.
- No files in production code or test suites were changed for this audit.

## Limits and open work

No real-world skill utility, calibration, human capability, or causal benefit was tested. A single machine reviewer cannot establish whether the skill gate is scientifically sufficient. Live provider behavior, browser rendering, independent participant review, and empirical Gates 0–5 remain unrun and open. Trigger deduplication is state-hash based: after a notification, the same relevant signal values remain suppressed for that trigger until its relevant state changes or the trigger is replaced/expired; there is no explicit re-arm interval.
