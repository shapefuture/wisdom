import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from parallel import select_cells  # noqa: E402


REVISION = "git:abc123"
CONTRACTS = {"api": "v1", "schema": "v2"}


def cell(task_id, **overrides):
    value = {
        "task_id": task_id,
        "base_revision": REVISION,
        "read_paths": [f"docs/{task_id}.md"],
        "write_paths": [f"src/{task_id}.py"],
        "contract_reads": {},
        "contract_writes": [],
        "shared_resources": [],
        "acceptance": ["behavior is complete"],
        "quality_commands": [["python3", "-m", "unittest"]],
        "outputs": [f"src/{task_id}.py"],
        "role": "worker",
    }
    value.update(overrides)
    return value


class SelectCellsTests(unittest.TestCase):
    def plan(self, cells, ready=None, **kwargs):
        return select_cells(cells, ready if ready is not None else {c["task_id"] for c in cells}, REVISION, CONTRACTS, **kwargs)

    def test_selects_disjoint_live_ready_cells_and_returns_original_objects(self):
        a, b = cell("a"), cell("b")
        result = self.plan([a, b])
        self.assertEqual(result["selected"], [a, b])
        self.assertIs(result["selected"][0], a)
        self.assertEqual(result["rejected"], [])

    def test_rejects_overlapping_write_scopes(self):
        a = cell("a", write_paths=["src/shared/**"], outputs=["src/shared/a.py"])
        b = cell("b", write_paths=["src/shared/b.py"], outputs=["src/shared/b.py"])
        result = self.plan([a, b])
        self.assertEqual([c["task_id"] for c in result["selected"]], ["a"])
        self.assertIn("write scope overlaps", result["rejected"][0]["reason"])

    def test_rejects_read_write_overlap(self):
        a = cell("a", write_paths=["src/change.py"], outputs=["src/change.py"])
        b = cell("b", read_paths=["src/change.py"])
        result = self.plan([a, b])
        self.assertEqual([c["task_id"] for c in result["selected"]], ["a"])
        self.assertIn("read scope overlaps", result["rejected"][0]["reason"])

    def test_rejects_traversal_and_absolute_paths(self):
        bad = cell("bad", write_paths=["src/../secrets"], outputs=["src/../secrets"])
        absolute = cell("absolute", read_paths=["/etc/passwd"])
        result = self.plan([bad, absolute])
        self.assertEqual(result["selected"], [])
        self.assertEqual(len(result["rejected"]), 2)
        self.assertTrue(all("repository-relative" in item["reason"] for item in result["rejected"]))

    def test_rejects_stale_base_revision_and_contract_version(self):
        stale = cell("stale", base_revision="git:old")
        old_contract = cell("contract", contract_reads={"api": "v0"})
        result = self.plan([stale, old_contract])
        self.assertEqual(result["selected"], [])
        self.assertIn("base_revision", result["rejected"][0]["reason"])
        self.assertIn("contract version", result["rejected"][1]["reason"])

    def test_rejects_missing_acceptance_and_quality_criteria(self):
        no_acceptance = cell("accept", acceptance=[])
        no_quality = cell("quality", quality_commands=[])
        result = self.plan([no_acceptance, no_quality])
        self.assertEqual(result["selected"], [])
        self.assertIn("acceptance", result["rejected"][0]["reason"])
        self.assertIn("quality_commands", result["rejected"][1]["reason"])

    def test_live_ready_ids_are_authoritative_and_static_ready_is_ignored(self):
        cell_a = cell("a", ready=True)
        result = self.plan([cell_a], ready=set())
        self.assertEqual(result["selected"], [])
        self.assertIn("live ready_ids", result["rejected"][0]["reason"])

    def test_integrator_and_shared_wiring_are_excluded(self):
        integrator = cell("integrator", role="integrator")
        wiring = cell("wiring", shared_wiring=True)
        result = self.plan([integrator, wiring])
        self.assertEqual(result["selected"], [])
        self.assertTrue(all("excluded from worker sweeps" in item["reason"] for item in result["rejected"]))

    def test_rejects_shared_resources_and_contract_conflicts(self):
        first = cell("first", shared_resources=["firebase-emulator"])
        second = cell("second", shared_resources=["firebase-emulator"])
        third = cell("third", contract_writes=["api"], priority=0)
        fourth = cell("fourth", contract_reads={"api": "v1"})
        result = self.plan([first, second, third, fourth])
        self.assertEqual([c["task_id"] for c in result["selected"]], ["third", "first"])
        reasons = {item["task_id"]: item["reason"] for item in result["rejected"]}
        self.assertIn("shared resource", reasons["second"])
        self.assertIn("contract read overlaps write", reasons["fourth"])

    def test_greedy_order_uses_rank_then_priority_then_task_id(self):
        cells = [
            cell("z", critical_path_rank=4, priority=0),
            cell("b", critical_path_rank=5, priority=1),
            cell("a", critical_path_rank=5, priority=1),
            cell("c", critical_path_rank=5),
        ]
        result = self.plan(cells, max_workers=4)
        self.assertEqual([c["task_id"] for c in result["selected"]], ["a", "b", "c", "z"])

    def test_rejects_outputs_outside_write_scope(self):
        outside = cell("outside", write_paths=["src/owned/**"], outputs=["docs/result.md"])
        result = self.plan([outside])
        self.assertEqual(result["selected"], [])
        self.assertIn("covered", result["rejected"][0]["reason"])

    def test_rejects_every_occurrence_of_duplicate_task_id(self):
        result = self.plan([cell("same"), cell("same", priority=1)])
        self.assertEqual(result["selected"], [])
        self.assertEqual(len(result["rejected"]), 2)
        self.assertTrue(all(item["reason"] == "duplicate task_id" for item in result["rejected"]))

    def test_rejects_contract_write_read_conflicts_in_either_order(self):
        reader = cell("reader", contract_reads={"schema": "v2"})
        writer = cell("writer", contract_writes=["schema"])
        result = self.plan([reader, writer])
        self.assertEqual([c["task_id"] for c in result["selected"]], ["reader"])
        self.assertIn("contract write overlaps read", result["rejected"][0]["reason"])


if __name__ == "__main__":
    unittest.main()

