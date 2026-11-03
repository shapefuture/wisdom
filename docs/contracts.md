# Frozen implementation contracts v1.0.0

Python 3.12+, no runtime dependency installation. All services accept a StorePort and optional ProposalProvider. Import ports/errors, not a concrete store. Runtime composition is the sole concrete binding.

## Records and storage
Envelope: {id, kind, version, created_at, updated_at, data}. Data is JSON. Kinds are singular snake_case (source, span, claim, argument, interpretation, theory, mechanism, problem, idea, decision, prediction, experiment, outcome, learning, skill, trigger, trace, goal, assessment, policy, job). IDs are opaque strings. All methods are in wisdom/ports.py. Version starts at 1. put is append-only versioned with compare-and-swap; immutable records reject revision. Links: {id, source_id, target_id, relation, polarity, data}. Every mutation is journaled; idempotency keys bind to exact request payload. list hides tombstones. get raises NotFound. Persistence supports :memory: and file SQLite.

## Service slots (root freezes these signatures)
- wisdom.store.Store(path=":memory:", raw_dir=None) implements StorePort.
- wisdom.governance.Governor(store).assess(record_id, purpose="research", stakes="low") -> assessment dict; .authorize(action, context) -> dict with allowed/reason. Separate support from execution.
- wisdom.ingest.IngestService(store).ingest(payload) -> source envelope; .spans(source_id) -> span envelopes; .coverage(source_id) -> dict.
- wisdom.evidence.EvidenceService(store, provider=None).analyze(source_id) -> {claims:[],arguments:[],interpretations:[],warnings:[]}; .review(claim_id, payload) -> claim envelope; .verify_span(span_id) -> dict.
- wisdom.theory.TheoryEngine(store, provider=None).build(payload) -> theory envelope; .mechanism(payload) -> mechanism envelope.
- wisdom.invention.InventionEngine(store, provider=None).problem(payload) -> problem envelope; .forge(problem_id, payload=None) -> {problem,diagnosis,ideas:[],missing_evidence:[]}; .red_team(idea_id) -> dict. Output hypotheses, never validated novelty. Preserve no-match results.
- wisdom.learning.DecisionService(store).create(payload) -> decision envelope; .approve(decision_id,payload) -> decision envelope; .voi(payload) -> dict.
- wisdom.learning.OutcomeLab(store).predict(payload) -> prediction envelope; .experiment(payload) -> experiment envelope; .observe(payload) -> outcome envelope; .learn(prediction_id) -> learning envelope; .skill(payload) -> skill envelope; .promote(skill_id,payload) -> skill envelope.
- wisdom.retrieval.RetrievalService(store).search(query,lens="semantic",limit=20) -> list; .compile(payload) -> context dict; .lineage(record_id) -> {nodes:[],edges:[],gaps:[]}.
- wisdom.workflows.WorkflowService(store).route(payload) -> dict; .run(kind,payload,key=None) -> job envelope; .retry(job_id) -> job envelope.
- wisdom.memory.MemoryService(store).trigger(payload) -> trigger envelope; .evaluate(signals,budget=3) -> {notifications:[],suppressed:[]}; .trace(payload) -> trace envelope; .goal(payload) -> goal envelope.
- wisdom.watchdog.Watchdog(store).audit() -> dict.

## Source payload
{title,uri,text,format:"text"|"srt"|"vtt",source_family,author,rights:{allowed:true,license:"user-provided",private:false,allow_export:true}, idempotency_key?}. No arbitrary URL fetch. Empty/unavailable text stays BLOCKED or PARTIAL with reason; no fabricated transcripts. span data: {source_id,text,start_char,end_char,start_ms?,end_ms?,speaker?,content_hash}. Unicode offsets are Python codepoints, documented in exports. Immutable original/source spans. Claims: {text,source_id,span_ids,epistemic_type:"SOURCE_ATTRIBUTED_CLAIM",qualifiers,speaker,review_status}. Source text cannot override permissions.

