import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bootstrap
import delivery
import leases
import package as portable_package

PACKAGE = Path(__file__).resolve().parents[1]


def mission():
    value = json.loads((PACKAGE / "templates/mission.json").read_text())
    value["objective"] = "Implement the whole approved test project"
    value["roots"] = [{"id": "ROOT", "name": "Complete program"}]
    value["requirements"] = [{"id": "REQ-1", "task_ids": ["TASK"], "acceptance": "A real behavior works and fails safely"}]
    value["quality"]["required_commands"] = [["python3", "-m", "unittest"]]
    return value


def snapshot():
    return {"items": [
        {"id": "ROOT", "issue_type": "epic", "status": "open", "title": "Complete program", "acceptance_criteria": "Whole approved program is verified"},
        {"id": "TASK", "issue_type": "task", "parent": "ROOT", "status": "open", "title": "Behavior", "acceptance_criteria": "A real behavior works and fails safely", "notes": "PRIVATE-NOTE"},
    ], "ready_ids": ["TASK"]}


def accept(candidate="git:verified", reviewer="reviewer", builder="builder"):
    return {"delivery": {"acceptance": {
        "decision": "accepted", "candidate": candidate, "requirements": ["REQ-1"],
        "evidence": [{"ref": "test-artifact", "outcome": "passed"}],
        "independent_review": {"ref": "review-artifact", "reviewer": reviewer, "builder": builder, "decision": "accepted", "candidate": candidate},
    }}}


