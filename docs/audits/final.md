# Independent final audit — Wisdom Foundry candidate

**Candidate:** Git commit `40312598dbf10dbc351ca8a3148966d5336dd5ad`  
**Generated content identity:** `sha256:f3b3222540f241884bdbb320e7c56b34dcb714bf1057bfa9d065e58ebce7be51` (`python tools/generation.py`)  
**Review scope:** Frozen `docs/contracts.md`, `docs/architecture.md`, and `docs/AAA-V7-SPEC.md`; runtime services, ports, API, CLI, UI source, architecture declarations, and available local checks.  
**Verdict:** The candidate is a capable local advisory reference implementation with good boundary discipline and green deterministic checks. It is **not accepted as source-faithful yet** because one P1 speaker-attribution defect remains. It is not a complete AAA v7.1 implementation, a production-ready multi-tenant system, or evidence of empirical superiority. External Gates 0–5 remain open.

## Blocking finding

### P1 — Model-proposed speaker identities can be stored as certain

`EvidenceService._validate_proposals` accepts any string in the provider's `speaker` field. In `analyze`, a non-null proposed speaker is stored with `speaker_uncertain: false`, even when the source metadata says the author/speaker is unknown and no human or source annotation supports that identity. Exact quote validation does not validate who said the words.

**Independent reproduction:** I supplied a provider response with the exact quote `I support a change.` and `speaker: "Famous Person"` for a source whose author was `unknown`. The resulting claim had `speaker_uncertain: false` and `review_status: "unreviewed"`. This directly conflicts with the architecture's source-attribution, speaker-uncertainty, and adversarial conflicting-speaker requirements.

**Required correction:** Keep provider-suggested speaker names explicitly unverified/uncertain, or only mark attribution certain when supported by source metadata or a human annotation. Add a regression with a conflicting speaker identity. This audit does not accept the candidate for source-faithfulness until that behavior is corrected and rechecked.

## Privacy scope requiring an explicit product decision

With a configured provider, `InventionEngine.forge` submits the user-entered problem dossier to `invention.diagnose`; when there are eligible source mechanisms, it may submit it again with `invention.forge`. The source-consent guard covers linked source ancestry, but a problem with no source ancestry has no model-sharing rights field, so the provider call is allowed. The UI action and configured-provider indicator may be intended to authorize this, but the UI does not say that the problem text will be sent to the provider. Since problem dossiers may contain sensitive personal context, make the disclosure/consent boundary explicit or establish that the forge action is itself the intended per-request consent.

This is a policy and UX ambiguity rather than a demonstrated unauthorized external action. It must be resolved before connecting private applications or broadening data collection.

