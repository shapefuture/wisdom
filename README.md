# Wisdom Foundry

A local research workbench for **Evidence → Theory → Invention → Decision → Experimental Learning**, implementing the attached Wisdom Foundry 11 architecture with SQLite, exact source anchors and human-controlled authority.

## Run

Requires Python 3.12+. No runtime packages, account, model key, or network access are required for offline use.

```bash
git clone https://github.com/shapefuture/wisdom.git
cd wisdom
python -m wisdom serve
```

Open **http://127.0.0.1:8787**. The workspace starts empty. Register authorized text, SRT or VTT, analyze exact source spans, review claims, build scoped theories and mechanisms, enter an independent problem, generate transfer hypotheses, record decisions, preregister predictions, and compare outcomes.

Offline mode preserves exact unreviewed utterances and creates conservative, explicitly untested structured drafts. It does not pretend to infer speaker intent, validate mechanisms, adjudicate philosophy, check worldwide prior art, or prove useful invention. The UI reports actual records and data.

## Optional reasoning model

Use an explicitly configured JSON-capable chat-completions-compatible HTTPS gateway:

```bash
export WISDOM_PROVIDER_URL=https://your-model-gateway.example/v1/chat/completions
export WISDOM_MODEL=your-model-name
# Set WISDOM_API_KEY through your secret manager/environment.
python -m wisdom serve
```

A source must explicitly permit **model processing** before its text can leave the local workspace. Problems, theories and mechanisms also have separate, unchecked model-sharing consent controls for user-entered context. Provider operations resolve typed canonical records and exact spans; arbitrary raw-text operations are rejected. Provider outputs are untrusted proposals: exact quotations and schemas are checked; semantic meaning and suggested speaker identity still require review. Source permission does not authorize purchases, communications, arbitrary URL fetches, execution, or goal changes. Model timeout defaults to 45 seconds; output defaults to 3,000 tokens and can be bounded by WISDOM_MODEL_TIMEOUT/WISDOM_MAX_TOKENS.

## CLI

```bash
python -m wisdom ingest transcript.vtt --rights-confirmed --allow-export
python -m wisdom analyze SOURCE_ID
python -m wisdom search "feedback timing" --lens fusion
python -m wisdom context "Which assumption changes this decision?" --budget 2000
python -m wisdom audit
python -m wisdom export --format markdown --out research.md
python -m wisdom --db .wisdom/foundry.db status
```

Use `python -m wisdom call --help` for typed JSON-file operations across theory, invention, decisions, forecasts, experiments, outcomes, skills, triggers and TRACE. API contracts: [docs/contracts.md](docs/contracts.md).

## What is implemented

- Authorized intake and coverage; immutable originals/spans; exact Unicode offsets and subtitle time anchors.
- Claims, versioned reviews, interpretations/arguments, scoped theory and mechanism cards, signed positive/negative evidence and source-family accounting.
- Human dialogue/viewpoint annotations and typed disagreements preserve dissent; historical context can reopen what was recorded at an earlier decision time.
- Independent problem dossiers, multiple reframes, tentative structural/functional matching, explicit negative-transfer gaps, no-match results and eight-axis red-team checklists.
- Human decision contracts, qualitative value-of-information, immutable preregistration hashes, append-only observations, bounded learning and conditional skills with separate evidence/authorization gates.
- Inspectable lexical/functional/structural retrieval and context, versioned lineage, human goals/TRACE, prospective triggers with expiry, duplicate suppression and zero-notification budgets.
- Durable workflow state, bounded manual retries, interrupted-run recovery, rights-filtered JSON/Markdown/Argdown export, deletion propagation, tamper-evident event journal and independent watchdog checks.
- Responsive local web UI, CSRF/origin/host checks, no external scripts, no runtime action executor.

## Validation and scope

```bash
python -m unittest discover -s tests -v
python tools/architecture_check.py
python tools/evaluate.py
```

With Playwright and Chromium installed in a browser-enabled development environment, run `node tools/browser_smoke.cjs` for actual source intake/review and desktop/mobile checks. That check is separate from the dependency-free runtime and backend suite.

The executable tests validate software behavior. **Empirical Gates 0–5 are not accepted**: independent real source/problem sets, human gold annotations, blinded comparisons to a strong cited-RAG baseline, real experiments and unaided capability measurements must actually be collected. Live ASR/vision, YouTube owner-authorized caption acquisition, connected private apps, external research and consequential actions are adapter boundaries, not secretly enabled integrations. Missing media stays explicitly unavailable.

This is a local, single-user reference implementation, not a multi-tenant hosted service or a production AAA conformance certificate. Full roadmap and task authority: [docs/PLAN.md](docs/PLAN.md), `.delivery/mission.json`, and `.delivery/tracker.json`. Operational/recovery instructions: [docs/OPERATIONS.md](docs/OPERATIONS.md). The supplied architecture is preserved in [docs/architecture.md](docs/architecture.md).

## Workflow provenance

The delivery process was explicitly requested from [shapefuture/ArchetypeAI](https://github.com/shapefuture/ArchetypeAI/blob/main/.agents/skills/full-plan-delivery/SKILL.md); its unmodified bundled tooling under `.agents/skills/full-plan-delivery` retains its [PolyForm Noncommercial license](.agents/skills/full-plan-delivery/LICENSE). It is development tooling and is not imported by the product runtime. The requested [Gauntlet Loop](https://github.com/robonuggets/gauntlet-loop/blob/main/.claude/skills/gauntlet-loop/SKILL.md) informed separate builder/critic passes against the supplied specification. [AAA v7.1](docs/AAA-V7-SPEC.md) informed contracts, isolation and governed recovery; broader conformance remains a testable claim.

