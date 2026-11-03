# Independent adversarial acceptance review

**Scope:** Frozen Wisdom Foundry contracts v1.0.0, the WISDOM FOUNDRY 11 architecture, and AAA v7.1 specification. The initial test design preceded implementation. A later read-only pass of the integrated service modules identified concrete authority and permission issues listed below; this is not a full candidate acceptance review because the API/composition layer was not yet integrated or frozen.

## Prioritized threats and acceptance conditions

| Priority | Threat | Acceptance condition |
|---|---|---|
| P0 | Untrusted-source prompt injection or task hijacking | Source text remains data through ingestion, analysis, retrieval, memory, and workflows. A source cannot change rights, permissions, policy, evaluation, or cause an external effect. Injection attempts are retained or quarantined with provenance, not obeyed. |
| P0 | Fabricated quotation, speaker, transcript, or citation | Every source-attributed quote is an exact, context-checked substring of immutable source spans with valid offsets and speaker attribution. Missing/unavailable source material remains blocked/partial; generation cannot fill the gap. Unsupported quotations are rejected or explicitly marked as unverified hypotheses, never stored as source fact. |
| P0 | Privacy/rights bypass or cross-record disclosure | Denied or restricted source material cannot be analyzed, retrieved into unrelated context, exported, or exposed to a provider. Private and non-exportable flags are enforced at each boundary, including derived records and exports; deletion/purge propagates to derived caches where required. |
| P0 | Unauthorized external action | Decision approval is a human-choice record only. Authorization is a separate gate, and execution requires an explicit capability, scope, risk check, and appropriate human approval. Retrieved prose, an approved option, or a job retry is not itself execution authority. |
| P1 | Prediction/outcome contamination | Registered predictions are immutable and timestamped/hashed before outcome arrival. Outcomes append new records; learning never revises the historical prediction or its precommitment hash. |
| P1 | Idempotency replay or key collision | Exact retries return the same result without duplicate records, events, or effects. Reusing a key with any changed request payload produces a conflict and no mutation. Replay must remain correct after restart. |
| P1 | Source-family laundering | Copies, syndications, model paraphrases, and pages deriving from one root are counted as one evidence family. Independent support is proposition-specific and polarity-aware; a shared family must not silently increase corroboration. |
| P1 | Unsupported promotion | A plausible idea, one anecdote, user adoption, or model confidence cannot become validated empirical knowledge or an active skill by promotion alone. Evidence support, uncertainty, applicability, contraindications, and required authority remain distinct. |
| P2 | Cross-boundary epistemic collapse | Source claims, interpretations, theories, transfer hypotheses, predictions, observations, and decisions retain distinct types and lineage. Similarity is not mechanism identity; an idea is not a validated novelty claim. |
| P2 | Self-evaluation/reward gaming | Evaluation and evidence authority are outside the candidate being judged; held-out outcomes and independent checks are used where required. Candidate-produced score files are not authoritative evidence. |

These priorities combine the hard evidence, permission, privacy, and authority controls in architecture §§4, 5, 10, 11, and 14 with AAA v7.1's authority separation, typed effects, immutable generations, and evidence-promotion firewall. P0 acceptance is a precondition to enabling any external-action path.

## Adversarial test coverage

`tests/test_adversarial.py` probes documented public ports/service slots for source injection, empty-source hallucination, invented quotation, exact-payload idempotency, prediction immutability, source-family independence, unsupported skill promotion, and approval-versus-execution separation. It deliberately uses hostile provider outputs and same-family copied material.

The tests are acceptance probes, not a complete security proof. They need adaptation only where the integrated implementation's public envelope representation differs from the frozen contract; do not weaken the tested invariants to match an unsafe implementation. Tests should run against a clean integrated candidate and, for replay claims, against a file-backed SQLite store reopened between attempts.

## Contract gaps to resolve during integration

