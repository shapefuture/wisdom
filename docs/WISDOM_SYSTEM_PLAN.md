# Wisdom Foundry: consolidated system plan (v2 direction)

Status: proposed plan, not an accepted specification. Empirical gates 0–5 remain open until measured with independent evidence.
Sources combined: `docs/architecture.md` (Wisdom Foundry 11 blueprint), the "Wisdom Foundry 2.0" strategic audit, the Stoa Wisdom Atlas review, the mining plan, and the follow-on capability review. Sunk cost is ignored throughout: where the current code is the wrong foundation, this plan says so.

---

## 0. Purpose and definition of success

**Purpose.** Turn sources, experience and hard problems into better human judgment, new options that were not visible before, tested interventions, and durable human capability. Mining wisdom from sources is one input to that purpose, not the purpose.

**Definition of done (the "10/10" target, made measurable).** The system reaches its target only when all of the following are demonstrated with independent evidence, not fixtures:

1. **Source fidelity.** Every quoted or cited passage is a verbatim, timestamped span that a reviewer can reopen. Zero unattributed or invented quotations in audited output.
2. **Mining quality.** Candidate precision and recall per kind are measured on a blinded gold set, with intervals and labeller agreement reported.
3. **Epistemic honesty.** No output presents a source report, an interpretation, a transfer hypothesis, a tested finding, or an authorised skill as a different type. Audits find no type laundering.
4. **Retrieval.** Recall, relevance, and source-family diversity beat a plain full-text baseline and a cited-RAG baseline on held-out episodes and held-out domains.
5. **Invention.** Blinded expert panels rate structural transfer and invention as more accurate, diverse, and useful than brainstorming and lexical baselines, with false transfers counted explicitly.
6. **Decisions.** Decision contracts with timestamped evidence snapshots improve measured decision quality against a no-system control, and the system recommends "do less research" when that is correct.
7. **Experiments and learning.** Preregistered predictions and discriminating tests produce outcome records, and conditional skills hold up on held-out tasks.
8. **Human capability.** Unaided performance does not degrade, and ideally improves, with use. Measured without the assistant present.
9. **Governance.** Permission, rights, prompt-injection, memory-poisoning and deletion tests pass before any external-action authority is granted.
10. **Reproducibility.** Every headline number can be regenerated from the packaged data, and every gap is named.

Items 1–3 and 9–10 are engineering targets. Items 4–8 need measurement design, independent annotators, baselines, and real use. The tracker must mark those as evidence-blocked rather than simulate them.

---

## 1. Non-negotiable principles

These come from the blueprint's twelve invariants and the audit. They constrain every subsystem.

1. **Separate types, never collapse them.** Source report ≠ attributed claim ≠ interpretation ≠ explanatory hypothesis ≠ transfer hypothesis ≠ tested finding ≠ practice candidate ≠ authorised skill ≠ normative position ≠ open question. Status is versioned and purpose-dependent.
2. **Preserve the source.** Originals are immutable. Spans are verified against them. Transcript quality is recorded, not hidden.
3. **Context is part of meaning.** Speaker, genre, modality, qualifiers, dialogue sequence, and dissent are retained. Speaker identity stays uncertain until supported.
4. **Similarity is not equivalence.** Lexical overlap, embedding closeness, structural correspondence, causal identity, and practical transfer are different claims with different labels.
5. **Absence is not evidence of absence.** Unknown, contradicted, withdrawn, stale and out-of-scope are distinct states.
6. **Evidence integrity and authorisation are hard gates.** Novelty or expected value cannot buy past a rights or safety refusal.
7. **Source text is data.** It cannot authorise tools, values, permissions or promotion.
8. **Human authority is separate from model output.** Models propose. Humans approve. Approving a decision is not authorising an action.
9. **Never let model judgment grade model output.** Evaluation labels come from independent or blinded humans, and the watchdog keeps private examples.
10. **Preserve dissent and unresolved aporia.** Do not manufacture consensus or force one reading.
11. **Keep the human capable.** Measure unaided performance. Fade assistance as independence grows.
12. **Add complexity only when a benchmark shows it helps.**

---

## 2. Decisions: keep, replace, build (sunk cost ignored)

| Area | Current | Decision | Reason |
|---|---|---|---|
| Exact source spans, Unicode offsets, timestamp anchors | Implemented, verified | **Keep, make the foundation** | Best-proven part of the system |
| Immutable originals, content hashes | Implemented | **Keep** | Needed for any audit |
| Hash-chained event journal | Implemented | **Keep, extend** with recorded time, parents, method version, consent scope, reason | Replay and audit depend on it |
| Rights, consent, deletion propagation | Implemented | **Keep, extend** with rights basis and attestation | Required for any real corpus |
| SQLite as the store | Implemented | **Keep** | Adequate for a single-user system; graph DB only on measured need |
| Generic `records` with JSON `data` | Implemented | **Replace the semantics**, keep the storage: typed tables or validated JSON with enforced schemas | Store currently accepts any dictionary |
| Generic `edges` table as the authoritative relation | Implemented | **Replace** with qualified relation records; keep edges as a rebuildable index | Relations need context, evidence, review, and time |
| `semantic` retrieval lens | Lexical alias | **Rename to `lexical`**; add real semantic channel only when measured | Honesty |
| Lexical mechanism matching emitting `STRUCTURALLY_MATCHES` | Implemented | **Replace**: emit `CANDIDATE_RESEMBLANCE` | Lexical overlap is not structure |
| Claim extraction with single epistemic type | Implemented (provider-assisted, span-verified) | **Redesign** into source occurrence → assertion → proposition → evidence item | Provenance and normalisation are missing |
| Theory and mechanism cards | Implemented | **Redesign** into typed models with scope, evidence polarity, failure conditions | Needs multi-model structure |
| Problem dossiers | Implemented | **Keep, extend** and bind into a Problem-to-Change Case | Dossiers are sound |
| Invention matcher | Lexical | **Replace** with structural transfer pipeline | Core intellectual weakness |
| Red-team checklist (eight attacks) | Implemented | **Keep**; add independent human review path | Checklist is automated, not independent |
| Decision contracts | Implemented, partial fields | **Keep, complete** per blueprint §8.1 | Strong design |
| Qualitative VOI | Implemented | **Keep**, add stop rule | Enables "do less research" |
| Preregistration hashes, append-only outcomes | Implemented | **Keep and expand** | Core experimental integrity |
| Conditional skills with evidence and authorisation gates | Implemented, single promotion path | **Keep**; split knowledge gate and execution gate | Blueprint §9.6 |
| Prospective triggers | Implemented | **Keep** | Advisory-only, expiring |
| Goals and TRACE | Implemented | **Keep** | Human-owned |
| Watchdog | Structural checks only | **Extend** into independent audit system | Missing reject audits, drift, suppression checks |
| Web workbench | Responsive, not browser-verified | **Redesign** around Problem-to-Change Cases and coverage-first views | Current UI is an admin console |
| Mining pipeline (Stoa-style patterns) | Prototype outside the repo | **Reimplement cleanly** inside the package; treat patterns as candidate generation only | Scripts have no licence; typing was unreliable |
| Audio-proxy acquisition route | Prototype outside the repo | **Do not adopt** | Circumvents platform access controls |
| Evaluation fixtures | Synthetic | **Keep as software tests**; add gold sets and blinded panels as separate evidence | Fixtures cannot establish value |