def cell(task_id, revision):
    return {"task_id": task_id, "base_revision": revision, "read_paths": [f"docs/{task_id}.md"], "write_paths": [f"src/{task_id}.py"],
            "contract_reads": {}, "contract_writes": [], "shared_resources": [], "acceptance": ["Real output"],
            "quality_commands": [["python3", "-m", "unittest"]], "outputs": [f"src/{task_id}.py"]}


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.config, self.data = mission(), snapshot()

    def inspect(self):
        return delivery.inspect_scope(self.project, self.config, self.data)

    def test_missing_scope_and_requirement_tasks_are_rejected(self):
        self.data["items"] = self.data["items"][1:]
        with self.assertRaisesRegex(delivery.DeliveryError, "Missing declared"):
            self.inspect()
        self.data = snapshot()
        self.config["requirements"][0]["task_ids"] = ["ABSENT"]
        with self.assertRaisesRegex(delivery.DeliveryError, "missing or detached"):
            self.inspect()

    def test_dynamic_descendant_is_in_scope_and_notes_are_not_reported(self):
        self.data["items"].append({"id": "NEW", "parent": "TASK", "status": "open", "issue_type": "task"})
        report = self.inspect()
        self.assertIn("NEW", report["allowed"])
        self.assertNotIn("PRIVATE-NOTE", delivery.render(self.config, report))

    def test_active_task_with_blocking_dependency_is_not_executable(self):
        task = self.data["items"][1]
        task["status"] = "in_progress"
        task["dependencies"] = [{"depends_on_id": "PRE", "type": "blocks"}]
        self.data["items"].append({"id": "PRE", "status": "open", "issue_type": "task", "parent": "ROOT"})
        self.data["ready_ids"] = []
        with self.assertRaisesRegex(delivery.DeliveryError, "Active status alone"):
            delivery.validate_selection(self.inspect(), "TASK")
        self.data["items"][-1]["status"] = "closed"
        delivery.validate_selection(self.inspect(), "TASK")

    def test_relationship_edges_are_not_false_implementation_blockers(self):
        self.data["items"].append({"id": "RELATED", "status": "open", "issue_type": "task", "parent": "ROOT"})
        self.data["items"][1]["dependencies"] = [{"depends_on_id": "RELATED", "type": "relates_to"}]
        delivery.validate_selection(self.inspect(), "TASK")
        self.data["items"][1]["dependencies"][0]["type"] = "unknown-prerequisite"
        with self.assertRaisesRegex(delivery.DeliveryError, "blocking dependencies"):
            self.inspect()

    def test_inconsistent_ready_frontier_and_hierarchy_are_rejected(self):
        self.data["items"][1]["status"] = "closed"
        with self.assertRaisesRegex(delivery.DeliveryError, "closed or blocked"):
            self.inspect()
        self.data = snapshot()
        self.data["items"][1]["parent"] = "TASK"
        with self.assertRaisesRegex(delivery.DeliveryError, "cycle"):
            self.inspect()

    def test_closed_status_does_not_prove_acceptance(self):
        for row in self.data["items"]:
            row["status"] = "closed"
        self.data["ready_ids"] = []
        with self.assertRaisesRegex(delivery.DeliveryError, "lacks a recorded"):
            delivery.require_complete(self.config, self.inspect())
        for row in self.data["items"]:
            row["metadata"] = accept()
        self.assertIn("cannot authenticate", delivery.require_complete(self.config, self.inspect(), "git:verified"))

    def test_missing_live_acceptance_criteria_prevents_completion(self):
        for row in self.data["items"]:
            row.update(status="closed", metadata=accept())
        self.data["ready_ids"] = []
        self.data["items"][1]["acceptance_criteria"] = ""
        with self.assertRaisesRegex(delivery.DeliveryError, "live acceptance criteria are missing"):
            delivery.require_complete(self.config, self.inspect())

    def test_stale_builder_review_and_unobserved_evidence_fail_acceptance(self):
        for row in self.data["items"]:
            row.update(status="closed", metadata=accept())
        self.data["ready_ids"] = []
        with self.assertRaisesRegex(delivery.DeliveryError, "stale"):
            delivery.require_complete(self.config, self.inspect(), "git:new")
        self.data["items"][1]["metadata"] = accept(reviewer="same", builder="same")
        with self.assertRaisesRegex(delivery.DeliveryError, "builder"):
            delivery.require_complete(self.config, self.inspect())
        self.data["items"][1]["metadata"] = accept()
        self.data["items"][1]["metadata"]["delivery"]["acceptance"]["evidence"][0]["outcome"] = "unrun"
        with self.assertRaisesRegex(delivery.DeliveryError, "lacks a recorded"):
            delivery.require_complete(self.config, self.inspect())

    def test_requirement_acceptance_coverage_is_required(self):
        for row in self.data["items"]:
            row.update(status="closed", metadata=accept())
        self.data["ready_ids"] = []
        self.data["items"][1]["metadata"]["delivery"]["acceptance"]["requirements"] = []
        with self.assertRaisesRegex(delivery.DeliveryError, "verified requirement coverage"):
            delivery.require_complete(self.config, self.inspect())

    def test_missing_cli_never_reads_an_export(self):
        with patch.dict(delivery.os.environ, {}, clear=True), patch.object(delivery.shutil, "which", return_value=None):
            with self.assertRaisesRegex(delivery.DeliveryError, "do not initialize/import or read an export"):
                delivery.Tracker(self.project, self.config).snapshot()

    def test_configured_absolute_dolt_root_binds_live_tracker_without_local_fallback(self):
        live_root = self.project / "live-dolt"
        live_root.mkdir()
        beads_dir = self.project / ".beads"
        beads_dir.mkdir()
        self.config["tracker"]["beads_dir"] = ".beads"
        self.config["tracker"]["dolt_root"] = str(live_root)
        ambient_dolt = self.project / "ambient-dolt"
        ambient_dolt.mkdir()
        ambient_beads = self.project / "ambient-beads"
        ambient_beads.mkdir()
        with patch.dict(delivery.os.environ, {"DOLT_ROOT_PATH": str(ambient_dolt), "BEADS_DIR": str(ambient_beads)}, clear=True), \
                patch.object(delivery.shutil, "which", return_value="/bin/bd"), \
                patch.object(delivery.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "{}", "")) as run:
            delivery.Tracker(self.project, self.config).run("list")
        self.assertEqual(run.call_args.kwargs["env"]["DOLT_ROOT_PATH"], str(live_root.resolve()))
        self.assertEqual(run.call_args.kwargs["env"]["BEADS_DIR"], str(beads_dir.resolve()))
        self.assertFalse((self.project / ".delivery/runtime/dolt").exists())

    def test_missing_configured_absolute_dolt_root_fails_closed(self):
        live_root = self.project / "missing-live-dolt"
        fallback = self.project / "ambient-dolt"
        fallback.mkdir()
        self.config["tracker"]["dolt_root"] = str(live_root)
        with patch.dict(delivery.os.environ, {"DOLT_ROOT_PATH": str(fallback)}, clear=True), \
                patch.object(delivery.shutil, "which", return_value="/bin/bd"), \
                patch.object(delivery.subprocess, "run") as run:
            with self.assertRaisesRegex(delivery.DeliveryError, "refusing to initialize or use another database"):
                delivery.Tracker(self.project, self.config).run("list")
        run.assert_not_called()
        self.assertFalse(live_root.exists())

    def test_missing_relative_dolt_root_fails_closed_without_creating_a_database(self):
        relative_root = self.project / ".delivery/runtime/dolt"
        with patch.dict(delivery.os.environ, {}, clear=True), \
                patch.object(delivery.shutil, "which", return_value="/bin/bd"), \
                patch.object(delivery.subprocess, "run") as run:
            with self.assertRaisesRegex(delivery.DeliveryError, "refusing to initialize or use another database"):
                delivery.Tracker(self.project, self.config).run("list")
        run.assert_not_called()
        self.assertFalse(relative_root.exists())

    def test_missing_configured_beads_workspace_fails_closed(self):
        fallback = self.project / "ambient-beads"
        fallback.mkdir()
        self.config["tracker"]["beads_dir"] = ".missing-beads"
        with patch.dict(delivery.os.environ, {"BEADS_DIR": str(fallback)}, clear=True), \
                patch.object(delivery.shutil, "which", return_value="/bin/bd"), \
                patch.object(delivery.subprocess, "run") as run:
            with self.assertRaisesRegex(delivery.DeliveryError, "refusing tracker auto-discovery"):
                delivery.Tracker(self.project, self.config).run("list")
        run.assert_not_called()
        self.assertFalse((self.project / ".missing-beads").exists())

    def test_configured_beads_paths_must_be_nonempty_strings(self):
        for key in ["binary", "beads_dir", "dolt_root"]:
            config = mission()
            config["tracker"][key] = []
            with self.subTest(key=key), self.assertRaisesRegex(delivery.DeliveryError, f"Configured Beads {key}"):
                delivery.validate_config(config)

    def test_mission_reference_checks_every_summary_field(self):
        (self.project / ".delivery").mkdir()
        (self.project / ".delivery/mission.json").write_text(json.dumps(self.config))
        reference = json.loads(delivery.mission_memory(self.config, self.project))
        self.assertEqual(delivery.mission_memory_mismatches(reference, self.config, self.project), [])
        stale_values = {
            "objective": "stale objective",
            "mission_file": "other.json",
            "mission_sha256": "0" * 64,
            "root_ids": ["OTHER"],
            "linked_task_ids": ["OTHER"],
            "authorization": {"implementation": False},
            "constraints": ["stale constraint"],
            "requirement_count": 999,
            "scope_record_count": -1,
            "unresolved_acceptance_criteria": ["OTHER"],
            "contract_versions": {"contract": "stale"},
        }
        for field, stale_value in stale_values.items():
            with self.subTest(field=field):
                tampered = {**reference, field: stale_value}
                self.assertEqual(delivery.mission_memory_mismatches(tampered, self.config, self.project), [field])
        self.assertEqual(delivery.mission_memory_mismatches([], self.config, self.project), ["<not-an-object>"])

    def test_artifact_symlink_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.project / "escape").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(delivery.DeliveryError, "escapes"):
                delivery.safe_path(self.project, "escape/file")


