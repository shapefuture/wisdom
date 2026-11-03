# Independent correction review

**Candidate:** `ab33aaff1858f83d86ed38ce491fee1b6fb5e637`  
**Generated content identity:** `sha256:f5b020db957a96619c15c99af699e91e1b469bc98790fc9ae00a5e86b7b8ac6b`  
**Review basis:** `docs/REVIEW_FIX_CONTRACT.md`, `docs/contracts.md`, `docs/architecture.md`, `docs/AAA-V7-SPEC.md`, and the six prior independent audits.  
**Verdict:** No P0/P1 defect remains in the correction scope after targeted adversarial recheck. Accept this candidate as a local, single-user advisory reference implementation for the exercised code-level contract. This verdict does not establish full AAA v7.1 conformance, production readiness, or empirical superiority.

## Corrected blocking finding

The prior candidate returned `accept_for_purpose` from `Governor.assess()` for a theory whose provenance formed a two-record cycle, while `access.allowed()` denied it. The frozen candidate now uses the shared ancestry traversal in both serving and assessment. The added regression and an independent probe confirm that cyclic and missing lineage no longer produce an acceptance route; the assessment quarantines these records and serving denies them.

The earlier speaker-attribution defect is also corrected: provider-suggested speaker names remain separate and uncertain unless supported by source metadata or human annotation. A quoted passage alone does not establish who spoke it.

## Correction contract review

- Access checks apply ancestor-source grants and derived-record vetoes, reject unresolved lineage and cycles, and deny expired, blocked, poisoned, or quarantined records. Purpose aliases for external research and export are normalized; private material is denied for external research.
- The provider boundary accepts only the declared typed operations. Evidence payloads are rebuilt from canonical source and span records, with source hashes, exact offsets, and span text verified. User-entered theory and problem context requires explicit opt-in; linked source ancestry must independently grant model use. No arbitrary tool or external-action executor is exposed.
- Source quotes remain anchored to immutable canonical spans. Model-suggested attribution remains uncertain. Predictions and source evidence are immutable; outcomes are append-only and retry identity binds explicitly supplied timestamps and values.
- Purge performs SQLite secure-delete and checkpoint cleanup where possible, removes dependent rows/caches and raw content, and reports active-reader limitations. Documentation limits the guarantee: backups, snapshots, active-reader snapshots, media forensics, and other copies are outside its scope.
- UI changes expose analysis warnings, represent unavailable observed values explicitly, validate the evaluation budget, and show unchecked model-sharing choices. Package discovery is explicit and CI actions are pinned to full commit SHAs.
- Source-family counting treats copied or unknown material conservatively. The synthetic evaluation continues to label human comparison, real-world effects, and human capability as unmeasured.

These findings establish behavior in this local code and its deterministic probes. They do not prove semantic truth or equivalent guarantees in a deployed environment.

## Checks on the frozen candidate

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -v` | **PASS**, 115 tests. |
| Targeted cycle/missing-lineage probe | **PASS**: assessment quarantines and serving denies both. |
| Targeted rights probe | **PASS**: private `external-research` and case-insensitive quarantine are denied. |
| `python tools/architecture_check.py` | **PASS**: declared adapter, store-port, constitution, logical-slot, and scope checks. |
| `python tools/evaluate.py` | **PASS** for synthetic checks only; A0–A6 comparison not run, real-world effect and human capability unmeasured. |
| CLI help and `python -m wisdom --db :memory: status` | **PASS**; reports a valid empty ledger and `external_actions_enabled: false`. |
| `node --check wisdom/web/app.js`; `python -m compileall -q wisdom tools` | **PASS**. |
| Wheel build, isolated target install, installed CLI status | **PASS** using `pip wheel --no-deps --no-build-isolation`; `python -m build` was unavailable in this environment. |
| `TMPDIR=.delivery/runtime node tools/browser_smoke.cjs` | **BLOCKED**: Playwright is installed but its Chromium executable is absent. No real-browser validation was completed. |

The exact generation hash was reproduced by `python tools/generation.py`. Checks used no connected provider, external application, production database, or browser.

## Scope and remaining acceptance

The authority model is a localhost, single-user profile under OS-account trust. Owner and reviewer labels are self-reported attribution, not authenticated identities. Consequential external actions and runtime external execution are disabled. This candidate is a useful local reference system, not a multi-user identity or permissions service.

Real-browser acceptance, live-provider behavior, licensed-source review, operational deletion and recovery assurance, and scientific/field evaluation remain unvalidated. External empirical Gates 0–5 remain open. In particular, no fixtures or synthetic benchmarks demonstrate superiority over strong cited-retrieval baselines, performance on unseen sources/problems, reliable causal transfer, or improved unaided human capability. Novelty/prior-art review and any real experiment require independent evidence and human review.
