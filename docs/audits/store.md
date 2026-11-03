# WF-AUDIT-STORE: independent storage and governance review

**Candidate:** `40312598dbf10dbc351ca8a3148966d5336dd5ad`  
**Scope:** `wisdom/store.py`, `wisdom/governance.py`, `wisdom/access.py`, associated tests and contract requirements  
**Verdict:** **Blocked on P1 rights and deletion gaps.** This is a code and local-test review; it is not browser, production, live-provider, or empirical validation.

## Findings

### P1 — Derived rights and unresolved lineage fail open in the access helper

`wisdom/access.py:allowed()` checks source ancestry, but does not apply the current derived record's own `rights` flags or expiry. `sources_for()` silently skips missing referenced IDs. Both behaviors can make retrieval, provider transport, and export treat a restricted or provenance-incomplete derived record as allowed.

Reproduction with a local `Store()`:

```python
source = store.put("source", {"text": "authorized", "rights": {
    "allowed": True, "allow_export": True, "allow_model": True}})
derived = store.put("idea", {"source_id": source["id"], "rights": {
    "allowed": True, "allow_export": False, "allow_model": False}})
orphan = store.put("idea", {"source_id": "missing-source", "rights": {"allowed": True}})
```

Observed: `allowed(store, derived, purpose="export")` and `purpose="model"` both returned `True`; `allowed(store, orphan)` returned `True`, while `Governor.assess(orphan_id)` correctly returned `quarantine`. This helper is used by `wisdom/exports.py`, `wisdom/composition.py`, `wisdom/retrieval.py`, and `wisdom/api.py`.

**Required correction:** enforce a derived record's own vetoes/expiry in the central helper and fail closed when any referenced lineage record is missing. Recheck provider, retrieval, API, and export paths against these cases.

### P1 — Purge removes live rows and sidecar bytes but does not securely erase SQLite pages

The purge path deletes dependent records, versions, edges, and matching idempotency responses; it unlinks the content-addressed raw sidecar when no live source shares the hash. Those logical effects passed. However, a unique marker in a purged source remained byte-searchable in the main SQLite database after `purge_source()` and `Store.close()`.

Reproduction used a temporary file database under `.delivery/runtime`: store source text `UNIQUE_PRIVATE_AUDIT_MARKER_93bd1c`, purge it, close the store, then search the database and WAL artifacts. The marker remained in `purge.sqlite`. `list`, `get`, `history`, and search no longer returned the record. Thus the operation is logical deletion plus sidecar removal, not physical/secure erasure from SQLite storage.

**Required correction:** explicitly define the deletion guarantee. If secure erasure is required, use a storage design/procedure that handles SQLite pages, WAL/journal files and relevant backups; otherwise clearly scope the guarantee to logical deletion and avoid implying that deleted content is unrecoverable.

### P2 — Family-independence assessment does not use the contracted content-hash fallback

`Governor._family_independence()` counts only indices with an explicit `source_family`. With two source records that each have distinct `content_hash` values but no `source_family`, assessment returned `count: 0`, `families: []`, `status: "unknown"`. The frozen contract says a missing family uses the original content hash; identical originals should collapse, while distinct hashes should remain distinct.

New ingested sources receive a default family, which limits the exposure for current intake. Legacy or directly stored sources with hashes but no family still get the wrong independence report.

**Required correction:** derive a stable family key from `content_hash` when the explicit family is absent, and test distinct hashes, duplicate hashes, and shared explicit families.

### P2 — Event-chain verification does not detect canonical record edits

`verify_ledger()` verifies that event hashes link to each other, but does not compare a record or version's bytes with the `data_hash` stored in its corresponding event. In a temporary database, directly changing a canonical record's `data` from `canonical title` to `tampered title` left `verify_ledger()["valid"] == True`.

This is narrower than event-chain tampering: editing an event's hashed principal is detected by the current tests. The present verdict establishes chain consistency, not record-to-event consistency or resistance to a database writer who can alter both.

**Required correction:** either verify record/version hashes against their journal entries or name and document this function strictly as event-chain verification. Add a record-data tampering regression if the stronger integrity claim is intended.

### P2 — Rights-bearing purposes outside a small exact-name set bypass purpose flags

`Governor.assess()` maps only `export`, `model`, `external_research`, and `external` to rights flags. A well-supported derived record with an ancestor source having `allow_export: false` returned `accept_for_purpose` for `purpose="publish"`; `access.allowed(..., purpose="publish")` also returned `True`. There is no publish endpoint in this candidate, but generic purpose assessment does not fail closed for other external-use labels.

**Required correction:** normalize a defined closed set of purpose aliases to rights flags and fail closed for unrecognized external purposes. Keep execution authorization separate.

### P2 — Malformed rights context is ignored by local action authorization

The standard unknown/external action tests fail closed. An additional probe found `Governor.authorize("read", {"authorized": True, "rights": "denied"})` returns `allowed: True`: a present but non-object `rights` value is ignored. A missing rights field may be valid for a purely local action, but malformed present rights should not be treated as affirmative permission.

**Required correction:** reject or deny malformed rights context when supplied; retain tests for each allowlisted local action, unknown actions, external actions, and rights vetoes.

## Checks run

- `python -m unittest discover -s tests -v` — **94 passed** on the frozen candidate.
- Additional isolated file-backed SQLite workflow under `.delivery/runtime`: close/reopen retained source data; duplicate idempotent source put returned the same record without a duplicate event; two independent connections racing one CAS produced exactly one winner and one conflict; purge removed live source/derived/job rows, dependent edge rows, idempotency responses, and raw sidecar bytes; event chain remained valid after purge.
- Targeted probes confirmed the P1/P2 observations above, including residual SQLite source bytes after purge.

No production database, browser, external connector, or live provider was used. Temporary runtime artifacts were isolated under `.delivery/runtime`.