class FakeTracker:
    def __init__(self, fail_comment=False):
        self.memory, self.comments, self.fail_comment = {}, [], fail_comment

    def run(self, name, values=None, **kwargs):
        values = values or {}
        if name == "remember":
            self.memory[values["key"]] = values["text"]
            return "saved"
        if name == "comments":
            return self.comments
        if name == "comment":
            if self.fail_comment:
                raise delivery.DeliveryError("unavailable")
            self.comments.append({"text": values["text"]})
            return "saved"
        raise AssertionError(name)


class HandoffTests(unittest.TestCase):
    def args(self, next_task="TASK"):
        return argparse.Namespace(task="TASK", next=next_task, completed="Concrete behavior", remaining="Other criteria remain", evidence="Relevant checks passed; no user session", candidate="git:verified", blocker="")

    def test_partial_write_retains_continuation_and_retry_deduplicates(self):
        config, data = mission(), snapshot()
        with tempfile.TemporaryDirectory() as directory:
            report = delivery.inspect_scope(Path(directory), config, data)
        tracker = FakeTracker(fail_comment=True)
        with self.assertRaisesRegex(delivery.DeliveryError, "PARTIAL HANDOFF"):
            delivery.persist_handoff(tracker, config, report, self.args())
        self.assertEqual(json.loads(tracker.memory[config["memory_keys"]["handoff"]])["next"], "TASK")
        tracker.fail_comment = False
        delivery.persist_handoff(tracker, config, report, self.args())
        delivery.persist_handoff(tracker, config, report, self.args())
        self.assertEqual(len(tracker.comments), 1)

    def test_no_next_requires_no_eligible_work_and_exact_blocker(self):
        config, data = mission(), snapshot()
        with tempfile.TemporaryDirectory() as directory:
            report = delivery.inspect_scope(Path(directory), config, data)
            with self.assertRaisesRegex(delivery.DeliveryError, "Eligible work exists"):
                delivery.persist_handoff(FakeTracker(), config, report, self.args(None))
            data["ready_ids"] = []
            data["items"][1]["blocked"] = True
            report = delivery.inspect_scope(Path(directory), config, data)
        args = self.args(None)
        with self.assertRaisesRegex(delivery.DeliveryError, "exact blockers"):
            delivery.persist_handoff(FakeTracker(), config, report, args)
        args.blocker = "TASK requires a participant; research owner must arrange a consented session"
        delivery.persist_handoff(FakeTracker(), config, report, args)


