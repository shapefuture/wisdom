# WF-AUDIT-WEB: workbench/API compatibility audit

**Frozen candidate:** `40312598dbf10dbc351ca8a3148966d5336dd5ad`  
**Scope:** `wisdom/web/*`, its HTTP routes and service validators, schemas, and CLI-facing contracts.  
**Verdict:** **Not accepted yet.** Two P1 user-facing evidence-state gaps need correction or an explicit product decision; one P2 validation gap is listed below. The static/security and API checks otherwise passed.

## Findings

### P1 — Analysis warnings are discarded by the UI

`wisdom/web/app.js:81` announces “Analysis complete” using only result counts. It never renders `out.warnings`. The HTTP route returns status 200 and an empty collections result with warnings when a source is blocked, expired, has no spans, or fails span re-verification. A user who clicks Analyze can therefore see “Analysis complete: 0 claims…” without the reason or the fact that analysis did not proceed. The source row contains a status value, but that does not explain the result of the action.

**Fix:** Render warnings from the response and use a neutral “No analysis produced” result when the collections are empty; retain the warning reason in the visible result.

### P1 — Outcome form cannot record missing measurements

`wisdom/web/index.html:91` makes the Observed result textarea required and has no missingness field or unavailable-measurement control. The service contract explicitly supports `observed: null` with a non-empty `missingness` explanation (`wisdom/learning.py:322–330`). The workbench cannot represent this valid outcome state, so a user must omit it or enter text as if it were an observation.

**Fix:** Add a missing-measurement path that sends `observed: null` and requires a `missingness` explanation; make the observed field optional only in that mode.

### P2 — Trigger evaluation does not validate its budget control

The review budget control belongs to `trigger-form` (`wisdom/web/index.html:99`), but its value is read by the separate `evaluate-form` submit handler (`wisdom/web/app.js:103`). That handler calls `reportValidity()` only on `evaluate-form`. The number control has min/max but no explicit integer step; a decimal may bypass sibling-form validation and reach `MemoryService.evaluate`, which rejects non-integer budgets. The API error is surfaced, so this is a form-validation mismatch rather than silent acceptance.

**Fix:** Set `step="1"` and validate the budget before sending the evaluation request.

## Checks completed

- `node --check wisdom/web/app.js` passed.
- `node --check tools/browser_smoke.cjs` passed.
- HTML parser check: 69 unique IDs, no duplicate IDs, no missing static JavaScript ID selectors, and submit handlers present for all 15 HTML forms.
- Static XSS sink scan found no `.innerHTML`, `insertAdjacentHTML`, or `outerHTML` assignments. Dynamic content is built with DOM nodes and `textContent`; external links are limited to `http(s)` and use `rel="noopener noreferrer"`.
- Source form posts `#source-form [name="text"].value` directly, rather than the trimmed `dataFor()` value, so leading/trailing and internal source whitespace survives. The URI is stored as metadata; the application does not fetch it.
- Connection state is marked connected only after dashboard and all kind-list requests succeed. Session/API failures display unavailable/error state and non-2xx JSON errors are surfaced to the user.
- `python3 -m unittest tests.test_api -v`: 3 passed, including HTTP boundary and private-source export/purge cases.
- `python3 -m unittest discover -s tests -v`: 94 passed.
- `python3 tools/architecture_check.py`: passed all five checks.
- Live local HTTP probes submitted valid payloads through source, claim review, theory, mechanism, problem/forge, decision/approval, prediction, experiment, outcome/learn, VOI, goal, trigger/evaluate, TRACE, and skill routes; all passed. These probes did not claim browser event simulation.

## Browser and UX limits

No Chromium/Chrome executable is installed in this environment. The browser smoke script was syntax-checked only; it was not launched. No visual screenshot, responsive-layout, assistive-technology, or real keyboard-navigation claim is made.
