# Delivery record — 3 November 2026

The local single-user reference implementation is published at [shapefuture/wisdom](https://github.com/shapefuture/wisdom). The product remains advisory-only. This is verified software delivery, not evidence that the system improves real-world wisdom or satisfies every optional AAA profile.

## Verified candidate

- Reviewed local candidate: `ab33aaff1858f83d86ed38ce491fee1b6fb5e637`.
- Immutable runtime content generation: `sha256:f5b020db957a96619c15c99af699e91e1b469bc98790fc9ae00a5e86b7b8ac6b`.
- Published code commit: [842f6e94](https://github.com/shapefuture/wisdom/commit/842f6e94a52102ec26360bd3140e63c8a54cf6f3).
- Local and GitHub Git trees matched exactly: `ed6f88f64b55d1adf85578f80c40aa9702f0d8b6`.
- [GitHub Actions run](https://github.com/shapefuture/wisdom/actions/runs/41618578054): completed successfully.
- [Independent correction review](audits/correction-review.md): no remaining P0/P1 defects found within the reviewed code scope.

## Observed validation

| Check | Result |
| --- | --- |
| Unit, contract, security, persistence, recovery and HTTP scenarios | 115 passed |
| Architecture gates | Passed |
| Synthetic anchor/negation/no-forced-match evaluation | Passed; real-world effects unmeasured |
| JavaScript syntax and HTML/control/API checks | Passed |
| Wheel build, isolated installation and installed CLI | Passed |
| Configured model transport and consent contracts | Tested with local fakes; live gateway unverified |
| Real browser rendering and keyboard/usability session | Blocked: Chromium executable absent |
| Blinded source fidelity, invention usefulness, decision lift and human capability | Not run |

Six parallel Luna workcells built the components, followed by six independent cross-component audit streams and a correction/review cycle. The individual audit reports preserve the defects found on earlier candidates; the correction review records the accepted code generation.

## Remaining acceptance and owners

| Task | Concrete prerequisite | Owner |
| --- | --- | --- |
| WF-WEB / WF-BROWSER | Run `node tools/browser_smoke.cjs` with Playwright Chromium; inspect desktop/mobile and keyboard interaction, then conduct user usability review | Browser-enabled environment owner / product reviewer |
| Gate 0 | Authorized representative sources, independently collected problems, human gold coding and a strong cited-RAG baseline | Product researcher |
| Gates 1–3 | Held-out human-adjudicated source/theory/transfer and blinded invention comparisons, including prior-art/negative cases | Independent evaluators |
| Gate 4 | Prospective real experiments, measured outcomes and unaided human capability/agency checks | Study owner / participants |
| Gate 5 | Live model/media/connector credentials, rights/access review, measured operations and explicit production authorization | Operator / source-rights owner |

The runtime does not fetch arbitrary URLs, scrape unrestricted captions, transcribe inaccessible media, send messages, purchase, deploy, or execute learned skills. ASR/vision, live source acquisition, external app connections and controlled consequential autonomy require genuine authorized adapters and acceptance evidence. Full AAA conformance and production readiness are not claimed.

## Start

```bash
git clone https://github.com/shapefuture/wisdom.git
cd wisdom
python -m wisdom serve
```

Open http://127.0.0.1:8787. No runtime dependency installation is required for offline use. Follow [operations and recovery](OPERATIONS.md) for state, backups, deletion limits and optional model configuration.

The complete scope remains in `.delivery/mission.json`; authoritative current states and continuation are in `.delivery/tracker.json`. No empirical stage was silently closed.