1. `Source` supports a fixed rights object, while policy outcomes for `allowed=false`, missing rights, and mixed private/export restrictions are not fully specified in the frozen contract. Define fail-closed behavior and error/state semantics; do not infer authorization from source text.
2. `Governor.authorize(action, context)` does not spell out capability tokens, actor identity, approval binding, expiry, or effect class. Before wiring tools, bind authorization to a specific principal, action, target, payload digest, expiry, and idempotency/fencing identity. A generic `human_approved: true` boolean is insufficient for consequential actions.
3. `source_family` is present, but the contract does not define lineage discovery, independent-family counting, or how cross-family sources that copy a common origin are handled. Preserve uncertainty rather than count sources as independent by default.
4. The prediction schema says immutable, timestamped, and hashed, but does not fix canonical serialization, hash algorithm, timestamp source, or how subsequent metadata is separated from the committed prediction payload. Define these before asserting hash compatibility across implementations.
5. The local contract does not expose an external-action execution port. Keep this boundary absent unless separately specified and gated; approval, routing, job execution, and retry must not acquire ambient external authority.
6. The architecture's broad evaluation claims require blinded human/expert labels, source anchors, negative examples, and holdout tasks. Deterministic unit fixtures can detect regressions but cannot establish comparative product value.

## Read-only findings from the current integration

These findings were reported to the integration owner for remediation. Recheck them against the frozen candidate before treating them as resolved.

| Priority | Finding | Evidence and impact |
|---|---|---|
| P0 / privacy | `EvidenceService.analyze` forwards source spans to a configured `ProposalProvider` after checking `rights.allowed`, without consulting the existing model-purpose permission gate. | `wisdom/evidence.py` sends `spans` to `provider.complete`; `wisdom/access.py::allowed(..., purpose="model")` requires `rights.allow_model is True`, but the evidence path does not call it. A private source without model permission can therefore leave the local boundary. The frozen source schema should add an explicit model-processing consent field and fail closed. |
| P1 / authority | `Governor.authorize` permits an unregistered action when the context has the generic `authorized: true` flag. | The consequential-action set is a small fixed list. `send_email` with `{"authorized": true, "human_approved": false}` falls through and is allowed. Unknown effects should deny by default or require a declared typed effect and scoped capability. |
| P1 / inherited rights | `Governor.assess` reads only the assessed record's local rights fields, rather than restricting assessment through source ancestry. | A derived claim with favorable local support fields can be assessed for export even when its source is blocked/private/non-exportable. This conflicts with purpose-bound derived access and can make a downstream decision appear authorized. |
| P1 / deletion lineage | Store purge traversal does not recognize the `source_mechanism_ids` field used on generated ideas. | The idea's outgoing `inspired_by` edge points from the idea toward its mechanism, while purge walks forward from doomed ancestors. A source purge may delete its claim/mechanism lineage yet leave generated ideas, their text, or their indexed FTS entry. Add the lineage key to deletion dependency traversal and verify descendants are removed. |

The current integration also stores `original_text` in a `BLOCKED` source record when rights are denied. Whether local retention is permitted depends on rights semantics, which the frozen source contract does not define. Fail closed by discarding the body for denied rights unless retention is explicitly authorized; a blocked metadata stub is sufficient to record the access gap.

## External Gates 0–5 remain open

No local contract test, synthetic fixture, implementation demo, model self-rating, or architecture conformance score can close the empirical roadmap. Preserve these independent gates as external acceptance work:

| Gate | Evidence still required |
|---|---|
| **0 — Define value** | Authorized representative source set, independently collected problems, manual coding rubric, rights/access record, strong LLM+RAG baseline, annotated mechanism/problem set, and baseline review-time measurement. |
| **1 — Evidence and attribution** | Independent source anchors and blinded evaluation of quote fidelity, speaker position, qualifications, rebuttals, ambiguity, and correction burden; fail/rework on persistent fabricated quotations. |
| **2 — Theory and mechanisms** | Unseen sources/problems, explicit negative cases and source-family deduplication; compare against simpler summarization/reasoning baselines for scope and theory quality. |
| **3 — Generative invention** | Blinded independently sourced problems, hard negative transfers, external novelty/prior-art review, usefulness and structural diversity ratings, cost, and harm review. Model-judge appeal is insufficient. |
| **4 — Decision and learning** | Preregistered predictions, measured outcomes, contamination controls, holdout tasks after feedback, baseline comparison, causal limitations, skill conditions/counterexamples, and human-agency/overdependence measures. |
| **5 — Productization and autonomy** | Reproducible operations, deletion/export verification, rights/security review, shadow/rollback evidence, human-agency metrics, bounded costs, and explicit scoped approval for any external effects. |

**Disposition:** Adversarial contract tests are necessary but not sufficient. Before any claim of empirical superiority, every applicable external Gate 0–5 needs independently reviewable evidence. AAA v7.1 conformance and local test passage would establish design/implementation properties only, not wisdom quality, invention value, or real-world benefit.
