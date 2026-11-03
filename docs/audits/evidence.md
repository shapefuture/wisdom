# Independent ingestion and evidence audit

**Candidate reviewed:** `40312598dbf10dbc351ca8a3148966d5336dd5ad`  
**Scope:** `wisdom/ingest.py`, `evidence.py`, `annotations.py`, `api.py`, `exports.py`, `composition.py`, plus relevant access/store/provider code.  
**Verdict:** No P0/P1 defect found in the audited source-rights, exact-span, provider-consent, historical-read, export/purge, or local HTTP-boundary paths. This is a focused implementation audit, not evidence of live-provider quality, browser quality, or empirical benefit.

## Runtime evidence

I ran `.delivery/runtime/evidence_audit.py` with a temporary SQLite database, temporary raw-object directory, in-process provider sentinel, and `FoundryServer` bound to port `0`. The script removed its temporary database and raw files at exit. No external provider or network service was contacted.

All 10 focused checks passed:

| Check | Result |
|---|---|
| Denied source bytes | Denied input text was absent from the stored manifest, spans, FTS search, and raw-object directory; its content hash and blocked status remained. |
| Exact spans | Unicode codepoint offsets sliced back to exact source passages; span verification and source coverage agreed. |
| Model-sharing opt-in | `allow_model: false` made zero provider calls and used offline exact-span claims. `allow_model: true` permitted a local sentinel call; its output remained marked an unverified paraphrase. |
| Export filtering | A private, non-exportable source and its claims were absent from JSON export. A parallel HTTP export check also omitted its text. |
| Historical versions | A reviewed claim advanced to v2 while v1 retained its original unreviewed data; HTTP version lookup returned v1 under current access permissions. |
| Deletion and caches | Purge removed the source and derived records, FTS hits, content-addressed raw object, and source idempotency response; the ledger remained valid. |
| HTTP mutation boundary | Missing CSRF was rejected (403); `text/plain` was rejected (400). |
| HTTP origin/host boundary | Foreign `Origin`, unrecognized `Host`, and `Sec-Fetch-Site: cross-site` were rejected (403). |
| Denied source HTTP view | The source endpoint returned a restricted manifest without the denied source bytes; export omitted the denied text. |
| Runtime cleanup | Temporary database, raw directory, server, and thread were closed after the checks. |

The complete repository suite also passed: `python3 -m unittest discover -s tests -v` — **94 tests, OK**.

## Code review notes

- `IngestService` validates required rights fields, defaults model sharing to false, and stores blocked/expired sources as metadata/hash manifests without source bytes or spans.
- `EvidenceService` rechecks rights and span integrity before analysis, requires explicit model-sharing consent before provider use, validates proposed quotations as exact substrings of cited spans, preserves offline source text as unreviewed attributed claims, and makes analysis replayable through source-linked assessment plans.
- `AnnotationService` requires source-owned exact spans for dialogue annotations and two accessible claim records plus a typed conflict and reason for contradictions. Contradictions remain unresolved and link claims with negative polarity.
- `Application` wraps an injected provider with source-consent checks. Provider use was exercised with a capture-only sentinel; live provider transport was deliberately not exercised.
- `allowed()` propagates source restrictions through record references and lineage edges. HTTP current-version permission checks gate history/version reads; export applies `purpose="export"` to source ancestry.
- `Store.purge_source()` removes derived records, versions, edges, matching FTS entries, idempotency responses, and unreferenced raw content while preserving digest-only journal history.
- The HTTP adapter uses an allowlisted static path map, exact loopback `Host` checks, same-origin `Origin`, `Sec-Fetch-Site` checks, JSON-only mutations, and a constant-time CSRF-token comparison.

## Limitations

- This audit did not evaluate model quality, transcript accuracy on licensed live media, independent annotation agreement, or human decision lift.
- No browser-based end-to-end run was performed; this audit does not claim rendered visual or keyboard coverage.
- HTTP checks used localhost only and did not contact a real external model endpoint.
- Hashes of denied text remain in restricted manifests by contract; hashes can reveal equality and may permit guessing for low-entropy inputs. The manifest is not a substitute for minimizing sensitive input before submission.

No production code or tests were modified. The only committed file from this audit is this report; the reproducible focused script is kept in `.delivery/runtime/` scratch.
