#!/usr/bin/env python3
"""Portable live-tracker continuity and guarded sweep commands (Python 3.10+)."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from support import DeliveryError, safe_path, source_revision


def argv_valid(value):
    return isinstance(value, list) and bool(value) and all(isinstance(arg, str) and bool(arg) for arg in value)


def validate_config(config):
    if not isinstance(config, dict):
        raise DeliveryError("Mission configuration must be an object.")
    if config.get("schema_version") != 1 or not isinstance(config.get("objective"), str) or not config["objective"].strip() or "REPLACE" in config["objective"]:
        raise DeliveryError("A versioned, concrete complete mission is required.")
    roots = config.get("roots", [])
    if not isinstance(roots, list) or not roots or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip() or row["id"] == "REPLACE" for row in roots):
        raise DeliveryError("Declare every approved live roadmap root.")
    if len({row["id"] for row in roots}) != len(roots):
        raise DeliveryError("Roadmap root IDs must be unique.")
    if not config.get("constraints") or not isinstance(config.get("authorization"), dict):
        raise DeliveryError("Persistent constraints and explicit authorization are required.")
    if any(not isinstance(config["authorization"].get(key), bool) for key in ["implementation", "publication", "production_changes"]):
        raise DeliveryError("Authorization flags must be explicit booleans; never infer production approval.")
    tracker = config.get("tracker", {})
    if not isinstance(tracker, dict) or tracker.get("kind") not in {"beads", "command"}:
        raise DeliveryError("Supported adapters are beads and explicitly configured command adapters.")
    for key in ["binary", "beads_dir", "dolt_root"]:
        if key in tracker and (not isinstance(tracker[key], str) or not tracker[key].strip()):
            raise DeliveryError(f"Configured Beads {key} must be a non-empty string.")
    if tracker["kind"] == "command":
        for name in ["snapshot", "recall", "remember", "comments", "comment"]:
            if not argv_valid(tracker.get("commands", {}).get(name)):
                raise DeliveryError(f"Command adapter needs an explicit {name} argv contract.")
    if not isinstance(config.get("quality"), dict) or not isinstance(config["quality"].get("independent_review_required"), bool):
        raise DeliveryError("Quality settings must explicitly state whether independent review is required.")
    commands = config["quality"].get("required_commands")
    if not isinstance(commands, list) or any(not argv_valid(command) for command in commands):
        raise DeliveryError("Required quality commands must be argv arrays, never shell strings.")
    parallel = config.get("parallel", {})
    if not isinstance(parallel.get("max_workers"), int) or isinstance(parallel["max_workers"], bool) or not 1 <= parallel["max_workers"] <= 32:
        raise DeliveryError("Set a bounded max_workers between 1 and 32.")
    if not isinstance(parallel.get("contract_versions"), dict):
        raise DeliveryError("Declare current shared contract versions.")
    if not isinstance(parallel.get("integrator_paths"), list) or not parallel["integrator_paths"] or any(not isinstance(path, str) or not path for path in parallel["integrator_paths"]):
        raise DeliveryError("Declare administrative/shared paths owned by the integrator.")
    keys = config.get("memory_keys", {})
    if not keys.get("mission") or not keys.get("handoff") or keys["mission"] == keys["handoff"]:
        raise DeliveryError("Separate mission and handoff memory keys are required.")
    requirements = config.get("requirements", [])
    if not isinstance(requirements, list) or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip()
            or not isinstance(row.get("task_ids"), list) or not row["task_ids"] or any(not isinstance(item_id, str) or not item_id.strip() for item_id in row["task_ids"])
            or not isinstance(row.get("acceptance"), str) or not row["acceptance"].strip() for row in requirements):
        raise DeliveryError("Each approved requirement needs an ID, task IDs and concrete acceptance.")
    if len({row["id"] for row in requirements}) != len(requirements):
        raise DeliveryError("Requirement IDs must be unique.")
    if not isinstance(config.get("linked_task_ids", []), list) or any(not isinstance(item_id, str) or not item_id.strip() for item_id in config.get("linked_task_ids", [])):
        raise DeliveryError("Linked integration IDs must be a list of actual task IDs.")
    maps = config.get("plan_maps", [])
    if not isinstance(maps, list) or any(not isinstance(row, dict) or not isinstance(row.get("path"), str) or not row["path"] or not isinstance(row.get("key"), str) or not row["key"] for row in maps):
        raise DeliveryError("Plan maps require a JSON path and selected top-level key.")


def load_config(project):
    config = json.loads(safe_path(project, ".delivery/mission.json").read_text())
    validate_config(config)
    return config


def mission_memory(config, project):
    """Keep Beads continuity small while binding it to the complete local mission file."""
    mission_path = safe_path(project, ".delivery/mission.json")
    coverage = config.get("coverage_notes", {})
    value = {
        "objective": config["objective"],
        "mission_file": ".delivery/mission.json",
        "mission_sha256": hashlib.sha256(mission_path.read_bytes()).hexdigest(),
        "root_ids": [row["id"] for row in config["roots"]],
        "linked_task_ids": config.get("linked_task_ids", []),
        "authorization": config["authorization"],
        "constraints": config["constraints"],
        "requirement_count": len(config.get("requirements", [])),
        "scope_record_count": coverage.get("scope_record_count"),
        "unresolved_acceptance_criteria": coverage.get("scope_records_without_acceptance_criteria", []),
        "contract_versions": config.get("parallel", {}).get("contract_versions", {}),
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def mission_memory_mismatches(restored, config, project):
    """Return pointer fields that no longer describe the canonical mission."""
    if not isinstance(restored, dict):
        return ["<not-an-object>"]
    expected = json.loads(mission_memory(config, project))
    return [key for key, value in expected.items() if restored.get(key) != value]


class Tracker:
    """Only the configured live source supplies status; no export fallback."""
    def __init__(self, project, config):
        self.project, self.config = Path(project), config
        self.settings = config["tracker"]

    def run(self, name, substitutions=None, json_result=True, write=False):
        values = substitutions or {}
        env = os.environ.copy()
        if self.settings["kind"] == "beads":
            binary = os.environ.get("BEADS_BIN") or self.settings.get("binary", "bd")
            candidate = str(self.project / binary) if "/" in binary and not Path(binary).is_absolute() else binary
            executable = shutil.which(candidate)
            if not executable:
                raise DeliveryError("Beads CLI unavailable. Repair configured setup; do not initialize/import or read an export.")
            configured_beads_dir = self.settings.get("beads_dir")
            if configured_beads_dir:
                beads_path = Path(configured_beads_dir)
                if beads_path.is_absolute():
                    try:
                        beads_dir = beads_path.resolve(strict=True)
                    except OSError:
                        raise DeliveryError("Configured live Beads workspace directory is unavailable; refusing tracker auto-discovery.") from None
                else:
                    beads_dir = safe_path(self.project, configured_beads_dir)
                if not beads_dir.is_dir():
                    raise DeliveryError("Configured live Beads workspace path is not a directory; refusing tracker auto-discovery.")
                env["BEADS_DIR"] = str(beads_dir)
            configured_dolt_root = self.settings.get("dolt_root", ".delivery/runtime/dolt")
            configured_dolt_path = Path(configured_dolt_root)
            if configured_dolt_path.is_absolute():
                # An explicit absolute root binds the mission to its existing live
                # tracker. Never create a database at this path or silently fall
                # back to Beads' project-local auto-discovery.
                try:
                    dolt_root = configured_dolt_path.resolve(strict=True)
                except OSError:
                    raise DeliveryError("Configured live Beads Dolt root is unavailable; refusing to initialize or use another database.") from None
                if not dolt_root.is_dir():
                    raise DeliveryError("Configured live Beads Dolt root is not a directory; refusing to initialize or use another database.")
                env["DOLT_ROOT_PATH"] = str(dolt_root)
            else:
                selected_dolt_root = env.get("DOLT_ROOT_PATH", configured_dolt_root)
                selected_dolt_path = Path(selected_dolt_root)
                if not selected_dolt_path.is_absolute():
                    selected_dolt_path = safe_path(self.project, selected_dolt_root)
                try:
                    dolt_root = selected_dolt_path.resolve(strict=True)
                except OSError:
                    raise DeliveryError("Configured live Beads Dolt root is unavailable; refusing to initialize or use another database.") from None
                if not dolt_root.is_dir():
                    raise DeliveryError("Configured live Beads Dolt root is not a directory; refusing to initialize or use another database.")
                env["DOLT_ROOT_PATH"] = str(dolt_root)
            operations = {
                "list": ["list", "--all", "--limit", "0"], "ready": ["ready", "--limit", "0"],
                "recall": ["recall", values.get("key", "")],
                "remember": ["remember", values.get("text", ""), "--key", values.get("key", "")],
                "comments": ["comments", values.get("task_id", "")],
                "comment": ["comments", "add", values.get("task_id", ""), values.get("text", "")],
            }
            command = [executable, "--sandbox"] + ([] if write else ["--readonly"]) + (["--json"] if json_result else []) + operations[name]
        else:
            # Replace exact placeholders only; JSON argv + shell=False prevents text becoming shell code.
            command = []
            for argument in self.settings["commands"][name]:
                placeholder = re.fullmatch(r"\{([a-z_]+)\}", argument)
                if placeholder:
                    key = placeholder[1]
                    if key not in values:
                        raise DeliveryError(f"Unresolved command-adapter placeholder in {name}.")
                    command.append(values[key])
                else:
                    command.append(argument)
        result = subprocess.run(command, cwd=self.project, env=env, capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise DeliveryError(f"Live tracker operation {name} failed with exit {result.returncode}; diagnose access/tool configuration. Raw notes and credentials are not printed.")
        return json.loads(result.stdout) if json_result else result.stdout

    def snapshot(self):
        if self.settings["kind"] == "command":
            value = self.run("snapshot")
        else:
            items = self.run("list")
            ready = self.run("ready")
            value = {"items": items, "ready_ids": [row["id"] for row in ready]}
        if not isinstance(value, dict) or not isinstance(value.get("items"), list) or not isinstance(value.get("ready_ids"), list):
            raise DeliveryError("Snapshot adapter must return items and ready_ids arrays from the live tracker.")
        return value


def blocking_dependencies(row):
    nonblocking = {"parent-child", "related", "relates-to", "relates_to", "discovered-from", "discovered_from", "duplicates", "supersedes"}
    return [edge.get("depends_on_id", edge.get("id")) for edge in row.get("dependencies", [])
            if edge.get("type", "blocks") not in nonblocking]


def inspect_scope(project, config, snapshot):
    items = snapshot["items"]
    by_id = {row["id"]: row for row in items}
    if len(by_id) != len(items):
        raise DeliveryError("Live snapshot contains duplicate IDs.")
    roots = {row["id"] for row in config["roots"]}
    mandatory = roots | set(config.get("linked_task_ids", []))
    if mandatory - by_id.keys():
        raise DeliveryError("Missing declared live scope IDs: " + ", ".join(sorted(mandatory - by_id.keys())))

    def root_of(item_id):
        seen = set()
        while item_id in by_id:
            if item_id in roots:
                return item_id
            if item_id in seen:
                raise DeliveryError("Live tracker hierarchy cycle.")
            seen.add(item_id)
            row = by_id[item_id]
            parents = {edge.get("depends_on_id", edge.get("id")) for edge in row.get("dependencies", []) if edge.get("type") == "parent-child"}
            if row.get("parent"):
                parents.add(row["parent"])
            if len(parents) > 1:
                raise DeliveryError("Conflicting live parent authorities.")
            item_id = next(iter(parents), None)
        return None

    ownership = {item_id: root_of(item_id) for item_id in by_id}
    allowed = {item_id for item_id, root in ownership.items() if root} | set(config.get("linked_task_ids", []))
    ready = set(snapshot["ready_ids"])
    if ready - by_id.keys():
        raise DeliveryError("Ready frontier and live snapshot disagree; reread the tracker.")
    for item_id in ready:
        row = by_id[item_id]
        if row["status"] not in {"open", "in_progress"} or row.get("blocked") is True:
            raise DeliveryError("Ready frontier includes a closed or blocked task; repair the adapter or reread.")
        if any(dep not in by_id or by_id[dep]["status"] != "closed" for dep in blocking_dependencies(row)):
            raise DeliveryError("Ready frontier disagrees with live blocking dependencies.")
    for root in config["roots"]:
        if root.get("spec") and not safe_path(project, root["spec"]).is_file():
            raise DeliveryError("Declared roadmap specification is missing.")
    planned = set()
    for plan in config.get("plan_maps", []):
        mapped = json.loads(safe_path(project, plan["path"]).read_text())[plan["key"]]
        ids = mapped.values() if isinstance(mapped, dict) else mapped
        if not isinstance(mapped, (dict, list)) or any(not isinstance(item_id, str) or not item_id.strip() for item_id in ids):
            raise DeliveryError("A plan map must contain actual task ID strings.")
        planned.update(ids)
    for requirement in config.get("requirements", []):
        planned.update(requirement["task_ids"])
    if planned - allowed:
        raise DeliveryError("Approved plan/requirement IDs are missing or detached from declared scope: " + ", ".join(sorted(planned - allowed)))
    executable = {item_id for item_id in allowed if by_id[item_id].get("issue_type", "task") in {"task", "feature", "spike", "bug"}}
    ready &= executable
    active = {item_id for item_id in executable if by_id[item_id]["status"] == "in_progress" and not by_id[item_id].get("blocked")
              and all(dep in by_id and by_id[dep]["status"] == "closed" for dep in blocking_dependencies(by_id[item_id]))}
    return {"by_id": by_id, "ownership": ownership, "allowed": allowed, "ready": ready, "active": active}


def validate_selection(report, task_id):
    if task_id not in report["ready"] | report["active"]:
        raise DeliveryError(f"{task_id} is outside scope, blocked, non-executable or finished. Active status alone is insufficient.")


def render(config, report, all_items=False):
    lines = ["FULL DELIVERY MISSION", config["objective"], "LIVE TRACKER COVERAGE (task counts are not feature percentages)"]
    for root in config["roots"]:
        rows = [row for item_id, row in report["by_id"].items() if report["ownership"][item_id] == root["id"]]
        lines.append(f"{root['id']} {root.get('name', '')}: {dict(Counter(row['status'] for row in rows))}")
    frontier = sorted(report["ready"] | report["active"], key=lambda item_id: (report["by_id"][item_id].get("priority", 4), item_id))
    lines.append(f"Eligible scope slices: {len(frontier)}; showing {'all' if all_items else 'up to 12'} (use status --all or --json for the complete frontier).")
    for item_id in frontier if all_items else frontier[:12]:
        row = report["by_id"][item_id]
        lines.append(f"{item_id} {row['status']} {row.get('title', '')}")
    lines.append(f"Mapped approved requirements: {len(config.get('requirements', []))}.")
    if not config.get("requirements"):
        lines.append("SETUP GAP: complete criterion coverage has not been configured; completion will fail.")
    if not config["quality"]["required_commands"]:
        lines.append("SETUP GAP: required quality commands have not been configured; completion will fail.")
    lines.append("Inspect actual acceptance and predecessors. Evidence blockers hold their exact scope; a report is not a lease, approval or acceptance decision.")
    return "\n".join(lines)


def require_complete(config, report, current_candidate=None):
    if any(report["by_id"][item_id]["status"] != "closed" for item_id in report["allowed"]):
        raise DeliveryError("Whole-program completion rejected: unfinished scope records remain.")
    missing_acceptance = sorted(item_id for item_id in report["allowed"]
                                if not isinstance(report["by_id"][item_id].get("acceptance_criteria"), str)
                                or not report["by_id"][item_id]["acceptance_criteria"].strip())
    if missing_acceptance:
        sample = ", ".join(missing_acceptance[:10])
        suffix = " …" if len(missing_acceptance) > 10 else ""
        raise DeliveryError("Whole-program completion rejected: live acceptance criteria are missing for " + sample + suffix + ".")
    if not config.get("requirements") or not config["quality"]["required_commands"]:
        raise DeliveryError("Whole-program completion rejected: requirement coverage or quality gates are unconfigured.")
    for item_id in report["allowed"]:
        row = report["by_id"][item_id]
        proof = row.get("metadata", {}).get("delivery", {}).get("acceptance", {})
        evidence = proof.get("evidence")
        if (proof.get("decision") != "accepted" or not isinstance(proof.get("candidate"), str)
                or not proof["candidate"].strip() or not isinstance(evidence, list) or not evidence
                or any(not isinstance(entry, dict) or not entry.get("ref") or entry.get("outcome") not in {"passed", "observed", "accepted"} for entry in evidence)):
            raise DeliveryError(f"{item_id}: closed status lacks a recorded acceptance decision, candidate and evidence references.")
        if item_id in {root["id"] for root in config["roots"]} and current_candidate is not None and proof["candidate"] != current_candidate:
            raise DeliveryError(f"{item_id}: root acceptance is stale for the current integrated candidate.")
        if config["quality"].get("independent_review_required", True):
            review = proof.get("independent_review", {})
            if (not isinstance(review, dict) or not review.get("ref") or not review.get("reviewer") or not review.get("builder")
                    or review["reviewer"] == review["builder"] or review.get("decision") != "accepted" or review.get("candidate") != proof["candidate"]):
                raise DeliveryError(f"{item_id}: required independent review is missing, stale or attributed to the builder.")
    for requirement in config["requirements"]:
        if not any(requirement["id"] in report["by_id"][item_id].get("metadata", {}).get("delivery", {}).get("acceptance", {}).get("requirements", [])
                   for item_id in requirement["task_ids"]):
            raise DeliveryError(f"{requirement['id']}: no mapped task acceptance records verified requirement coverage.")
    # Structural checks cannot establish that an external observation actually occurred.
    return "Completion prerequisites present in the live tracker. Required independent acceptance must validate evidence and the current integrated candidate; this command cannot authenticate empirical claims."


def persist_handoff(tracker, config, report, args):
    if args.task not in report["allowed"]:
        raise DeliveryError("Handoff source is outside the approved mission.")
    frontier = report["ready"] | report["active"]
    if args.next:
        validate_selection(report, args.next)
    elif frontier:
        raise DeliveryError("Eligible work exists; name the actual next task instead of declaring the program blocked.")
    elif not args.blocker:
        raise DeliveryError("With no eligible next work, record exact blockers, owners and unblock actions (or confirmed completion).")
    for value in [args.completed, args.remaining, args.evidence, args.candidate]:
        if not value.strip():
            raise DeliveryError("Handoff requires nonempty progress, remaining criteria, candidate identity and actual evidence.")
    value = {
        "task": args.task, "next": args.next, "completed": args.completed, "remaining": args.remaining,
        "evidence": args.evidence, "candidate": args.candidate, "blocker": args.blocker,
        "root_ids": [row["id"] for row in config["roots"]],
    }
    handoff_id = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]
    value["handoff_id"] = handoff_id
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    key = config["memory_keys"]["handoff"]
    # Upsert continuity first. On comment failure recovery still has the next task; retries deduplicate the comment.
    tracker.run("remember", {"key": key, "text": encoded}, json_result=False, write=True)
    try:
        comments = tracker.run("comments", {"task_id": args.task})
        if isinstance(comments, dict):
            comments = comments.get("comments", [])
        marker = "DELIVERY-HANDOFF " + handoff_id
        if not any(marker in row.get("text", row.get("body", "")) for row in comments):
            tracker.run("comment", {"task_id": args.task, "text": marker + "\n" + encoded}, json_result=False, write=True)
    except (DeliveryError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as error:
        raise DeliveryError(f"PARTIAL HANDOFF: memory {key} is saved; task comment is unconfirmed. Repeat the identical handoff to recover safely. {type(error).__name__}") from None
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["schema", "session", "status", "remember-mission", "handoff", "complete", "sweep", "reserve", "release", "leases"])
    parser.add_argument("--project", default=".")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--task")
    parser.add_argument("--next")
    for name in ["completed", "remaining", "evidence", "candidate", "blocker"]:
        parser.add_argument("--" + name, default="")
    parser.add_argument("--cells")
    parser.add_argument("--owner", help="Coordinator/worker identity for local lease ownership.")
    parser.add_argument("--lease")
    parser.add_argument("--workers-stopped", action="store_true", help="Release only after the coordinator has stopped/joined every worker.")
    args = parser.parse_args(argv)
    project = Path(args.project).resolve()
    config = load_config(project)
    if args.command == "schema":
        print("Mission schema valid. Live scope, configured checks and acceptance are not established by schema validation.")
        return 0
    tracker = Tracker(project, config)
    if args.command == "remember-mission":
        tracker.run("remember", {"key": config["memory_keys"]["mission"], "text": mission_memory(config, project)}, json_result=False, write=True)
        print("Mission reference, scope identity and carried-forward decisions saved in the selected tracker; the complete criteria remain in the hash-bound mission file. No task state changed.")
        return 0
    if args.command == "session":
        print("PERMANENT MISSION: " + config["objective"])
        print("Persistent constraints: " + json.dumps(config["constraints"], ensure_ascii=False))
        print("Authorization: " + json.dumps(config["authorization"]))
        for name, key in config["memory_keys"].items():
            try:
                raw = tracker.run("recall", {"key": key}, json_result=False)
                # Beads may prefix recall with its key heading; never print arbitrary raw memory.
                start = raw.find("{")
                restored, _ = json.JSONDecoder().raw_decode(raw[start:]) if start >= 0 else ({}, 0)
                if name == "handoff":
                    print("RESTORED HANDOFF: " + json.dumps({field: restored.get(field) for field in ["handoff_id", "task", "next", "completed", "remaining", "candidate", "evidence", "blocker", "root_ids"]}, ensure_ascii=False))
                    if set(restored.get("root_ids", [])) != {row["id"] for row in config["roots"]}:
                        print("RECOVERY WARNING: handoff scope differs from permanent mission; recompute and reconcile.")
                else:
                    mismatches = mission_memory_mismatches(restored, config, project)
                    if mismatches:
                        print("RECOVERY WARNING: remembered mission reference differs in " + ", ".join(mismatches) + "; reconcile approved scope before continuing.")
                    else:
                        print("RESTORED MISSION REFERENCE: " + json.dumps({field: restored.get(field) for field in ["mission_file", "mission_sha256", "root_ids", "requirement_count", "scope_record_count", "unresolved_acceptance_criteria", "contract_versions"]}, ensure_ascii=False))
            except (DeliveryError, ValueError, TypeError, subprocess.TimeoutExpired):
                print(f"Recovery memory {key} unavailable; permanent mission is retained. Repair memory persistence.")
    if args.command in {"leases", "release"}:
        import leases
        if args.command == "leases":
            print(json.dumps(leases.read_leases(project), indent=2))
        else:
            if not args.lease or not args.owner or not args.workers_stopped:
                raise DeliveryError("Release requires the actual lease, owning coordinator and --workers-stopped confirmation.")
            leases.release(project, args.lease, args.owner)
            print("Lease released; task status is unchanged. Stop/join its workers before release.")
        return 0
    report = inspect_scope(project, config, tracker.snapshot())
    if args.command == "handoff":
        if not args.task:
            raise DeliveryError("Handoff requires --task.")
        print(json.dumps(persist_handoff(tracker, config, report, args), ensure_ascii=False, indent=2))
    elif args.command == "complete":
        print(require_complete(config, report, source_revision(project, clean=True)))
    elif args.command in {"sweep", "reserve"}:
        from parallel import select_cells, scopes_overlap, validate_cell
        if not config["authorization"]["implementation"]:
            raise DeliveryError("Implementation authorization is absent; setup and planning alone do not grant it.")
        if not args.cells:
            raise DeliveryError("Provide candidate workcells with --cells (not a static ready queue).")
        candidates = json.loads(safe_path(project, args.cells).read_text())
        revision = source_revision(project, clean=True)
        if not isinstance(candidates, list):
            raise DeliveryError("Candidate workcells must be an array.")
        for cell in candidates:
            if validate_cell(cell, revision, config["parallel"]["contract_versions"]) is None:
                for name in [*cell["read_paths"], *cell["write_paths"]]:
                    safe_path(project, name)
                if any(scopes_overlap(write, owned) for write in cell["write_paths"] for owned in config["parallel"]["integrator_paths"]):
                    cell["shared_wiring"] = True
        selection = select_cells(candidates, report["ready"], revision, config["parallel"]["contract_versions"], config["parallel"]["max_workers"])
        if args.command == "reserve":
            import leases
            if not args.owner or not selection["selected"]:
                raise DeliveryError("Reservation requires an owner and at least one live-ready conflict-free cell.")
            selection["lease"] = leases.reserve(project, selection["selected"], args.owner, config["parallel"]["max_workers"])
            selection["dispatch_precondition"] = "No worker may start until each native atomic tracker claim and live revision/precondition recheck succeeds. This local reservation is not a tracker claim, permission grant or sandbox."
        print(json.dumps(selection, indent=2))
    else:
        if args.task:
            validate_selection(report, args.task)
        if args.json:
            print(json.dumps({"roots": config["roots"], "scope_ids": sorted(report["allowed"]), "ready_ids": sorted(report["ready"]), "eligible_active_ids": sorted(report["active"])}, indent=2))
        else:
            print(render(config, report, args.all))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DeliveryError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(f"Delivery guard stopped: {error}", file=sys.stderr)
        raise SystemExit(2)