## Theory/mechanism/problem payload
Theory {title,claim_ids,scope,explanation,counterexamples,predictions}; mechanism {title,theory_id?,claim_ids,problem_state,intervention,effects,boundary_conditions,contraindications,functional_signature,structural_signature,source_domain}. Problem {title,description,desired_state,maintaining_force,actors,constraints,failed_attempts,domain,stakes,stuck_type}. Ideas include source mechanism IDs, mappings, mismatches, failure hypotheses, cheapest_test, novelty_status:"unchecked", epistemic_type:"TRANSFER_HYPOTHESIS".

## Decisions/experiments payload
Decision {question,owner,options,values,constraints,assumptions,evidence_ids,stop_search_when,stakes}. Approval {choice,approved_by,reason}; it records human choice only, never runs tools. Prediction {statement,metric,expected,direction,horizon,analysis_plan,stop_conditions,hypothesis_id?,experiment_id?,probability?}. It is immutable, timestamped and hashed before observations. Outcome {prediction_id,observed,method,limitations,occurred_at?}. Skill {title,trigger,prerequisites,procedure,contraindications,evidence_ids,abort_criteria,required_authority}; explicit authorization separate from outcome support.

## API
JSON endpoints. GET /api/dashboard, /api/records?kind=, /api/records/<id>?version=, /api/history/<id>, /api/events, /api/search?q=&lens=, /api/lineage/<id>, /api/export?format=json|markdown|argdown, /api/audit.
POST /api/sources; /api/sources/<id>/analyze; /api/claims/<id>/review; /api/theories; /api/mechanisms; /api/problems; /api/problems/<id>/forge; /api/ideas/<id>/red-team; /api/decisions; /api/decisions/<id>/approve; /api/voi; /api/predictions; /api/experiments; /api/outcomes; /api/learning/<prediction_id>; /api/skills; /api/skills/<id>/promote; /api/triggers; /api/triggers/evaluate; /api/trace; /api/goals; /api/context; /api/route; /api/jobs; /api/jobs/<id>/retry.
GET /api/records returns {records:[]}; single record routes return envelope directly. Errors {error,code} with 400/403/404/409/503. Mutating endpoints check same origin, JSON content type and local session CSRF. UI gets token via GET /api/session returning {csrf_token}. Never accept arbitrary record-kind writes.

## Backward-compatible additions

Source rights include allow_model:false by default; model sharing requires explicit true independently of local storage/export. Missing source_family uses original content hash; copies count as one family. Source originals are available as both original_text and text for compatibility. Restricted manifests keep metadata/hashes without denied bytes.

Problems persist allow_model:false unless opted in. Theory/mechanism calls also require payload.allow_model:true for user-entered context. Typed model operations resolve canonical IDs and original span text, rather than scanning strings for IDs; unknown/raw-text model operations deny. Suggested speaker labels are stored as unverified suggestions with speaker_uncertain:true. Distinct content hashes are dedup groups, not evidence of independently known origins.

POST /api/annotations accepts {kind:utterance|argument|interpretation|viewpoint|contradiction,reviewer,data,idempotency_key?}. Dialogue annotations require source_id and exact span_ids. Contradictions require two claim_ids, conflict_type (empirical|semantic|normative|design|philosophical_aporia) and reason; disagreement stays unresolved. POST /api/mechanisms/<id>/discover performs reverse problem matching. POST /api/assess evaluates purpose-specific rights/evidence. Source deletion requires confirm:true and reason, and removes dependent records and caches.

Context accepts as_of (timezone-aware timestamp) to reconstruct recorded versions at a decision time under current access permissions. Returned text is exact source text or explicitly typed analyst/generative text. Full packet metadata and opposing evidence count toward the estimated characters/4 budget; no actual tokenizer accuracy is claimed. Semantic mode is a lexical fallback; embeddings are not installed.

Outcome limitations accept human text or a string array and normalize to an array. Decision approvals are stored under data.approval. Prediction hash is data.preregistration_hash. Promoted conditional skills require reviewer sufficiency plus learning from at least two distinct observed preregistrations, and separate explicit human authorization; they remain non-executable. This evidence floor is an engineering guard, not a scientific sufficiency theorem.

