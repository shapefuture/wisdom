import tempfile
import threading
import unittest
from pathlib import Path

from wisdom.errors import Conflict, NotFound
from wisdom.store import Store


class StoreTests(unittest.TestCase):
    def test_reopen_versions_search_and_history(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "records.sqlite"
            store = Store(db)
            first = store.put("idea", {"title":"Quiet feedback loops", "description":"feedback loops aid repair"})
            second = store.put("idea", {"title":"Revised feedback loops"}, record_id=first["id"], expected_version=1)
            self.assertEqual(second["version"], 2)
            self.assertEqual([x["version"] for x in store.history(first["id"])], [1, 2])
            store.close()
            store = Store(db)
            self.assertEqual(store.get(first["id"])["data"]["title"], "Revised feedback loops")
            self.assertEqual(store.get(first["id"], 1)["data"]["title"], "Quiet feedback loops")
            self.assertEqual(store.search("feedback loops")[0]["id"], first["id"])
            self.assertTrue(store.verify_ledger()["valid"])
            store.close()

    def test_cas_and_immutable_span_prediction(self):
        store = Store()
        span = store.put("span", {"source_id":"src", "text":"original"})
        pred = store.put("prediction", {"statement":"will improve"})
        with self.assertRaises(Conflict):
            store.put("span", {"text":"changed"}, record_id=span["id"], expected_version=1)
        with self.assertRaises(Conflict):
            store.put("prediction", {"statement":"changed"}, record_id=pred["id"], expected_version=1)
        rec = store.put("claim", {"text":"v1"})
        with self.assertRaises(Conflict):
            store.put("claim", {"text":"bad CAS"}, record_id=rec["id"], expected_version=0)
        with self.assertRaises(Conflict):
            store.put("claim", {"text":"stale"}, record_id=rec["id"], expected_version=2)
        self.assertEqual(store.get(rec["id"])["version"], 1)

    def test_idempotency_binds_payload_and_principal(self):
        store = Store()
        one = store.put("source", {"title":"A"}, idempotency_key="k", principal="alice")
        same = store.put("source", {"title":"A"}, idempotency_key="k", principal="alice")
        self.assertEqual(one["id"], same["id"])
        with self.assertRaises(Conflict):
            store.put("source", {"title":"B"}, idempotency_key="k", principal="alice")
        other = store.put("source", {"title":"B"}, idempotency_key="k", principal="bob")
        self.assertNotEqual(one["id"], other["id"])
        ev1 = store.append_event("NOTE", "x", {"memo":"one"}, idempotency_key="e")
        ev2 = store.append_event("NOTE", "x", {"memo":"one"}, idempotency_key="e")
        self.assertEqual(ev1, ev2)
        with self.assertRaises(Conflict):
            store.append_event("NOTE", "x", {"memo":"two"}, idempotency_key="e")

    def test_edges_and_fts_filter(self):
        store = Store()
        a = store.put("source", {"title":"Orchard notes"})
        b = store.put("claim", {"text":"Orchard observations"})
        edge = store.link(a["id"], b["id"], "SUPPORTS", polarity="positive", data={"scope":"local"})
        self.assertEqual(store.edges(b["id"])[0], edge)
        found = store.search("orchard", kinds=["claim"])
        self.assertEqual([r["id"] for r in found], [b["id"]])

    def test_content_addressed_original_and_purge_cascade(self):
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw"
            store = Store(Path(td) / "db.sqlite", raw_dir=raw)
            source = store.put("source", {"text":"private transcript", "rights":{"allowed":True,"private":True}}, idempotency_key="private-source")
            span = store.put("span", {"source_id":source["id"], "text":"private transcript"})
            claim = store.put("claim", {"source_id":source["id"], "span_ids":[span["id"]], "text":"derived"})
            independent = store.put("idea", {"title":"separate"})
            edge = store.link(source["id"], independent["id"], "INSPIRED_BY")
            obj = next(raw.glob("*/*"))
            self.assertEqual(obj.read_text(), "private transcript")
            result = store.purge_source(source["id"], "user rights request")
            self.assertEqual(result["deleted_count"], 4)
            for rid in (source["id"], span["id"], claim["id"]):
                with self.assertRaises(NotFound): store.get(rid)
                self.assertEqual(store.search("private"), [])
                with self.assertRaises(NotFound): store.history(rid)
            self.assertFalse(obj.exists())
            self.assertEqual(store.edges(), [])
            self.assertNotIn(independent["id"], [r["id"] for r in store.list()])
            events = store.events()
            self.assertTrue(all("private transcript" not in str(e) for e in events))
            cached = store._db.execute("SELECT response FROM idempotency").fetchall()
            self.assertTrue(all("private transcript" not in row[0] for row in cached))
            self.assertTrue(store.verify_ledger()["valid"])

    def test_purge_secure_delete_removes_unique_marker_from_bounded_file_backed_store(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "bounded-purge.sqlite"
            raw = Path(td) / "raw"
            marker = "UNIQUE_PRIVATE_PURGE_MARKER_7d14aa"
            store = Store(db, raw_dir=raw)
            self.assertEqual(store._db.execute("PRAGMA secure_delete").fetchone()[0], 1)
            self.assertTrue(store._fts)
            source = store.put("source", {"text": marker, "rights": {"allowed": True}})
            derived = store.put("claim", {"source_id": source["id"], "text": f"quote {marker}"})
            self.assertEqual({r["id"] for r in store.search(marker)}, {source["id"], derived["id"]})
            result = store.purge_source(source["id"], "bounded retention test")
            self.assertEqual(result["storage_cleanup"]["wal_checkpoint"], "complete")
            self.assertIn(result["storage_cleanup"]["fts_cleanup_mode"],
                          {"secure_delete", "drop_rebuild_secure_delete"})
            store.close()

            db_artifacts = [p for p in Path(td).glob("bounded-purge.sqlite*") if p.is_file()]
            self.assertTrue(db_artifacts)
            for artifact in db_artifacts + [p for p in raw.rglob("*") if p.is_file()]:
                with self.subTest(artifact=artifact.name):
                    self.assertNotIn(marker.encode("utf-8"), artifact.read_bytes())

    def test_purge_reports_wal_checkpoint_blocked_by_active_reader(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "reader-purge.sqlite"
            store = Store(db)
            marker = "ACTIVE_READER_PRIVATE_MARKER"
            source = store.put("source", {"text": marker, "rights": {"allowed": True}})
            reader = __import__("sqlite3").connect(db, isolation_level=None)
            try:
                reader.execute("BEGIN")
                reader.execute("SELECT data FROM records WHERE id=?", (source["id"],)).fetchone()
                result = store.purge_source(source["id"], "reader limitation test")
                self.assertEqual(result["storage_cleanup"]["wal_checkpoint"], "blocked_by_active_reader")
                self.assertEqual(store.list("source"), [])
                wal = Path(str(db) + "-wal")
                self.assertTrue(wal.exists())
                self.assertIn(marker.encode("utf-8"), wal.read_bytes())
            finally:
                reader.rollback()
                reader.close()
                store._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                store.close()
            for artifact in Path(td).glob("reader-purge.sqlite*"):
                if artifact.is_file():
                    self.assertNotIn(marker.encode("utf-8"), artifact.read_bytes())

    def test_purge_rebuilds_fts_when_secure_delete_command_is_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "fts-fallback.sqlite"
            marker = "FTS_FALLBACK_PRIVATE_MARKER"
            store = Store(db)
            if not store._fts:
                store.close()
                self.skipTest("SQLite build has no FTS5")
            source = store.put("source", {"text": marker, "rights": {"allowed": True}})
            # Exercise the fallback used on SQLite builds without FTS5's
            # secure-delete command.
            try:
                store._db.execute("INSERT INTO record_fts(record_fts, rank) VALUES('secure-delete', 0)")
            except __import__("sqlite3").OperationalError:
                pass
            store._fts_secure_delete = False
            result = store.purge_source(source["id"], "FTS fallback test")
            self.assertEqual(result["storage_cleanup"]["fts_cleanup_mode"], "drop_rebuild_secure_delete")
            store.close()
            for artifact in Path(td).glob("fts-fallback.sqlite*"):
                if artifact.is_file():
                    self.assertNotIn(marker.encode("utf-8"), artifact.read_bytes())

    def test_ledger_binds_current_and_historical_record_versions(self):
        store = Store()
        record = store.put("idea", {"title": "original"})
        self.assertTrue(store.verify_ledger()["valid"])
        store._db.execute("UPDATE records SET data=? WHERE id=?", ('{"title":"current tamper"}', record["id"]))
        current_result = store.verify_ledger()
        self.assertFalse(current_result["valid"])
        self.assertEqual(current_result["broken_record_id"], record["id"])
        store.close()

        store = Store()
        record = store.put("idea", {"title": "version one"})
        record2 = store.put("idea", {"title": "version two"}, record_id=record["id"], expected_version=1)
        self.assertEqual(record2["version"], 2)
        self.assertTrue(store.verify_ledger()["valid"])
        store._db.execute("UPDATE record_versions SET data=? WHERE id=? AND version=1",
                          ('{"title":"history tamper"}', record["id"]))
        history_result = store.verify_ledger()
        self.assertFalse(history_result["valid"])
        self.assertEqual(history_result["broken_version"], 1)
        store._db.execute("UPDATE record_versions SET data=? WHERE id=? AND version=1",
                          ("{broken-json", record["id"]))
        malformed_result = store.verify_ledger()
        self.assertFalse(malformed_result["valid"])
        self.assertEqual(malformed_result["broken_version"], 1)
        store.close()

    def test_schema_version_is_set_and_future_schema_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "schema.sqlite"
            store = Store(db)
            self.assertEqual(store._db.execute("PRAGMA user_version").fetchone()[0], 1)
            store.close()
            raw = __import__("sqlite3").connect(db)
            raw.execute("PRAGMA user_version=2")
            raw.close()
            with self.assertRaisesRegex(RuntimeError, "newer than supported"):
                Store(db)

    def test_purge_follows_nested_and_bidirectional_lineage_but_preserves_co_source(self):
        store = Store()
        source_a = store.put("source", {"original_text":"private A", "rights":{"allowed":True}})
        source_b = store.put("source", {"text":"independent B", "rights":{"allowed":True}})
        span_a = store.put("span", {"source_id":source_a["id"], "text":"private A"})
        claim_a = store.put("claim", {"source_id":source_a["id"], "span_ids":[span_a["id"]], "text":"derived claim"})
        claim_b = store.put("claim", {"source_id":source_b["id"], "text":"independent claim"})
        theory = store.put("theory", {"source_ids":[source_a["id"],source_b["id"]], "claim_ids":[claim_a["id"],claim_b["id"]]})
        idea = store.put("idea", {"theory_id":theory["id"], "description":"cached application"})
        job = store.put("job", {"input":{"source_id":source_a["id"]}, "result":{"output_record_id":idea["id"], "cached":"private A"}})
        # Both evidence->derived and derived->evidence edge orientations are supported.
        store.link(span_a["id"], claim_a["id"], "ATTRIBUTES_TO")
        store.link(theory["id"], claim_a["id"], "USES_EVIDENCE")
        store.link(idea["id"], theory["id"], "INSPIRED_BY")

        result = store.purge_source(source_a["id"], "rights request")
        expected = {source_a["id"],span_a["id"],claim_a["id"],theory["id"],idea["id"],job["id"]}
        self.assertEqual(set(result["deleted_ids"]), expected)
        self.assertEqual(store.get(source_b["id"])["data"]["text"], "independent B")
        self.assertEqual(store.get(claim_b["id"])["data"]["text"], "independent claim")
        self.assertEqual(store.search("private A"), [])
        self.assertNotIn("private A", str(store.events()))

    def test_raw_storage_supports_original_text_and_text_alias_deduplication(self):
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw"
            store = Store(Path(td) / "db.sqlite", raw_dir=raw)
            first = store.put("source", {"original_text":"shared original", "rights":{"allowed":True}})
            second = store.put("source", {"text":"shared original", "rights":{"allowed":True}})
            obj = next(raw.glob("*/*"))
            self.assertEqual(obj.read_text(), "shared original")
            store.purge_source(first["id"], "remove first copy")
            self.assertTrue(obj.exists())
            store.purge_source(second["id"], "remove last copy")
            self.assertFalse(obj.exists())

    def test_ledger_tamper_detected(self):
        store = Store()
        store.put("idea", {"title":"ledger entry"})
        with store._lock:
            store._db.execute("UPDATE events SET principal='changed' WHERE seq=1")
        result = store.verify_ledger()
        self.assertFalse(result["valid"])
        self.assertEqual(result["events_checked"], 0)

    def test_concurrent_compare_and_swap_has_single_winner(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "c.sqlite")
            store = Store(db)
            rec = store.put("decision", {"question":"initial"})
            barrier = threading.Barrier(3)
            outcomes = []
            def writer(value):
                local = Store(db)
                barrier.wait()
                try:
                    local.put("decision", {"question":value}, record_id=rec["id"], expected_version=1)
                    outcomes.append("ok")
                except Conflict:
                    outcomes.append("conflict")
                finally: local.close()
            threads = [threading.Thread(target=writer, args=(v,)) for v in ("left", "right")]
            for t in threads: t.start()
            barrier.wait()
            for t in threads: t.join()
            self.assertCountEqual(outcomes, ["ok", "conflict"])
            self.assertEqual(store.get(rec["id"])["version"], 2)
            store.close()


if __name__ == "__main__": unittest.main()
