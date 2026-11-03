# Operations and recovery

The supported deployment profile is local single-user, advisory-only. Run as an unprivileged OS account. Bind is fixed to loopback; do not put the workspace on a public proxy without adding a real authentication/tenant boundary. The HTTP boundary rejects unexpected Host/Origin, cross-site requests, missing CSRF, non-JSON writes, oversize bodies and arbitrary static paths. Source HTML is rendered as text. No external actions execute.

## Authoritative state and restart
Default state: .wisdom/foundry.db (SQLite WAL), .wisdom/raw (content-addressed originals). Records and history are authoritative. FTS/search and context packets are serving projections. On startup, running workflows become interrupted and await explicit bounded retry. A failed job stores only a safe exception class; inspect the original local operation/input and audit before retry.

Canonical writes use transactions. Revisions require expected version; immutable source spans/predictions cannot be revised. Payload-bound idempotency protects exact retries; it does not make unspecified external effects safe. The event journal stores hashes rather than original source text so deletion can remove original/derived bytes. Hash chaining detects internal tampering but cannot prove semantic truth, prevent privileged filesystem edits, or detect tail truncation without an independently stored head.

This profile trusts the local OS account. Owner/reviewer names and human-approval flags record the operator's statements; they are not authenticated multi-user identities or cryptographic proof of humanity. No model response can invoke goal/approval APIs, and these records grant no external execution capability. Multi-user authentication, legal signatures and consequential delegated actions need a separate authorized deployment profile.

## Backup
Stop the process, or use SQLite's supported online backup API. Copy the database and raw directory together into an access-controlled destination. Do not copy a live database file without its WAL state. The backup can contain personal information and original licensed text; rights-filtered export is a separate operation.

```bash
python - <<'PY'
import sqlite3
from pathlib import Path
Path("backups").mkdir(exist_ok=True)
source=sqlite3.connect(".wisdom/foundry.db")
target=sqlite3.connect("backups/foundry.db")
source.backup(target)
target.close();source.close()
PY
```

Test a restore with a copy and `python -m wisdom --db backups/foundry.db audit`. Never overwrite the live database while a process holds it open. Schema version 1 rejects unknown future versions; any future migration must include forward/backward compatibility evidence and a tested backup/restore path.

## Generation identity and rollback
`python tools/generation.py` prints the immutable content identity, logical bindings, policy/configuration hashes and source commit for this checkout. It can write a manifest under generations/ using --write. No auto-updater mutates a running generation.

Build candidate generations from clean commits, run tests/architecture/evaluation, and record the manifest and independent review in the tracker. Deploy by starting the verified checkout after stopping the old local process. Rollback means checking out a known-good commit and restoring a compatible database backup if schemas changed. A pointer file cannot magically replace already running Python code; this implementation makes no such claim. Runtime self-modification and policy self-promotion are disabled.

## Source correction, expiry and deletion
Human reviews append claim revisions; exact originals stay unchanged. Open version history and source anchors to inspect what was known at the time. Expired/restricted sources are excluded from serving use. Delete a source in the local API with confirm:true/reason or `python -m wisdom delete-source SOURCE_ID --reason "..." --confirm`; dependent records, histories, caches and raw originals are removed according to dependency closure. Existing user-exported files/backups require separate user-controlled deletion.

Deletion enables SQLite and FTS secure-delete and attempts WAL truncation after commit. The response reports whether an active reader blocked truncation; release that reader and checkpoint before claiming the live database artifacts were scrubbed. Tests check a unique bounded fixture across database/WAL/SHM/raw files. This is not a guarantee against active-reader snapshots, backups, filesystem snapshots or storage-media forensics, and it cannot recall data already sent to an explicitly approved model provider.

## Research and media integration
No YouTube scraping or assumed unrestricted caption access. A future media adapter must declare rights, owner authorization where required, modality, partial coverage and exact timing alignment. ASR/vision dependency selection needs actual language/hardware/license tests. Unknown sources stay blocked; titles never count as inspected full content.

## Empirical release gates
Gate 0–5 task cards retain their external criteria in the live tracker. Fixtures prove software mechanics, not superiority over a strong baseline or better human wisdom. Scientific and human-subject evidence requires real independent design, data and participants. Production access, billing and communications are not part of this coding run.