## Checks run

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -v` | **PASS**, 94 tests, including adversarial service, rights, HTTP, replay, and workflow cases. |
| `python tools/architecture_check.py` | **PASS**; reported adapter isolation, store-port completeness, constitution, logical slots, and 22-section scope mapping. |
| `python tools/evaluate.py` | **PASS** for synthetic checks: exact anchors, negation retention, no forced match, and ledger integrity. It explicitly reports A0–A6 comparison not run, real-world effect unmeasured, and human capability unmeasured. |
| `python -m wisdom --help` and `python -m wisdom call --help` | **PASS**; CLI command groups and typed operations render. |
| `python -m wisdom --db :memory: status` | **PASS**; empty in-memory workspace, valid empty ledger, external actions disabled. |
| `node --check wisdom/web/app.js` | **PASS**. |
| `python -m compileall -q wisdom tools` | **PASS**. |
| `node tools/browser_smoke.cjs` | **BLOCKED**: Playwright is installed, but its Chromium executable is absent (`/root/.cache/ms-playwright/chromium_headless_shell-1234/...`). No real-browser UI or layout validation was completed. |

The browser smoke script first needed a writable `TMPDIR` because this environment lacks `/tmp`; after setting it to ignored candidate-local scratch, it reached Playwright and failed on the missing browser binary. No browser was installed or downloaded.

## Contract and architecture assessment

### Positive executable properties

- Source text is treated as untrusted data; the model adapter is JSON-only and tool-free, source sharing requires explicit `allow_model`, and source quotations are checked against exact spans.
- Source originals/spans and predictions are immutable; prediction hashes precede outcomes; outcomes and review corrections use append-only/versioned records.
- Rights traverse source lineage for serving, model, and export use; restricted manifests omit denied bytes; purge removes dependent records and caches.
- Provider/model output is typed as proposal or interpretation, transfer ideas remain unvalidated, and human decision approval records a choice without executing it.
- Authorization defaults to a small local-operation allowlist; the runtime declares external action execution disabled.
- Store mutations are transactional and journaled; CAS, idempotency replay, purge, concurrency, and restart/retry behavior have deterministic coverage.
- HTTP code enforces exact loopback Host checks, same-origin and CSRF checks for mutations, JSON-only request bodies, bounded body size, and a narrow static-file map. Export filtering is rights-aware.

These are implementation properties demonstrated in this local candidate and its test fixtures. They are not a semantic truth guarantee, formal proof, or independently validated operational assurance case.

### AAA v7.1 status

The checked-in constitution, logical slots, composition root, generation hash tool, control journal, store interfaces, and manual recovery instructions implement a useful **minimal local profile**. The repository also has real isolated review/workcell workflows. However, the executable architecture check is deliberately narrow; it does not certify full AAA conformance.

The repository does not implement the full AAA development fabric as an executable subsystem (task/conflict DAG compilation, write-set leases, contract fanout manager, candidate integration broker, and separately owned independent verifier/evidence root). Runtime generation activation is documented as manually starting a verified checkout; there is no atomic active-generation pointer, staged rollout, signature-backed evidence bundle, or autonomous rollback manager. These are scoped out or manual in this R2 single-user advisory profile. Do not advertise full AAA v7.1 conformance from the architecture-check result.

The generated content identity is reproducible from the command, but it is not committed as a manifest for this candidate; `generations/46037d901203dbc7aced8af4af4d6d57808fdf9a0da305bdae27494f59458bcc.json` is a different, older content identity. Persist the exact candidate manifest with its evidence bundle if a verified-generation claim is needed.

## Explicitly unimplemented or unvalidated

- No media acquisition, authorized YouTube captions, ASR, diarization, vision, connected private-app integration, or external research adapter is enabled. No arbitrary source URL fetch occurs.
- The `semantic` retrieval label is a documented lexical fallback; embeddings are not installed. Mechanism matching is lexical candidate generation, not validated causal transfer.
- Prior-art search is not live; novelty stays unchecked. Red-team output is explicitly an automated checklist, not independent human review.
- No production deployment, multi-tenant authentication, billing, communications, external action execution, runtime-agentic self-modification, distributed profile, shadow deployment, or canary was tested or enabled.
- Full review was not exhaustive formal verification, penetration testing, load testing, backup/restore drill, or real-browser acceptance.

## External empirical Gates 0–5 remain open

No number of passing local fixtures closes the roadmap's empirical gates. Still required are authorized representative sources and independently collected problems; a manual coding rubric and strong cited-RAG baseline; blinded human/expert source, argument, speaker, theory, and invention ratings; unseen-source/problem and hard-negative transfer tests; prior-art review; real measured experiments and holdout learning; cost and label-contamination audits; and unaided human-capability/overdependence measures. Gate 5 additionally requires license/security review, verified deletion/export behavior in realistic use, recovery evidence, and scoped human approval before any future external effect.

`tools/evaluate.py` accurately labels its fixture as synthetic and states that comparative human evaluation, real-world effects, and human capability remain unmeasured. Preserve that wording. A completed reference implementation is not a demonstrated superior wisdom, invention, or decision system.