class BootstrapTests(unittest.TestCase):
    def test_round_trip_preserves_user_files_hooks_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "AGENTS.md").write_text("# Keep my instructions\nExisting user rule.\n")
            (project / ".claude").mkdir()
            existing = {"permissions": {"allow": ["Read"]}, "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "existing-hook"}]}]}}
            (project / ".claude/settings.json").write_text(json.dumps(existing))
            changes = bootstrap.plan_install(project, mission(), hooks=True)
            self.assertIn("Existing user rule.", changes[project / "AGENTS.md"].decode())
            settings = json.loads(changes[project / ".claude/settings.json"])
            self.assertEqual(settings["permissions"], existing["permissions"])
            self.assertEqual(settings["hooks"]["SessionStart"][0], existing["hooks"]["SessionStart"][0])
            for path, content in changes.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            self.assertEqual(bootstrap.plan_install(project, mission(), hooks=True), {})

    def test_conflicting_install_and_mission_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            target = project / ".agents/skills/full-plan-delivery/SKILL.md"
            target.parent.mkdir(parents=True)
            target.write_text("User-owned differing skill")
            with self.assertRaisesRegex(ValueError, "Existing file differs"):
                bootstrap.plan_install(project, mission())
            self.assertFalse((project / "AGENTS.md").exists())
            target.unlink()
            (project / ".delivery").mkdir()
            old = mission()
            old["objective"] = "Other approved scope"
            (project / ".delivery/mission.json").write_text(json.dumps(old))
            with self.assertRaisesRegex(ValueError, "Existing mission differs"):
                bootstrap.plan_install(project, mission())
            self.assertFalse((project / "AGENTS.md").exists())

    def test_interrupted_atomic_install_can_resume_without_truncated_user_files(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            user_file = project / "AGENTS.md"
            user_file.write_text("Keep the existing instructions\n")
            changes = bootstrap.plan_install(project, mission())
            original_replace = bootstrap.os.replace
            count = 0
            def fail_second(source, destination):
                nonlocal count
                count += 1
                if count == 2:
                    raise OSError("injected unavailable space")
                return original_replace(source, destination)
            with patch.object(bootstrap.os, "replace", side_effect=fail_second):
                with self.assertRaisesRegex(ValueError, "Partial installation: 1"):
                    bootstrap.apply_changes(changes)
            self.assertEqual(user_file.read_text(), "Keep the existing instructions\n")
            remaining = bootstrap.plan_install(project, mission())
            bootstrap.apply_changes(remaining)
            self.assertEqual(bootstrap.plan_install(project, mission()), {})


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        def git(*args):
            return subprocess.run(["git", *args], cwd=self.project, check=True, capture_output=True, text=True)
        git("init", "-q")
        (self.project / ".gitignore").write_text(".delivery/runtime/\n")
        git("add", ".gitignore")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture baseline")
        self.revision = delivery.source_revision(self.project, clean=True)

    def test_reservation_rejects_duplicate_conflicting_and_over_capacity_work(self):
        first = leases.reserve(self.project, [cell("first", self.revision)], "owner", 2)
        with self.assertRaisesRegex(delivery.DeliveryError, "already reserved"):
            leases.reserve(self.project, [cell("first", self.revision)], "owner", 2)
        conflict = cell("other", self.revision)
        conflict["read_paths"] = ["src/first.py"]
        with self.assertRaisesRegex(delivery.DeliveryError, "conflicts"):
            leases.reserve(self.project, [conflict], "other-owner", 2)
        second = leases.reserve(self.project, [cell("second", self.revision)], "owner", 2)
        with self.assertRaisesRegex(delivery.DeliveryError, "WIP"):
            leases.reserve(self.project, [cell("third", self.revision)], "owner", 2)
        with self.assertRaisesRegex(delivery.DeliveryError, "another coordinator"):
            leases.release(self.project, first, "wrong-owner")
        leases.release(self.project, first, "owner")
        leases.release(self.project, second, "owner")
        self.assertEqual(leases.read_leases(self.project), [])

    def test_source_drift_dirty_baseline_and_competing_lock_are_rejected(self):
        stale = cell("old", "git:old")
        with self.assertRaisesRegex(delivery.DeliveryError, "Source advanced"):
            leases.reserve(self.project, [stale], "owner", 2)
        with leases.locked(self.project):
            with self.assertRaisesRegex(delivery.DeliveryError, "Another coordinator"):
                leases.reserve(self.project, [cell("new", self.revision)], "owner", 2)
        (self.project / "uncommitted.txt").write_text("Preserve this")
        with self.assertRaisesRegex(delivery.DeliveryError, "clean, committed"):
            leases.reserve(self.project, [cell("new", self.revision)], "owner", 2)
        self.assertEqual((self.project / "uncommitted.txt").read_text(), "Preserve this")


class PortableCLITests(unittest.TestCase):
    def test_packaging_does_not_follow_an_output_symlink_or_include_private_runtime_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "existing.txt"
            existing.write_text("Preserve my file")
            linked = root / "skill.zip"
            linked.symlink_to(existing)
            with self.assertRaisesRegex(ValueError, "symlink"):
                portable_package.build(linked, replace=True)
            self.assertEqual(existing.read_text(), "Preserve my file")
            (root / "SKILL.md").write_text("Skill")
            (root / ".env").write_text("Fixture private binding")
            (root / "runtime").mkdir()
            (root / "runtime/private.json").write_text("Fixture private state")
            self.assertEqual([file.name for file in portable_package.package_files(root)], ["SKILL.md"])

    def test_install_live_adapter_hooks_handoff_sweep_and_lease_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            outer = Path(directory)
            project = outer / "project with spaces"
            project.mkdir()
            config = mission()
            config["authorization"]["implementation"] = True
            prefix = [sys.executable, ".agents/skills/full-plan-delivery/tests/fixtures/command_tracker.py", str(project)]
            config["tracker"] = {"kind": "command", "commands": {
                "snapshot": [*prefix, "snapshot"], "recall": [*prefix, "recall", "{key}"],
                "remember": [*prefix, "remember", "{key}", "{text}"], "comments": [*prefix, "comments", "{task_id}"],
                "comment": [*prefix, "comment", "{task_id}", "{text}"],
            }}
            config_path = outer / "reviewed-mission.json"
            config_path.write_text(json.dumps(config))
            installed = project / ".agents/skills/full-plan-delivery"
            def run(path, *args, expected=0, cwd=project):
                result = subprocess.run([sys.executable, str(path), *args], cwd=cwd, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                return result
            run(PACKAGE / "scripts/bootstrap.py", "--project", str(project), "--mission-file", str(config_path), "--claude-hooks", "--apply")
            again = run(installed / "scripts/bootstrap.py", "--project", str(project), "--mission-file", str(config_path), "--claude-hooks", "--apply")
            self.assertIn("Applied 0 file changes", again.stdout)
            runtime = project / ".delivery/runtime"
            runtime.mkdir(parents=True)
            data = snapshot()
            data["items"].append({"id": "TASK-2", "parent": "ROOT", "title": "Independent behavior", "issue_type": "task", "status": "open"})
            data["ready_ids"].append("TASK-2")
            state_path = runtime / "test-tracker.json"
            state_path.write_text(json.dumps({"snapshot": data, "comments": {}, "memories": {}}))
            tool = installed / "scripts/delivery.py"
            run(tool, "schema", "--project", str(project))
            run(tool, "remember-mission", "--project", str(project))
            state = json.loads(state_path.read_text())
            mission_reference = json.loads(state["memories"][config["memory_keys"]["mission"]])
            self.assertEqual(mission_reference["mission_file"], ".delivery/mission.json")
            self.assertEqual(mission_reference["mission_sha256"], delivery.hashlib.sha256((project / ".delivery/mission.json").read_bytes()).hexdigest())
            self.assertEqual(mission_reference["requirement_count"], 1)
            self.assertNotIn("requirements", mission_reference)
            state["memories"][config["memory_keys"]["mission"]] = json.dumps({**mission_reference, "linked_task_ids": ["STALE"]})
            state_path.write_text(json.dumps(state))
            stale_session = run(tool, "session", "--project", str(project))
            self.assertIn("RECOVERY WARNING: remembered mission reference differs in linked_task_ids", stale_session.stdout)
            run(tool, "remember-mission", "--project", str(project))
            status = json.loads(run(tool, "status", "--project", str(project), "--json").stdout)
            self.assertEqual(status["ready_ids"], ["TASK", "TASK-2"])
            run(tool, "status", "--task", "ABSENT", expected=2)
            literal = "Fixture proof $(touch SHOULD-NOT-EXIST) `literal`; no real participant result"
            handoff = ["handoff", "--task", "TASK", "--next", "TASK-2", "--candidate", "fixture:candidate", "--completed", "Fixture slice", "--remaining", "Fixture remaining criteria", "--evidence", literal]
            run(tool, *handoff)
            run(tool, *handoff)
            state = json.loads(state_path.read_text())
            self.assertEqual(len(state["comments"]["TASK"]), 1)
            self.assertEqual(json.loads(state["memories"][config["memory_keys"]["handoff"]])["evidence"], literal)
            self.assertFalse((project / "SHOULD-NOT-EXIST").exists())
            env = os.environ.copy()
            env["CLAUDE_PROJECT_DIR"] = str(project)
            settings = json.loads((project / ".claude/settings.json").read_text())
            command = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
            result = subprocess.run(command, shell=True, cwd=outer, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"next": "TASK-2"', result.stdout)
            self.assertIn("RESTORED MISSION REFERENCE", result.stdout)
            self.assertNotIn("PRIVATE-NOTE", result.stdout)
            subprocess.run(["git", "init", "-q"], cwd=project, check=True, capture_output=True)
            subprocess.run(["git", "add", "."], cwd=project, check=True, capture_output=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "portable baseline"], cwd=project, check=True, capture_output=True)
            revision = delivery.source_revision(project, clean=True)
            cells_path = runtime / "cells.json"
            protected = cell("TASK", revision)
            protected.update(write_paths=["AGENTS.md"], outputs=["AGENTS.md"])
            cells_path.write_text(json.dumps([protected]))
            denied = json.loads(run(tool, "sweep", "--cells", ".delivery/runtime/cells.json").stdout)
            self.assertEqual(denied["selected"], [])
            self.assertIn("integrator/shared-wiring", denied["rejected"][0]["reason"])
            cells_path.write_text(json.dumps([cell("TASK", revision), cell("TASK-2", revision)]))
            proposal = json.loads(run(tool, "sweep", "--cells", ".delivery/runtime/cells.json").stdout)
            self.assertEqual(len(proposal["selected"]), 2)
            reserved = json.loads(run(tool, "reserve", "--cells", ".delivery/runtime/cells.json", "--owner", "fixture-owner").stdout)
            lease_id = reserved["lease"]
            run(tool, "release", "--lease", lease_id, "--owner", "wrong-owner", "--workers-stopped", expected=2)
            run(tool, "release", "--lease", lease_id, "--owner", "fixture-owner", expected=2)
            run(tool, "release", "--lease", lease_id, "--owner", "fixture-owner", "--workers-stopped")
            self.assertEqual(json.loads(run(tool, "leases").stdout), [])
            run(tool, "complete", expected=2)


if __name__ == "__main__":
    unittest.main()