The clean approach is a **v2 core** on a new branch, porting only the kept foundations (span store, rights, journal, decisions, preregistration) and rebuilding the epistemic model, extraction, retrieval, invention and learning on top. Migrate existing records through explicit migrations, with v1 records kept readable.

---

## 3. Target architecture

### 3.1 Three objective loops, three epistemic engines, one human cycle

- **Objectives:** EXECUTE (decisions and progress), DISCOVER (options and questions not implied by current goals), RETHINK (challenge assumptions, goals and the system's own behaviour).
- **Engines:** EVIDENCE (what sources actually communicate), THEORY (scoped explanations and conditional mechanisms), INVENTION (transformations and combinations, strongly criticised).
- **Human cycle:** TRACE — NOTICE → INTERPRET → VALUE → EXPLORE → ACT → LEARN — with feedback between any stages. The system supports this cycle. It does not own it.

### 3.2 Layers

```
Human authority and consent (values, decisions, approvals, goals)
        │
Workbench (case view, coverage-first home, review queues, generative panel kept separate)
        │
Application services
  Intake · Mining · Evidence · Theory · Case · Invention · Decision · Experiments · Capability · Memory · Retrieval · Watchdog · Workflows
        │
Canonical epistemic substrate (typed objects, qualified relations, derivation DAG, bitemporal events)
        │
Storage (immutable originals, SQLite records and FTS5, event journal, rebuildable indexes, exports)
        │
Cross-cutting assurance (rights, permissions, validation, provenance, uncertainty, audit, rollback)
```

### 3.3 Canonical object model

Typed objects. No universal "knowledge" table.

| Object | Contents | Identity rule |
|---|---|---|
| `Source` | URI or local path, title, rights basis, attestation, retrieval and publication times, original hash, transcript provenance (`creator_provided`, `caption_auto`, `asr_local`, `human_verified`) | Immutable original |
| `SourceSpan` | Exact character or time range, speaker and speaker uncertainty, hash | Never edited |
| `SourceOccurrence` | A statement at a place in a source, with extraction method and version | Immutable |
| `Utterance` | Turn, speaker, speech act, genre tags, linked spans | Speaker's words, not analyst's |
| `Assertion` | What a source or speaker asserts, with modality, negation, qualifiers, scope | Attribution explicit |
| `Proposition` | Normalised statement assessed across sources | Linked to assertions and evidence |
| `EvidenceItem` | Material bearing on a proposition, with polarity and quality | Separate from the AI's confidence in extraction |
| `EvidenceAssessment` | Study design, population, measurement, effect and uncertainty where applicable, risk of bias, directness, consistency, source-family independence, reviewer | No single confidence scalar |
| `Concept` | Intellectual entity with per-source `Definition`s, aliases, distinctions, examples, counterexamples | SKOS-like; definitions keep their source |
| `Interpretation` | One reading of a passage, its textual basis, conflicts, reader type (speaker-intended, interlocutor-inferred, analyst-proposed) | Several readings may coexist |
| `InterpretationLattice` | The set of supported readings for a passage, with conditions for choosing among them | Never forced to one reading |
| `Argument` | Claim, grounds, warrant, backing, qualifier, rebuttal, and who offered each part | Explicit argument edges |
| `Viewpoint` | Endorsement or dissent, context, source | Dissent kept |
| `Model` | Typed explanatory structure: conceptual, argument, causal, systems, temporal, analogical, or explanatory | Specialised by type |
| `Theory` | Scoped regularity, evidence for and against, alternatives, preconditions, predictions, failure conditions, open questions | May stay provisional |
| `Mechanism` | Passport: functional result, actors and roles, state transitions, relationships, resources, feedback, incentives, conditions, invariants, failure modes, evidence, transfer history | Source mechanism ≠ target transfer |
| `Problem` | Current and desired state, maintaining forces, actors, vetoes, constraints with provenance, failed attempts, unknowns, horizon | Independent of solutions |
| `Idea` (hypothesis) | Proposed transfer or intervention, mapping, mismatches, falsifiers, cheapest test, transfer status | Generated portions typed separately |
| `TransferMap` | Source and target roles, mapped relations, unmapped components, disanalogies, invariants, prerequisites, negative-transfer scenarios | Required before any transfer rung above candidate |
| `Case` | Problem-to-Change Case linking the above in order, with missing steps shown | Versioned; gaps explicit |
| `Goal` | Human-approved value or outcome, horizon, review date, decision rights | AI cannot change it silently |
| `Decision` | Contract (see §3.6) | Timestamped before resolution |
| `Prediction` | Outcome variable, expected direction or range, horizon, comparator, precommitment hash | Immutable once registered |
| `Experiment` | Design, eligible population, intervention, comparator, safety, primary and secondary outcomes, stop conditions | Linked to hypotheses |
| `Observation` / `Outcome` | Raw measurement, method, missingness, uncertainty | Appended, never edited; observation ≠ cause |
| `LearningRecord` | Prior prediction, observation, alternatives considered, measured outcome, causal certainty, context conditions, unexpected effects, failed attempts, next rule, exceptions, impact on human capability | Append-only |
| `Skill` | Trigger, prerequisites, procedure, contraindications, counterexamples, abort criteria, evaluation tests, last validated, evidence | Two gates: knowledge and execution |
| `LearningTask` / `LearningAttempt` / `FeedbackEvent` / `MasteryEstimate` / `CapabilityEvidence` | Human learning loop (§3.8) | Unaided attempts recorded before assistance |
| `ProspectiveTrigger` | Conditions, linked records, expiry, review cadence, advisory authority | No irreversible action |
| `MemoryItem` | Typed memory (§3.9) with retention and promotion basis | Per-type rules |
| `PolicyDecision` | `accept_for_purpose`, `new_region_research`, `quarantine`, `refuse`, with reason and purpose | Auditable |
| `Event` | Append-only transition with `event_id`, kind, subject, occurred_at, recorded_at, principal, method_version, parents, source_refs, schema_version, payload_hash, reason, consent_scope | Hash-chained |

Keep the existing `theory`, `mechanism`, `problem`, `decision`, `prediction`, `experiment` and `skill` names as specialisations where they help, but map them onto the typed model above.

### 3.4 Epistemic type system

Use the blueprint's categories, purpose-dependent and versioned:

`SOURCE_REPORT` · `SOURCE_ATTRIBUTED_CLAIM` · `INTERPRETATION` · `EXTERNAL_EVIDENCE` · `EXPLANATORY_HYPOTHESIS` · `TRANSFER_HYPOTHESIS` · `TESTED_FINDING` · `PRACTICE_CANDIDATE` · `AUTHORIZED_SKILL` · `NORMATIVE_POSITION` · `OPEN_QUESTION`

An object can carry different statuses for different purposes. The four-way gate gives the route, not the truth:

| Route | Meaning |
|---|---|
| `accept_for_purpose` | Evidence and scope support this specific use |
| `new_region_research` | Plausible, unfamiliar, important, under-covered; allocate investigation; not "wrong" |
| `quarantine` | Attribution, poisoning, source, conflict or applicability concern; not usable as authority |
| `refuse` | Rights, safety or policy requirement fails |

Separate axes, never averaged: `provenance_status`, `extraction_quality`, `semantic_support_status`, `evidence_quality`, `logical_support`, `causal_support`, `empirical_evidence_status`, `transfer_status`, `novelty_status`, `authorization_status`, `human_review`, `uncertainty` (controlled vocabulary: `unobserved`, `source_ambiguous`, `low_independence`, `inconsistent`, `out_of_scope`, `untested_transfer`, `not_identifiable`, `normative_dispute`, `out_of_distribution`).

### 3.5 Relations, time and provenance

**Relation record.** Every important link is a first-class object:

```
relation_id, subject_id, predicate (controlled vocabulary), object_id,
context {domain, scope, conditions[]}, rationale,
evidence_refs[], source_refs[], epistemic_status,
extraction {origin, method_version, confidence: null-or-calibrated},
review {status, reviewer}, valid_time {from, until},
recorded_at, supersedes, retracted_by
```

Predicates use the blueprint's full vocabulary: `QUOTES`, `ATTRIBUTES_TO`, `INTERPRETS`, `SUPPORTS`, `CONTRADICTS`, `QUALIFIES`, `DEPENDS_ON`, `USES_WARRANT`, `BACKED_BY`, `COUNTEREXAMPLE_TO`, `COREFERS_TO`, `FUNCTIONALLY_ANALOGOUS`, `STRUCTURALLY_MATCHES` (reserved for reviewed mappings), `CANDIDATE_RESEMBLANCE`, `PROPOSES_CAUSAL_LINK`, `PREDICTS`, `TESTS`, `OBSERVED_AS`, `SUPERSEDES`, `INSPIRED_BY`, `RELEVANT_WHEN`, `CONTESTED_BY`. A predicate exists only if a code path creates it.

Binary relations by default. N-ary relations are modelled as their own objects, not forced into pairs.

**Time.** Store separately: event time, publication time, ingest time, belief-valid interval, and decision time. Retrieval supports "as known at time T" using these, not record-update time alone.

**Derivation DAG.** Every synthesised answer, theory, idea and decision carries its path: `source occurrence → assertion → proposition → evidence assessment → synthesis step → conclusion`, with the assumptions introduced at each step. A citation list is not a derivation.

**Source families.** Copies, re-uploads and model paraphrases of one source count as one family. A model's paraphrase is never an independent witness.

### 3.6 Decision contract and products

A Decision Contract carries: `owner`, `question`, `why_it_matters`, `options`, `constraints` (with provenance), `values`, `key_assumptions`, `evidence_snapshot` (the evidence IDs and their versions at decision time), `evidence_needed`, `critical_unknown`, `reversibility`, `human_approval` requirement, `stop_search_when`, `next_step`, `decided_at`, `resolved_at`.

Three products are first-class outputs:

- **Decision Brief:** alternatives, evidence, material uncertainty, recommendation, rationale, provenance.
- **Assumption Challenge:** the load-bearing belief, strongest counter-evidence, alternative frames, the user's decision rights.
- **Information Deficit Card:** what is missing, why it matters, the cheapest credible way to reduce it, and when to stop.

The system is rewarded for recommending no action, no notification, no further research, or a human conversation when that is best justified.

### 3.7 Problem-to-Change Case (the organising unit)

Every substantive piece of work produces one versioned Case:

1. Independent problem model (before any source vocabulary is exposed)
2. Diagnosis and contradiction map (stuck class, maintaining force, conflicting requirements)
3. Candidate mechanisms (from the Mechanism Observatory)
4. Transfer map (correspondence, invariants, disanalogies, negative transfer)
5. Intervention candidates (what could actually change, expected benefits and side effects)
6. Evidence and independent critique (support, contradiction, speculation, prior art)
7. Decision and discriminating test (smallest test that separates this from the strongest alternative, with kill criteria)
8. Observed result and capability gained (what happened, what changed in the model, whether the human can now reproduce or transfer it)

A missing step stays visible as a gap. It is never filled by plausible prose.

### 3.8 Human capability engine (TRACE Learning)

- **Unaided first.** For selected tasks, the person makes a short independent attempt or prediction before AI-generated options are shown. The attempt is recorded.
- **Assistance modes:** Executor (bounded task, shows evidence), Collaborator (exposes choices and assumptions), Coach (scaffolds the person's own reasoning), Examiner (tests recall, explanation, discrimination, transfer), Independent Challenge (new problem, no answer first).
- **Learning loop:** Attempt → Feedback → Explanation → Retrieval → Contrast → Transfer → Delayed reassessment.
- **Exercises per knowledge object:** define from memory (recall), explain why it works (explanation), distinguish it from a rival (discrimination), rebuild the causal diagram (model reconstruction), identify a counterexample (critical understanding), apply to an unfamiliar problem (transfer), predict an outcome (generative understanding).
- **Scheduling.** Spaced retrieval for recall, using an FSRS-compatible adapter. Transfer and explanation are measured separately. FSRS is not treated as proof of transfer.
- **Scaffold fading.** Assistance reduces as unaided performance improves. Dependence is measured, not assumed away.
- **Feedback tiers.** Read, save, or share is attention, not evidence. Adoption is influence, not benefit. Only controlled or credible comparisons count as evidence of effect. Clicks and model self-praise are never primary reward.
- **Capability monitoring.** Periodic unaided tests, and an alarm if unaided judgment declines while AI-assisted output improves.

### 3.9 Memory and context

**Storage tiers.** Tier A: immutable sources and revisions. Tier B: epistemic graph (typed objects, relations, decisions, experiments), rebuildable from A and the journal. Tier C: serving projections (search indexes, summaries, embeddings, concept views). Tier C is a cache. Never mistake an embedding or summary for evidence.

**Typed memory.** Episodic, semantic (current beliefs, versioned on change), procedural (tested procedures, revalidated when conditions change), reflective (attempt patterns, negative cases kept), prospective (triggers), resource (documents to reopen), goal (human-owned), agent-performance (shadow-tested before promotion). Each type has its own promotion basis and retention rule.

**Consolidation rule.** Summaries are never the only copy. Consolidation reopens source evidence, keeps version history, and audits what was removed. Frequent mention never upgrades a claim to fact.

**Context compiler.** Inputs: task type, decision or problem binding, question, stakes, budget, user permissions, required claim status, target domain, known counter-examples. Outputs: source evidence, speaker attributions, interpretation choices, theory and mechanism candidates, negative cases, known failures, novel opportunities, missing evidence, staleness, permitted tools, packet version, derivation trail.

Rules: resolve permissions first; deduplicate by source family; always retrieve the strongest known contradictions; keep interpretation and invention labels visible; enforce budget by progressive disclosure (L0 summary → L1 structure → L2 full passages), never by silent deletion; invalidate the packet when a material source or belief changes.

**Shadow option portfolio.** Ideas that current goals do not justify are kept with their mechanism, activation conditions, cost of keeping them alive, and triggers. A shadow option is a real alternative path. A trigger is a reminder. They are different objects.

**Prospective triggers.** Typed conditions, linked records, expiry, review cadence, and advisory authority only. Notifications only when expected benefit is high and attention budget allows.

### 3.10 Retrieval

- **Channels:** exact (SQLite FTS5), concept (definitions, aliases, hierarchy), functional, structural, contradiction, evidence (passage and claim-evidence links), temporal (as-known-at-T). Semantic embeddings are an optional adapter, enabled only when a benchmark shows recall gain.
- **Routing:** a light intent classifier chooses channels per question. Definitions go to concept retrieval. Evidence questions go to exact passages. Contradiction questions go to comparisons. Transfer questions go to functional and relational structure.
- **Fusion:** transparent rank fusion. Ranking is never presented as confidence, and never overrides applicability or evidence checks.
- **Derivation:** every returned item shows why it was retrieved.
- **Blocking:** a search may legitimately return "none of these maps well".

### 3.11 Invention

**Breakthrough compiler.** A typed, inspectable workflow:

1. Build the dossier (stated problem, goal ladder, success judge, constraints with provenance, failed attempts and why, actors, vetoes, unknowns, reversibility, authority).
2. Diagnose why it persists. Classes: wrong representation, false constraint, hidden constraint, contradiction, reinforcing incentive, missing fact, capability gap, value or legitimacy conflict, coordination problem, genuine formal wall, wicked problem, ill-posed objective.
3. Generate independent reframings. Twelve operators: invert failure, change unit, change actor, change timing, change boundary, change objective, remove an element, ideal final result, distant causal isomorph, push a quantity to an extreme, generalise, dissolve the generating conditions. Each reframe must still serve the actual human goal.
4. Compile the contradiction, and try separation by time, space, condition, scale or level.
5. Run controlled collisions with four exploration policies: Fresh, Deepen, Refresh, Challenge. Generate mechanisms in separate contexts before mixing them.
6. Attempt far transfer through explicit structure mapping, never vocabulary.
7. Compose only when each component contributes a distinct function, and compare against the best single proposal.
8. Run an independent red team with eight attacks: source fidelity, structural transfer, causal alternative, stakeholders and legitimacy, prior art, implementation and harm, experiment design, system incentive. The automated version is labelled as such. An independent human pass is required before any high-stakes use.
9. Converge: separate known, inferred, plausible, speculative and unknown. Choose a discriminating test and define kill criteria. If nothing survives, the output is an Information Deficit Card or "no viable candidate yet". Never a forced breakthrough.
10. Record which operators helped, in which problem class, at what cost. Shadow-test any change to the operator policy.

**Transfer ladder.** Each rung needs its own evidence:

`candidate resemblance` → `structurally mapped` → `conditional transfer hypothesis` → `tested in target context` → `replicated or context-validated`

**Transfer map.** Source and target roles, mapped relations and higher-order relations, preconditions and invariants, unmapped components on both sides, contradictions and disanalogies, boundary conditions and resource differences, causal alternatives, negative-transfer scenarios, a target-adapted intervention, predictions and falsifying observations. Diagnose the target problem before exposing the source mechanism, or source vocabulary contaminates the diagnosis.

**Literature discovery and prior art (later).** Open discovery, closed discovery between two known concepts, two-node gap tests, temporal discovery in older literature, cross-lingual discovery preserving original terms, and prior-art screening. Each produces an Evidence Coverage Report: what was searched, languages, databases, date range, exclusions, known gaps, and coverage confidence. "No prior art found" never means "novel". Live connectors only with explicit authorisation and privacy-minimised queries.

**Outputs.** Reframing brief, mechanism transfer card, alternative portfolio, invention brief (design, prior art, critical assumptions, risks, test), discovery question (a newly exposed problem, possibly unrelated to current goals).

### 3.12 Experiments and outcomes

- **Preregister** substantial predictions before the first observation, with a precommitment hash computed by the storage service.
- **Prefer discriminating tests.** When two theories predict the same ordinary outcome, look for an observation where they diverge.
- **Causal caution.** Predictive association does not justify intervention. Causal language is weakened when identification is weak. Observational conclusions are labelled as observational.
- **Learning record** after every test (see §3.3). Distil skills from patterns across cases, not from single dramatic anecdotes. A lucky success is not a skill.
- **Self-improvement only through shadow-tested policy changes** (see §3.14).

### 3.13 Governance, security and autonomy

**Threat model.** Prompt injection, memory poisoning, data exfiltration, unauthorised actions, source laundering, feedback gaming, mistaken attribution.

**Mandatory controls:**

1. Untrusted-source isolation: excerpts are quoted and typed as data; no retrieved passage becomes an instruction.
2. Explicit per-source rights: copyright or licence, origin, consent, retention, export restrictions, and an attestation record. Respect platform access rules.
3. Least privilege: separate read from write, send, and execute permissions. Separate public research from private application context.
4. Human approval for consequential actions: purchases, communications, employment, health, deletion, foundational goal edits.
5. Purpose-limited retrieval: user context is not sent to external search providers for personalisation.
6. Provenance and replay: audit important writes and action attempts; keep model and policy versions.
7. Memory-poisoning checks: flag new high-authority instructions, self-referential content, forged sources, synthetic citations, conflicting lineage.
8. Secrets never in version-controlled config.
9. Sandboxed experiments with quotas.
10. Data controls: export, deletion, expiry, correction, deletion propagation to derived caches.
11. Supply-chain review of any imported code, with licence checked at the exact version.
12. Red-team tests: document injection, forged quotations, conflicting speaker identity, malicious captions, task hijacking, cross-tenant retrieval, system-prompt extraction.

**Autonomy ladder.** Explicit, enforced levels:

| Level | Examples | Gate |
|---|---|---|
| Read | Analyse an authorised corpus | Source and privacy permissions |
| Suggest | Draft a brief, hypothesis, or practice card | Evidence labels visible to the user |
| Prepare | Research plan, experiment spec, unsent draft | Risk limits, explicit proposed actions |
| Simulate | Sandboxed reasoning or code tests | Isolated tools, cost and safety limits |
| Act reversibly | Update approved working notes, low-risk scheduled task | Narrow authorisation, audit |
| Act consequentially | Publish, send, purchase, delete, alter records, high-stakes recommendation | Explicit informed approval plus specialised safeguards |

Better analysis never grants permission to act. The default across the system is advisory.

**Human values.** The system may challenge goals and map trade-offs. It never silently substitutes its own values, and it never claims empirical evidence settles a moral dispute. Banned design move: inferring a person's developmental stage, hidden motives, psychiatric state, personality, or private identity from conversation. Analyse expressed arguments and publicly documented context only.

### 3.14 Watchdog and self-improvement

**Watchdog (independent).** Keeps private evaluation examples. Receives raw audit evidence, not agent-summarised logs. Checks:

- Unsupported claims and lost qualifications
- Type laundering (mined or generated items carrying claim-level or tested statuses)
- Unanchored claims and span mismatches
- Reject audits: random samples of rejected and low-ranked material, scored by the stratified estimator in blueprint §11.7 (`P̂ = Σ_h (N_h / ΣN) · (v_h / n_h)`), with uncertainty and labeller agreement reported. Flip rate is not a false-negative rate.
- Minority-view suppression and source-family copying
- Answer drift after model or index updates
- Leakage from private or connected sources, and suspicious instructions inside documents
- Whether unaided human judgment is improving or declining
- Authority gaps: a skill without a separate human authorisation record

The watchdog can halt unsafe promotion. The optimiser that produces output cannot switch it off.

**Self-improvement.** Allowed targets: retrieval mix by task class, sampling allocation, which interpretations get expert review, trigger timing, which model handles which input, packet size and depth. Not editable by the system: human values, consent, external rights, source lineage, hard risk gates, the watchdog's evaluation authority.

Every proposed change: baseline → develop on training data → test on held-out sources and tasks → blinded comparison → shadow deployment → check for negative effects → promote with version and rollback.

**Multi-rate control.** Tactical, strategic, and foundational reviews run at different rates. Foundational changes (goals, values) require explicit human deliberation, not a threshold.

**Budgets.** Evidence integrity, action risk and authorisation, human attention, experiment and compute, structural change. Each budget has an observable and a defined response (quarantine, approval, batch or silence, narrow the investigation, dwell period). Use hysteresis where signals are noisy. Hard risk violations override dwell periods.

### 3.15 Outcome of mining

Mining (intake, candidates, verification) is the input layer. Its outputs are `SOURCE_REPORT` candidates with verbatim spans and kind hints. Nothing from mining carries a claim-level status until an evidence assessment and human review have run.

---

## 4. Intake, rights, and mining

**Intake.**
- Bundle importer (CSV or JSON manifest) with per-entry id, title, rights basis, attestation, model-use and export flags, retention.
- Transcript provenance class on every source.
- Creator-provided captions or transcripts, user-supplied files, or licensed transcription. Where access fails, record the gap by name. Do not bypass platform access controls, regardless of content rights.
- Idempotent, resumable, with explicit failure states (`DISCOVERED`, `ACCESSIBLE`, `CAPTURED`, `PARTIAL`, `BLOCKED`, `REVIEWED`, `EXPIRED`, with reason and time).
- Corpora stay out of git. Raw transcripts live in a private store or a local workspace. The repo carries code, schemas, and manifests without the content.

**Segmentation.** Hierarchy: video → chapters → argument episodes → speaker turns → sentence-bounded spans with context windows. Boundaries are retrieval aids, not truth boundaries. Median span length should be a few sentences; the Stoa median of 114 words is too long for a claim.

**Coverage map.** Per source and per corpus: topics, speakers where known, potential arguments, skipped or visual-only passages, transcript provenance, quality flags. The first screen of any corpus is its coverage and gaps.

**Candidate mining.**
- Deterministic, versioned marker patterns generate candidates.
- Each candidate is stored as `SOURCE_REPORT` (the quote) with `kind_hints`. Never a fixed claim status.
- Per-source and per-kind caps prevent one guest dominating.
- Every quote is verified against its stored span before save. The check I ran on the Stoa atlas passed 7,010 of 7,010 with transcripts available. Treat the verbatim test as a regression gate.
- The scoring formula is explicit, versioned, and described as quotability and diversity. It is never called wisdom.
- Optional provider-assisted refinement goes through the existing proposal validator. Its output is untrusted and discarded whole if malformed.

**Gold set.** Blinded labelling sheet with a rubric. Two annotators per sample, disagreements recorded. Precision and recall per kind with intervals. The regex miner is a baseline, not a judge.

**Reproducibility.** Headline counts must be regenerable from the packaged data. A rebuild that yields fewer records than the headline is reported as a defect, not hidden.

**Pilot corpus.** The Stoa transcripts, with the user's rights recorded. Held out by whole episodes and guests, not random spans. Kept local, out of the public repo.

---

## 5. Evaluation and evidence

### 5.1 Tracks, each with independent data

| Track | Test | Key metrics |
|---|---|---|
| A. Source fidelity and interpretation | Long transcripts and visual lectures with independently prepared anchors, speakers, positions, negations, caveats, changed views, minority views | Anchor accuracy, speaker attribution, quote verification, qualification preservation, argument completeness, disagreement preservation, cross-language fidelity, reviewer correction time |
| B. Retrieval and theory | Questions needing facts across spans, disagreements, mechanisms, omissions, prior versions, minority cases | Recall@k, precision of verified spans, counter-evidence recall, source-family diversity, valid scope, negative-transfer detection, missed-value rate |
| C. Invention | Real stuck problems collected independently, with hidden constraints and optional validated examples; includes semantically distant and no-transfer cases | Structural diversity, claim-level novelty after prior-art checks, mapping credibility, feasibility, negative-case awareness, cheapest-test quality, blinded preference vs baselines, eventual outcomes |
| D. Decision and outcome lift | Real decisions with timestamped alternatives, evidence, stakes and outcomes | Regret proxy, option coverage, appropriate research-stop rate, forecast calibration, unsupported execution recommendations, time and expense, validated results |
| E. Human capability and legitimacy | Assisted and unassisted sessions over time | Unaided reasoning and creative quality, explanation without the AI, fairness, inclusion of dissent, attention cost, dependency |

### 5.2 Ablation matrix

| Config | Adds | Question |
|---|---|---|
| A0 | Strong baseline: reasoning model, authorised transcript retrieval, exact citations | Control |
| A1 | Genre-sensitive dialogue, argument graph, interpretation alternatives | Better fidelity? |
| A2 | Scoped theories, evidence polarity, negative cases | Better conditional transfer? |
| A3 | Functional, structural, causal indexes | More distant-domain recall? |
| A4 | Reframing, collisions, adversarial critique | More useful structural diversity? |
| A5 | Predictions, experiments, conditional skills | Gains persist and improve future tasks? |
| A6 | Triggers, VOI, multi-rate control, capability policies | Net longitudinal value and attention efficiency? |

Report marginal gains (A3 − A2) and cost-adjusted gains. Include a direct end-to-end LLM prompt control, to test whether the intermediate objects help at all.

### 5.3 Baselines

1. Strong general-purpose LLM with a careful prompt
2. LLM with high-quality cited RAG
3. The previous Wisdom implementation
4. Conventional brainstorming or expert problem solving
5. TRIZ-assisted baseline
6. Analogical retrieval baseline
7. Human expert, where feasible

Comparable information, time, and compute budgets. Blinded reviewers who do not know which system produced an output.

### 5.4 Acceptance scorecard

Proposed gates, not published benchmark thresholds. Thresholds are derived from consequences and measured error rates, not chosen for sounding strict.

| Gate | Condition to promote a subsystem |
|---|---|
| Evidence preservation | No systematically unattributed or invented quotations in audited critical output |
| Argument fidelity | Beats a transcript-only baseline on adjudicated qualification, rebuttal, and speaker-position cases |
| Retrieval | Statistically and practically meaningful added verified recall at acceptable cost, including far-domain cases |
| Invention | Higher blinded usefulness and structural diversity than brainstorming, with no significant rise in harmful unsupported suggestions |
| Memory | Restores relevant context and correct prior versions at lower cost than naive replay |
| Routing | Lower compute and review without losing valuable findings |
| Learning | Holdout gains after feedback, with no label leakage or evaluation gaming |
| Governance | Permission and injection tests pass before any external action is authorised |
| Human capability | No unacceptable degradation in unaided judgment or independent exploration |
| Operations | Reproducible runs, defined recovery, exportability, observed failure rates, bounded expense |

### 5.5 Measurement hygiene

- Hold out whole episodes, authors, themes, and target domains. Not random records.
- Blinded judging. Never give judges the system identity.
- Keep evaluation material and outcome labels away from the agents that tune against them.
- Separate "interesting", "new", "feasible", and "works". Score them separately.
- Do not compress tracks into one headline score. A gain in one track that hides a loss in another is reported as a trade-off.
- Model-judge preference is not evidence of quality.
- Measure hidden loss: sample what the system did not surface, using a separate audit frame.
- Calibrate probabilities only where real probabilities exist, and use the uncertainty taxonomy where they do not.

### 5.6 Kill criteria

Reconsider the central design if:

- Structural transfer does not beat simpler retrieval at comparable cost.
- Mechanism maps are too expensive or subjective for humans to review.
- TRIZ and multi-lens analysis do not improve outcomes over a simpler workflow.
- Generated inventions score high on novelty and low on feasibility and usefulness.
- Independent reviewers cannot validate evidence and transfer reasoning reliably.
- The learning mode fails to improve unaided performance, when that is part of the promise.
- Operational complexity and attention cost exceed measured value.

Also kill or rework any component whose outputs are merely attractive, rediscovered, or model-judge pleasing.

---

## 6. User experience

**Principles.** Coverage before insight. Every claim links to its span. Generated content is visibly separate. Task-specific views, not one knowledge hairball. Quiet by default.

**Views.**
- **Coverage home:** what was accessible and processed, what is partial, what was blocked and why, the named gaps, source rights status.
- **Source trail:** source → spans → timestamp links → transcript quality flags.
- **Wisdom atlas (faithful):** supported agreement and disagreement, definitions, argument changes, tensions, scope conflicts, explicit gaps. Can say "these conversations do not establish consensus".
- **Generative atlas (separate panel):** new interpretations, problem classes, distant-domain matches, candidate interventions, each labelled `GENERATED_HYPOTHESIS` with its counter-argument trace. Never cited back into the faithful atlas.
- **Problem Observatory and Mechanism Observatory.**
- **Case view:** the eight-step Problem-to-Change Case, with gaps shown.
- **Decision and experiment workbench:** contracts, briefs, deficit cards, predictions, outcomes, learning records.
- **Capability studio:** learning tasks, unaided attempts, mastery trends, scaffold level.
- **Review queue:** what needs a human decision, with reasons and costs.
- **Audit view:** rejects, quarantines, drift, watchdog findings.

**Accessibility.** Keyboard operable, screen-reader labels, responsive at phone width, no horizontal page scroll.

**Verification.** Browser checks on desktop and phone widths in a browser-enabled environment (tracker: WF-BROWSER).

---

## 7. Data integrity and schema enforcement

- Validate every write against versioned schemas at the storage boundary, using a stdlib validator. Reject unknown kinds, unknown predicates, and missing required fields.
- Migration tests for every schema version. Old records stay readable.
- Span and prediction identity is immutable. Outcomes are appended.
- Idempotency keys on every write. Retries are bounded and explicit.
- Event journal records: `event_id`, `kind`, `subject_id`, `occurred_at`, `recorded_at`, `principal`, `method_version`, `parents`, `source_refs`, `schema_version`, `payload_hash`, `reason`, `consent_scope`, with hash chaining. Hash chains detect alteration, not falsehood, and the docs must say so.
- Event kinds from the blueprint's critical list are emitted by real code paths, and a test checks that each one is produced.
- Deletion propagates to derived caches. Export keeps rights filtering.

---

## 8. Operations

- Workflows are state machines for long tasks, with retries, explicit failure, and manual recovery. No untracked chains of model calls.
- Resource budgets and wall-clock limits per job.
- Structured logs and metrics for failure rates, cost, and latency.
- Reproducible runs: pinned versions, recorded model identities, packet versions.
- Backup and restore drill, documented and executed.
- Single-user local deployment first. Multi-user and hosting are deferred until a validated need and an authority model exist.

---

## 9. Migration from the current draft

The current draft has real foundations: exact spans, rights, the journal, decisions, preregistration, the watchdog's structural checks, and 115 passing tests. It also has known defects: misleading labels, a primitive edge model, no schema enforcement, lexical matching presented as structure, and no mining, learning, or evaluation evidence.

**Approach.** Build the v2 core on a branch. Port the kept foundations with their tests. Rebuild the epistemic model, mining, invention and learning on the new core. Migrate records through explicit, tested migrations. Keep v1 readable and export-compatible. Retire the v1 paths only when v2 passes the same tests plus the new ones.

**Honest-label fixes first.** Rename `semantic` to `lexical`. Replace `STRUCTURALLY_MATCHES` for lexical matches with `CANDIDATE_RESEMBLANCE`. Add a type-laundering check. These are cheap, and they stop the system overstating itself while the rebuild proceeds.

---

## 10. Phases, with exit criteria

Each phase has a tracker entry, an acceptance test, and an independent review before the next phase starts. Work is done in isolated worktrees pinned to a committed base, following `AGENTS.md`.

**Phase 0. Honesty and contracts.** Duration: short.
- Relabel lexical retrieval and lexical matching. Add type-laundering checks.
- Freeze the v2 object model, predicate vocabulary, epistemic types, and event kinds as versioned contracts.
- Exit: no interface, record or export implies semantic, structural, causal, or novelty validation that did not happen. Contracts reviewed.

**Phase 1. Intake and rights.**
- Bundle importer, rights attestation, transcript provenance classes, failure states, coverage report, corpora kept out of git.
- Exit: a 724-entry manifest imports idempotently, every gap is named, and rights records appear on every source.

**Phase 2. Mining and gold set.**
- Segmenter, marker-based candidate miner, caps, verbatim gate, scoring formula, reproducibility check.
- Blinded gold sheet, two annotators, per-kind precision and recall with intervals, regex baseline.
- Exit: the miner is deterministic; verbatim check passes on every candidate with a span; per-kind numbers are reported with uncertainty; no candidate carries a claim status.

**Phase 3. Canonical core.**
- Typed objects, qualified relations with real creation paths, bitemporal fields, derivation DAG, schema enforcement, event contract, source families, source occurrences, assertions, propositions, evidence items.
- Exit: every proposition traces to assertions and evidence; every relation is inspectable and validated; "as known at T" queries work; migration tests pass.

**Phase 4. Interpretation and dialogue.**
- Interpretation lattice, reader types, genre and speech-act routing with per-genre checks, reflexive alternative readings.
- Exit: a fixture with two supported readings keeps both through the context packet; neither is promoted; genre routing changes the verification template as specified.

**Phase 5. Evidence assessment and synthesis.**
- Evidence assessment record with design, bias, directness, independence, quality dimensions; multi-field binding check (all fields refer to the same study).
- Concept layer with per-source definitions; theory cards with LAW–SCOPE–EVIDENCE structure, negative cases, failure conditions.
- Exit: theory cards from several sources preserve distinct definitions, conflicts and dissent; the watchdog's type checks pass.

**Phase 6. Problem-to-Change Case and invention.**
- Case object and view; stuck-class enum; all twelve reframing operators; four collision policies; transfer ladder; transfer maps; NO_JUSTIFIED_MATCH as a valid result; automated red team labelled as automated.
- Exit: a case with a deliberately missing step shows the gap; the compiler produces a no-match result on a fixture with no valid transfer; transfer ladder rungs require their own evidence.

**Phase 7. Decision intelligence.**
- Complete Decision Contract with evidence snapshot; Decision Brief, Assumption Challenge, Information Deficit Card; VOI stop rule; decision time recorded.
- Exit: a decision made from a past snapshot reproduces the evidence the decider had; the system can recommend no further research with recorded reasons.

**Phase 8. Experiments and learning record.**
- Discriminating-design step; learning record with all fields; causal-language rules tied to design; prediction and outcome appended, never edited.
- Exit: a registered prediction cannot be altered; a learning record lists alternatives and failed attempts; causal wording is downgraded for observational designs.

**Phase 9. Human capability engine.**
- Learning tasks and attempts; unaided-first step; assistance modes; delayed reassessment; scaffold fading; feedback tiers enforced in code; capability monitoring.
- Exit: unaided attempts are recorded before assistance on selected tasks; clicks are not reward; capability trend is visible per person.

**Phase 10. Memory, context and retrieval.**
- Typed memory with retention; shadow option portfolio; goal-challenge tiers; context compiler inputs and outputs; L0/L1/L2 disclosure; derivation trail; per-episode caps; FTS5 channels with routing.
- Exit: packets reproduce across re-indexing; deduplicate by family; keep contradictions; respect permissions and as-of time.

**Phase 11. Governance, watchdog and self-improvement.**
- Autonomy ladder enforced; injection and poisoning tests in CI; reject audits with the stratified estimator; drift, suppression, and copying checks; shadow-tested policy changes with rollback.
- Exit: unsafe promotions are refused in tests; policy changes can be rolled back; the watchdog reports on its own inputs.

**Phase 12. Evaluation and evidence.**
- Gold sets for each track; baselines run under equal budgets; blinded review packets; ablation runs; reporting that includes losses.
- Exit: each gate in §5.4 has a result, positive or negative, with uncertainty. No self-grading.

**Phase 13. Product hardening.**
- Browser verification; accessibility; backup and restore drill; operational metrics.
- Exit: recovery and export tested; browser checks pass on desktop and phone widths.

**Later, only when measured.** Embeddings, external research connectors, media and speaker diarisation, graph databases, multi-user operation.

Phases 2 and 12 produce the evidence that every other phase is judged by. Start them early, even though their completion depends on people.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Mined quotes read as findings | Candidates stored as `SOURCE_REPORT` with hints; claim statuses blocked until assessment and review |
| Epistemic labels assigned by pattern | Type-laundering check; labels from evidence and review only |
| Transcript errors read as wording | Provenance class on every source; ASR-derived quotes flagged; reading for argument, not exact wording |
| Rights violation | Attestation required; corpora out of git; no access-control bypass; export filtered by rights |
| Over-generation of invention | Generated panel separate; kill criteria; blinded evaluation |
| Lexical similarity mistaken for transfer | Transfer ladder; `CANDIDATE_RESEMBLANCE` label; structural maps required |
| Learning replaced by dependence | Unaided-first tasks; capability monitoring; scaffold fading; kill criterion |
| Self-grading and reward hacking | Blinded independent labels; held-out sets; watchdog independence; shadow policy changes |
| Complexity without value | Ablations; cost-adjusted reporting; add-on-evidence rule |
| Schema drift and silent data loss | Boundary validation; migration tests; rebuild-from-package check |
| Scope creep into autonomy | Advisory default; ladder enforced; no external actions authorised |

---

## 12. Non-goals

- A wisdom score or any single headline "wisdom" number.
- A swarm of autonomous agents, or a prompt-driven multi-agent system with no independent method behind each agent.
- Inference of personality, developmental stage, hidden motives, or psychological state from conversation.
- Autonomous external actions, purchases, communications, or deletions without explicit approval.
- Circumventing platform access controls to obtain content, whatever the content rights.
- A graph database, vector store, or additional service before a measured need.
- Multi-tenant hosting or production deployment before validated need and authority.
- Treating passing tests, synthetic fixtures, or model-judge scores as evidence of real-world value.

---

## 13. Decisions needed from you

1. **Pilot corpus location.** Keep the Stoa transcripts in a private local store, or a private repository? They should not go into the public `shapefuture/wisdom` repository.
2. **Branch strategy.** Confirm the v2 core is built on a new branch and v1 stays as the readable baseline.
3. **Annotators.** Who will label the gold sets and serve on blinded panels? Without them, Phases 2, 5, 6 and 12 cannot produce evidence.
4. **Model provider.** Which model gateway, if any, is authorised for provider-assisted steps, and which sources are cleared for model processing?
5. **Acceptance thresholds.** Who sets the numeric gates in §5.4? The plan leaves them open on purpose.
6. **Human capability scope.** Which tasks and people will participate in the capability studies, and under what consent?

---

## 14. Immediate next actions

1. Create tracker entries for Phases 0–2, with acceptance tests as written in §10.
2. Open the v2 branch from the latest committed base; create isolated worktrees per workstream.
3. Land Phase 0 relabelling and the type-laundering check first. These are small and remove current overstatement.
4. Start the blinded gold sheet and rubric in parallel, since annotator time is the long pole.
5. Run Phase 1 intake on the rights-attested pilot corpus, keeping raw content out of git.
