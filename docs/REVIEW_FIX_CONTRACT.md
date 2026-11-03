# Audit correction contract (candidate 40312598 → next generation)

Confirmed fixes:
- Access must deny missing source lineage, poisoned/quarantined/expired states case-insensitively, and honor derived rights as well as all ancestor-source rights.
- Data removal must use SQLite secure-delete/checkpoint cleanup and truthful logical/physical/backup limits; no guarantee against storage snapshots/forensics.
- Outcome retry keys bind explicit caller timestamps; generated timestamps remain stable on exact retries.
- Provider-suggested speaker identity stays uncertain until supported human annotation. Quotation anchoring alone does not establish speaker identity.
- UI must show analysis warnings, support observed:null with missingness, validate actual evaluation budget, and keep opt-in model consent clear.
- Setuptools package discovery is explicit and CI actions pinned to verified official releases.

Model-sharing protocol (same ProposalProvider.complete(op,payload) signature):
1. Only evidence.propose, theory.build, theory.mechanism, invention.diagnose, invention.forge are supported operations. Unknown operations deny.
2. Evidence requires canonical payload.source_id and canonical span IDs; every source must grant rights.allow_model=true.
3. Theory/build and mechanism creation require user payload.allow_model=true for their user-entered context in addition to all ancestor source grants. Default remains local-only. The UI offers unchecked opt-in controls.
4. Problems persist allow_model:boolean, default false. diagnose and forge run a provider only if canonical problem allows it. Both model payloads carry problem_id for canonical lookup; candidate_mechanisms carry real IDs and all ancestors must permit model use.
5. Root ConsentProvider validates typed operation context and canonical source references, not substring heuristics. For evidence it verifies span text against canonical spans. Raw unknown payload operations are forbidden.
6. The model never receives tools; no external action executor or goal-mutation callback exists.

Local authority scope: localhost single-user under OS-account trust. Owner/reviewer strings are self-reported attribution, not authenticated identities. CSRF protects browser-origin writes; it is not a multi-user identity service. Consequential external authority is disabled. Do not invent identity verification or infer humanity from name strings.

Workers edit only assigned isolated worktree paths; root owns access.py, composition.py, ports, API, packaging/CI/docs and final integration. Current authority remains .delivery/tracker.json in root checkout.

