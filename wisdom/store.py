"""SQLite-backed canonical store with versioned records and an integrity ledger."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import Conflict, NotFound, ValidationError

_KIND = re.compile(r"^[a-z][a-z0-9_]*$")
_GENESIS = "0" * 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


class Store:
    """Persistent StorePort implementation. A single connection is serialized by an RLock."""

    def __init__(self, path: str = ":memory:", raw_dir: str | os.PathLike[str] | None = None):
        self.path = str(path)
        self.raw_dir = Path(raw_dir) if raw_dir is not None else None
        self._lock = threading.RLock()
        if self.raw_dir is not None:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=30)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            schema_version = self._db.execute("PRAGMA user_version").fetchone()[0]
            if schema_version > 1:
                self._db.close()
                raise RuntimeError(f"database schema version {schema_version} is newer than supported version 1")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.execute("PRAGMA busy_timeout=30000")
            # Apply on every connection: secure_delete is a connection setting.
            self._db.execute("PRAGMA secure_delete=ON")
            if self.path != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
                self._db.execute("PRAGMA synchronous=FULL")
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, version INTEGER NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    data TEXT NOT NULL, immutable INTEGER NOT NULL DEFAULT 0,
                    deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS record_versions (
                    id TEXT NOT NULL, version INTEGER NOT NULL, kind TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    data TEXT NOT NULL, immutable INTEGER NOT NULL,
                    PRIMARY KEY(id, version)
                );
                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
                    relation TEXT NOT NULL, polarity TEXT NOT NULL, data TEXT NOT NULL,
                    created_at TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL, subject_id TEXT NOT NULL, occurred_at TEXT NOT NULL,
                    principal TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    principal TEXT NOT NULL, key TEXT NOT NULL, request_hash TEXT NOT NULL,
                    response TEXT NOT NULL, PRIMARY KEY(principal, key)
                );
            """)
            if schema_version < 1:
                self._db.execute("PRAGMA user_version=1")
            try:
                self._db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS record_fts USING fts5(id UNINDEXED, kind UNINDEXED, content)")
                self._fts = True
                # FTS5 stores token data in its own shadow tables. SQLite 3.42+
                # supports secure deletion of index entries; older builds still
                # get the database-level secure_delete and post-purge checkpoint.
                try:
                    self._db.execute("INSERT INTO record_fts(record_fts, rank) VALUES('secure-delete', 1)")
                    self._fts_secure_delete = True
                except sqlite3.OperationalError:
                    self._fts_secure_delete = False
                self._fts_cleanup_mode = "secure_delete" if self._fts_secure_delete else "rebuild_on_purge"
            except sqlite3.OperationalError:
                # SQLite builds without FTS5 still retain correct search via a scan.
                self._fts = False
                self._fts_secure_delete = False
                self._fts_cleanup_mode = "not_applicable"
            self._rebuild_fts()

    def _transaction(self):
        class Tx:
            def __init__(inner, db): inner.db = db
            def __enter__(inner): inner.db.execute("BEGIN IMMEDIATE"); return inner.db
            def __exit__(inner, typ, value, tb):
                inner.db.execute("ROLLBACK" if typ else "COMMIT")
        return Tx(self._db)

    def _rebuild_fts(self) -> None:
        if not self._fts:
            return
        self._db.execute("DELETE FROM record_fts")
        rows = self._db.execute("SELECT id,kind,data FROM records WHERE deleted=0").fetchall()
        for row in rows:
            self._db.execute("INSERT INTO record_fts(id,kind,content) VALUES(?,?,?)",
                             (row["id"], row["kind"], self._searchable(row["data"])))

    @staticmethod
    def _searchable(raw: str) -> str:
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            return raw
        def flatten(v):
            if isinstance(v, dict): return " ".join(flatten(x) for x in v.values())
            if isinstance(v, (list, tuple)): return " ".join(flatten(x) for x in v)
            if isinstance(v, (str, int, float)): return str(v)
            return ""
        return flatten(value)

    def _event(self, kind: str, subject_id: str, payload: dict, principal: str) -> dict:
        occurred = _now()
        payload_hash = _hash(_json(payload))
        row = self._db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = row[0] if row else _GENESIS
        event_id = uuid.uuid4().hex
        fields = {"event_id": event_id, "kind": kind, "subject_id": subject_id,
                  "occurred_at": occurred, "principal": principal, "payload_hash": payload_hash,
                  "previous_hash": previous}
        event_hash = _hash(_json(fields))
        self._db.execute("INSERT INTO events(event_id,kind,subject_id,occurred_at,principal,payload_hash,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?)",
                         (event_id, kind, subject_id, occurred, principal, payload_hash, previous, event_hash))
        # The journal stores only a digest of the request payload, never source text/private content.
        return {**fields, "event_hash": event_hash}

    def _idempotent_get(self, key: str | None, principal: str, request_hash: str):
        if key is None: return None
        row = self._db.execute("SELECT request_hash,response FROM idempotency WHERE principal=? AND key=?", (principal, key)).fetchone()
        if row is None: return None
        if row["request_hash"] != request_hash:
            raise Conflict("idempotency key was already used for a different request")
        return json.loads(row["response"])

    def _idempotent_save(self, key: str | None, principal: str, request_hash: str, response: dict) -> None:
        if key is not None:
            self._db.execute("INSERT INTO idempotency(principal,key,request_hash,response) VALUES(?,?,?,?)",
                             (principal, key, request_hash, _json(response)))

    @staticmethod
    def _source_text(data: dict) -> str | None:
        original = data.get("original_text")
        if isinstance(original, str):
            return original
        text = data.get("text")
        return text if isinstance(text, str) else None

    def _put_raw(self, data: dict) -> str | None:
        if self.raw_dir is None or not isinstance(data, dict):
            return None
        source_text = self._source_text(data)
        if source_text is None:
            return None
        payload = source_text.encode("utf-8")
        digest = _hash(payload)
        target = self.raw_dir / digest[:2] / digest
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            tmp = target.with_name(target.name + ".tmp-" + uuid.uuid4().hex)
            tmp.write_bytes(payload)
            os.replace(tmp, target)
        return digest

    def put(self, kind: str, data: dict, *, record_id: str | None = None,
            expected_version: int | None = None, immutable: bool = False,
            idempotency_key: str | None = None, principal: str = "local-user",
            event_type: str | None = None) -> dict:
        if not isinstance(kind, str) or not _KIND.fullmatch(kind):
            raise ValidationError("kind must be singular snake_case")
        if not isinstance(data, dict):
            raise ValidationError("record data must be a JSON object")
        # Span and prediction identity is always immutable, independent of caller flags.
        immutable = bool(immutable or kind in {"span", "prediction"})
        rid = record_id or uuid.uuid4().hex
        req = {"op":"put", "kind":kind, "data":data, "record_id":record_id,
               "expected_version":expected_version, "immutable":immutable,
               "event_type":event_type}
        rh = _hash(_json(req))
        with self._lock, self._transaction():
            previous = self._idempotent_get(idempotency_key, principal, rh)
            if previous is not None: return previous
            row = self._db.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
            now = _now()
            if row is None:
                if expected_version not in (None, 0):
                    raise Conflict(f"expected version {expected_version}, record does not exist")
                version, created = 1, now
            else:
                if row["deleted"]:
                    raise Conflict("deleted record identifiers cannot be reused")
                if row["kind"] != kind:
                    raise Conflict("record kind cannot change")
                if row["immutable"]:
                    raise Conflict("immutable record cannot be revised")
                if expected_version is None or expected_version != row["version"]:
                    raise Conflict(f"version conflict: current version is {row['version']}")
                version, created = row["version"] + 1, row["created_at"]
            updated = now
            raw_hash = self._put_raw(data) if kind == "source" else None
            payload = dict(data)
            envelope = {"id":rid, "kind":kind, "version":version,
                        "created_at":created, "updated_at":updated, "data":payload}
            self._db.execute("INSERT OR REPLACE INTO records(id,kind,version,created_at,updated_at,data,immutable,deleted) VALUES(?,?,?,?,?,?,?,0)",
                             (rid,kind,version,created,updated,_json(payload),int(immutable)))
            self._db.execute("INSERT INTO record_versions(id,version,kind,created_at,updated_at,data,immutable) VALUES(?,?,?,?,?,?,?)",
                             (rid,version,kind,created,updated,_json(payload),int(immutable)))
            if self._fts:
                self._db.execute("DELETE FROM record_fts WHERE id=?", (rid,))
                self._db.execute("INSERT INTO record_fts(id,kind,content) VALUES(?,?,?)", (rid,kind,self._searchable(_json(payload))))
            self._event(event_type or ("RECORD_CREATED" if version == 1 else "RECORD_REVISED"), rid,
                        {"kind":kind,"version":version,"data_hash":_hash(_json(payload)),"raw_hash":raw_hash}, principal)
            self._idempotent_save(idempotency_key, principal, rh, envelope)
            return envelope

    def get(self, record_id: str, version: int | None = None) -> dict:
        with self._lock:
            if version is None:
                row = self._db.execute("SELECT * FROM records WHERE id=? AND deleted=0", (record_id,)).fetchone()
            else:
                # Deletion removes all historical versions, so a purge cannot be bypassed by version lookup.
                live = self._db.execute("SELECT deleted FROM records WHERE id=?", (record_id,)).fetchone()
                if live is None or live[0]: row = None
                else: row = self._db.execute("SELECT * FROM record_versions WHERE id=? AND version=?", (record_id,version)).fetchone()
            if row is None: raise NotFound(record_id)
            return {"id":row["id"],"kind":row["kind"],"version":row["version"],
                    "created_at":row["created_at"],"updated_at":row["updated_at"],
                    "data":json.loads(row["data"])}

    def list(self, kind: str | None = None) -> list[dict]:
        with self._lock:
            if kind is None:
                rows = self._db.execute("SELECT * FROM records WHERE deleted=0 ORDER BY created_at,id").fetchall()
            else:
                rows = self._db.execute("SELECT * FROM records WHERE deleted=0 AND kind=? ORDER BY created_at,id", (kind,)).fetchall()
            return [self._envelope(r) for r in rows]

    @staticmethod
    def _envelope(row) -> dict:
        return {"id":row["id"],"kind":row["kind"],"version":row["version"],
                "created_at":row["created_at"],"updated_at":row["updated_at"],"data":json.loads(row["data"])}

    def history(self, record_id: str) -> list[dict]:
        with self._lock:
            live = self._db.execute("SELECT deleted FROM records WHERE id=?", (record_id,)).fetchone()
            if live is None or live[0]: raise NotFound(record_id)
            rows = self._db.execute("SELECT * FROM record_versions WHERE id=? ORDER BY version", (record_id,)).fetchall()
            return [self._envelope(r) for r in rows]

    def link(self, source_id: str, target_id: str, relation: str, *, polarity: str = "neutral", data: dict | None = None) -> dict:
        if not source_id or not target_id or not relation:
            raise ValidationError("source, target, and relation are required")
        data = data or {}
        if not isinstance(data, dict): raise ValidationError("edge data must be an object")
        with self._lock, self._transaction():
            for rid in (source_id,target_id):
                row=self._db.execute("SELECT 1 FROM records WHERE id=? AND deleted=0",(rid,)).fetchone()
                if not row: raise NotFound(rid)
            edge={"id":uuid.uuid4().hex,"source_id":source_id,"target_id":target_id,
                  "relation":relation,"polarity":polarity,"data":data,"created_at":_now()}
            self._db.execute("INSERT INTO edges(id,source_id,target_id,relation,polarity,data,created_at) VALUES(?,?,?,?,?,?,?)",
                             (edge["id"],source_id,target_id,relation,polarity,_json(data),edge["created_at"]))
            self._event("EDGE_CREATED",edge["id"],{"source_id":source_id,"target_id":target_id,
                        "relation":relation,"polarity":polarity,"data_hash":_hash(_json(data))},"local-user")
            return edge

    def edges(self, record_id: str | None = None) -> list[dict]:
        with self._lock:
            if record_id is None:
                rows=self._db.execute("SELECT * FROM edges WHERE deleted=0 ORDER BY created_at,id").fetchall()
            else:
                rows=self._db.execute("SELECT * FROM edges WHERE deleted=0 AND (source_id=? OR target_id=?) ORDER BY created_at,id",(record_id,record_id)).fetchall()
            return [{"id":r["id"],"source_id":r["source_id"],"target_id":r["target_id"],"relation":r["relation"],
                     "polarity":r["polarity"],"data":json.loads(r["data"]),"created_at":r["created_at"]} for r in rows]

    def search(self, query: str, kinds: list[str] | None = None, limit: int = 20) -> list[dict]:
        if not isinstance(query,str) or not query.strip(): return []
        if not isinstance(limit,int) or limit < 1: return []
        with self._lock:
            if self._fts:
                # Quote terms to avoid exposing the FTS query language as an error surface.
                terms=re.findall(r"[\w'-]+",query,flags=re.UNICODE)
                if not terms:return []
                match=" AND ".join('"'+t.replace('"','""')+'"' for t in terms)
                try:
                    if kinds is not None and not kinds:
                        return []
                    kind_clause = " AND r.kind IN (" + ",".join("?" for _ in kinds) + ")" if kinds is not None else ""
                    params = (match, *kinds, limit) if kinds is not None else (match, limit)
                    rows=self._db.execute("SELECT r.* FROM record_fts f JOIN records r ON r.id=f.id WHERE record_fts MATCH ? AND r.deleted=0"+kind_clause+" ORDER BY bm25(record_fts),r.created_at DESC LIMIT ?",params).fetchall()
                except sqlite3.OperationalError:
                    rows=[]
            else:
                rows=self._db.execute("SELECT * FROM records WHERE deleted=0 ORDER BY updated_at DESC").fetchall()
                terms=[t.casefold() for t in re.findall(r"[\w'-]+",query,flags=re.UNICODE)]
                rows=[r for r in rows if all(t in self._searchable(r["data"]).casefold() for t in terms)][:limit]
            if kinds is not None: rows=[r for r in rows if r["kind"] in kinds]
            return [self._envelope(r) for r in rows[:limit]]

    def append_event(self, kind: str, subject_id: str, payload: dict, *, principal: str = "local-user", idempotency_key: str | None = None) -> dict:
        if not isinstance(payload,dict): raise ValidationError("event payload must be an object")
        req={"op":"append_event","kind":kind,"subject_id":subject_id,"payload":payload}
        rh=_hash(_json(req))
        with self._lock, self._transaction():
            previous=self._idempotent_get(idempotency_key,principal,rh)
            if previous is not None:return previous
            event=self._event(kind,subject_id,payload,principal)
            self._idempotent_save(idempotency_key,principal,rh,event)
            return event

    def events(self) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute("SELECT event_id,kind,subject_id,occurred_at,principal,payload_hash,previous_hash,event_hash FROM events ORDER BY seq").fetchall()]

    def verify_ledger(self) -> dict:
        with self._lock:
            rows=self._db.execute("SELECT * FROM events ORDER BY seq").fetchall()
            previous=_GENESIS
            for row in rows:
                fields={"event_id":row["event_id"],"kind":row["kind"],"subject_id":row["subject_id"],
                        "occurred_at":row["occurred_at"],"principal":row["principal"],"payload_hash":row["payload_hash"],
                        "previous_hash":row["previous_hash"]}
                if row["previous_hash"] != previous or row["event_hash"] != _hash(_json(fields)):
                    return {"valid":False,"events_checked":rows.index(row),"broken_event_id":row["event_id"]}
                previous=row["event_hash"]
            # The event row stores a digest of its payload, which itself contains
            # the canonical data hash. Recompute that digest for every retained
            # record version so direct record/history edits are detected too.
            versions = self._db.execute("SELECT * FROM record_versions ORDER BY id,version").fetchall()
            for version in versions:
                try:
                    data = json.loads(version["data"])
                except (ValueError, TypeError):
                    return {"valid":False,"events_checked":len(rows),"head":previous,
                            "records_checked":0,"broken_record_id":version["id"],
                            "broken_version":version["version"]}
                if not isinstance(data, dict):
                    return {"valid":False,"events_checked":len(rows),"head":previous,
                            "records_checked":0,"broken_record_id":version["id"],
                            "broken_version":version["version"]}
                data_hash = _hash(_json(data))
                raw_candidates = [None]
                if version["kind"] == "source":
                    source_text = self._source_text(data)
                    if source_text is not None:
                        raw_candidates.append(_hash(source_text.encode("utf-8")))
                bound = False
                for raw_hash in set(raw_candidates):
                    event_payload = {"kind": version["kind"], "version": version["version"],
                                     "data_hash": data_hash, "raw_hash": raw_hash}
                    payload_hash = _hash(_json(event_payload))
                    found = self._db.execute(
                        "SELECT 1 FROM events WHERE subject_id=? AND payload_hash=? LIMIT 1",
                        (version["id"], payload_hash)).fetchone()
                    if found:
                        bound = True
                        break
                if not bound:
                    return {"valid":False,"events_checked":len(rows),"head":previous,
                            "records_checked":0,"broken_record_id":version["id"],
                            "broken_version":version["version"]}
            records = self._db.execute("SELECT * FROM records WHERE deleted=0 ORDER BY id").fetchall()
            for record in records:
                history = self._db.execute(
                    "SELECT * FROM record_versions WHERE id=? ORDER BY version", (record["id"],)).fetchall()
                if (not history or history[-1]["version"] != record["version"] or
                        len(history) != record["version"] or
                        record["data"] != history[-1]["data"] or
                        record["kind"] != history[-1]["kind"] or
                        record["created_at"] != history[-1]["created_at"] or
                        record["updated_at"] != history[-1]["updated_at"] or
                        record["immutable"] != history[-1]["immutable"]):
                    return {"valid":False,"events_checked":len(rows),"head":previous,
                            "records_checked":len(records),"broken_record_id":record["id"],
                            "broken_version":record["version"]}
            return {"valid":True,"events_checked":len(rows),"head":previous,
                    "records_checked":len(records),"record_versions_checked":len(versions),
                    "integrity_scope":"event_chain_and_retained_record_versions"}

    def _checkpoint_after_purge(self) -> dict:
        """Scrub this SQLite file/WAL where possible; expose reader and media limits.

        This cannot erase backups, snapshots, previously copied files, pages held
        by active readers, or guarantee against storage-device forensic recovery.
        """
        scope = "current SQLite file and WAL only; excludes backups, snapshots, active-reader snapshots, and media forensics"
        with self._lock:
            secure_delete = bool(self._db.execute("PRAGMA secure_delete").fetchone()[0])
            if self.path == ":memory:":
                return {"secure_delete": secure_delete, "wal_checkpoint": "not_applicable", "scope": scope}
            mode = str(self._db.execute("PRAGMA journal_mode").fetchone()[0]).casefold()
            if mode != "wal":
                return {"secure_delete": secure_delete, "wal_checkpoint": "not_applicable", "scope": scope}
            prior_timeout = self._db.execute("PRAGMA busy_timeout").fetchone()[0]
            try:
                # A privacy cleanup should not block for the Store's general
                # 30-second writer timeout on an unrelated long-lived reader.
                self._db.execute("PRAGMA busy_timeout=0")
                busy, log_frames, checkpointed_frames = self._db.execute(
                    "PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                return {"secure_delete": secure_delete,
                        "fts_secure_delete": getattr(self, "_fts_secure_delete", False),
                        "fts_cleanup_mode": getattr(self, "_fts_cleanup_mode", "not_applicable"),
                        "wal_checkpoint": "complete" if not busy else "blocked_by_active_reader",
                        "log_frames": log_frames, "checkpointed_frames": checkpointed_frames,
                        "scope": scope}
            except sqlite3.Error:
                return {"secure_delete": secure_delete,
                        "fts_secure_delete": getattr(self, "_fts_secure_delete", False),
                        "fts_cleanup_mode": getattr(self, "_fts_cleanup_mode", "not_applicable"),
                        "wal_checkpoint": "incomplete", "scope": scope}
            finally:
                self._db.execute(f"PRAGMA busy_timeout={int(prior_timeout)}")

    @staticmethod
    def _record_references(value: Any):
        """Yield IDs referenced by canonical *_id and *_ids fields, at any nesting depth."""
        if isinstance(value, dict):
            if value.get('analysis_kind') == 'evidence_analysis_plan' and not value.get('source_id'):
                key = value.get('analysis_key', '')
                if isinstance(key, str) and key.startswith('evidence-analysis:'):
                    yield key.split(':')[1]
            for key, item in value.items():
                if isinstance(key, str) and key.endswith("_id") and isinstance(item, str):
                    yield item
                elif isinstance(key, str) and key.endswith("_ids") and isinstance(item, (list, tuple, set)):
                    yield from (ref for ref in item if isinstance(ref, str))
                yield from Store._record_references(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from Store._record_references(item)

    @staticmethod
    def _dependency_rank(kind: str) -> int:
        # Record layers let deletion flow from evidence toward derived products, never back
        # from a derived record into unrelated evidence that it cited.
        ranks = {
            "source": 0, "span": 1,
            "claim": 2, "argument": 2, "interpretation": 2,
            "theory": 3, "problem": 3, "mechanism": 4,
            "idea": 5, "decision": 6, "prediction": 6,
            "experiment": 7, "outcome": 8, "learning": 9, "skill": 10,
            "trigger": 10, "trace": 10, "goal": 10, "assessment": 10,
            "policy": 10, "job": 11,
        }
        return ranks.get(kind, 50)

    def purge_source(self, source_id: str, reason: str, *, principal: str = "local-user") -> dict:
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError("purge reason is required")
        with self._lock, self._transaction():
            source = self._db.execute("SELECT * FROM records WHERE id=? AND deleted=0", (source_id,)).fetchone()
            if source is None or source["kind"] != "source":
                raise NotFound(source_id)

            # Dependency references are read recursively, so jobs and cached nested results
            # invalidate just like direct source/span/claim references.
            live = self._db.execute("SELECT id,kind,data FROM records WHERE deleted=0").fetchall()
            rows_by_id = {row["id"]: row for row in live}
            edges = self._db.execute("SELECT source_id,target_id FROM edges WHERE deleted=0").fetchall()
            doomed = {source_id}
            changed = True
            while changed:
                changed = False
                for row in live:
                    rid = row["id"]
                    if rid in doomed or row["kind"] == "source":
                        continue  # a co-source is evidence, not a descendant to erase
                    data = json.loads(row["data"])
                    if any(ref in doomed for ref in self._record_references(data)):
                        doomed.add(rid)
                        changed = True
                for edge in edges:
                    src, dst = edge["source_id"], edge["target_id"]
                    if src not in rows_by_id or dst not in rows_by_id:
                        continue
                    src_kind, dst_kind = rows_by_id[src]["kind"], rows_by_id[dst]["kind"]
                    src_rank, dst_rank = self._dependency_rank(src_kind), self._dependency_rank(dst_kind)
                    # Either edge orientation can encode lineage. Follow only toward the more
                    # derived endpoint, so theory->source evidence invalidates theory without
                    # cascading from that theory back into other cited sources/claims.
                    if src in doomed and dst not in doomed and dst_kind != "source" and dst_rank > src_rank:
                        doomed.add(dst)
                        changed = True
                    if dst in doomed and src not in doomed and src_kind != "source" and src_rank > dst_rank:
                        doomed.add(src)
                        changed = True

            raw_hashes = set()
            if self.raw_dir is not None:
                for rid in doomed:
                    row = rows_by_id.get(rid)
                    if row and row["kind"] == "source":
                        source_text = self._source_text(json.loads(row["data"]))
                        if source_text is not None:
                            raw_hashes.add(_hash(source_text.encode("utf-8")))

            placeholders = ",".join("?" for _ in doomed)
            ids = tuple(doomed)
            self._db.execute(f"DELETE FROM record_versions WHERE id IN ({placeholders})", ids)
            self._db.execute(f"DELETE FROM records WHERE id IN ({placeholders})", ids)
            self._db.execute(f"DELETE FROM edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})", ids + ids)

            # Put responses can contain the original source envelope; remove every cache entry
            # whose nested response references any purged record. Journal events retain digests only.
            for row in self._db.execute("SELECT principal,key,response FROM idempotency").fetchall():
                try:
                    response = json.loads(row["response"])
                except ValueError:
                    continue
                response_id = response.get("id") if isinstance(response, dict) else None
                if response_id in doomed or any(ref in doomed for ref in self._record_references(response)):
                    self._db.execute("DELETE FROM idempotency WHERE principal=? AND key=?", (row["principal"], row["key"]))

            if self._fts and self._fts_secure_delete:
                for rid in doomed:
                    self._db.execute("DELETE FROM record_fts WHERE id=?", (rid,))
                self._fts_cleanup_mode = "secure_delete"
            elif self._fts:
                # Older FTS5 builds lack the secure-delete command. Drop and
                # rebuild the index under SQLite secure_delete so stale terms
                # are not retained in FTS tombstone segments.
                self._db.execute("DROP TABLE record_fts")
                self._db.execute("CREATE VIRTUAL TABLE record_fts USING fts5(id UNINDEXED, kind UNINDEXED, content)")
                live_records = self._db.execute("SELECT id,kind,data FROM records WHERE deleted=0").fetchall()
                for row in live_records:
                    self._db.execute("INSERT INTO record_fts(id,kind,content) VALUES(?,?,?)",
                                     (row["id"], row["kind"], self._searchable(row["data"])))
                self._fts_cleanup_mode = "drop_rebuild_secure_delete"
            self._event("SOURCE_PURGED", source_id,
                        {"reason_hash": _hash(reason), "deleted_count": len(doomed)}, principal)
            response = {"source_id": source_id, "deleted_ids": sorted(doomed), "deleted_count": len(doomed)}

        # Checkpoint only after the deletion transaction commits. An independent
        # reader can keep an older WAL snapshot alive; report that instead of
        # claiming that every on-disk copy has been erased.
        response["storage_cleanup"] = self._checkpoint_after_purge()

        if self.raw_dir is not None:
            remaining = self._db.execute("SELECT data FROM records WHERE kind='source' AND deleted=0").fetchall()
            remaining_hashes = set()
            for row in remaining:
                source_text = self._source_text(json.loads(row[0]))
                if source_text is not None:
                    remaining_hashes.add(_hash(source_text.encode("utf-8")))
            for digest in raw_hashes - remaining_hashes:
                target = self.raw_dir / digest[:2] / digest
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass
        return response

    def close(self) -> None:
        with self._lock:
            self._db.close()
