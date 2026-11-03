#!/usr/bin/env python3
"""Install the portable skill and append recovery instructions without overwriting user files."""
import argparse
import copy
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile

from support import DeliveryError
from package import package_files

PACKAGE = Path(__file__).resolve().parents[1]
START = "<!-- full-plan-delivery:begin -->"
END = "<!-- full-plan-delivery:end -->"


def fragment():
    return f"""{START}
## Full-plan delivery continuity

Use `.agents/skills/full-plan-delivery/SKILL.md` for the approved planning/execution process. The entire mission, scope and carried-forward decisions are in `.delivery/mission.json`; the configured live tracker is the only task-status authority.

- At entry, resumption/compaction and task transitions, run `python3 .agents/skills/full-plan-delivery/scripts/delivery.py session --project .` and inspect the actual selected task, dependencies and acceptance criteria.
- Recover every approved roadmap root and criterion. Planning is not implementation; closed status alone is not acceptance evidence. Never substitute an export for the live tracker.
- Continue within existing authorization. Informational questions do not silently cancel the mission; explicit pauses/cancellations do. Setup authorization alone does not authorize implementation or production changes.
- Attribute missing human/service/hardware evidence to its exact criterion. Prepare enabling work and continue independent eligible slices. Never fabricate observations or silently bypass dependencies.
- Use bounded sweeps, declared source/write/contract scopes and coordinator reservations before parallel writes. A scheduling proposal is not a lock or sandbox. Serialize shared wiring and integration.
- After a coherent slice, record criterion progress, candidate identity, checks and limitations in the tracker. After two review/polish passes without material progress, reassess the entire frontier.
- Before handing off, persist evidence and an actual eligible next task with the skill's `handoff` command. If no eligible work remains, record the exact blockers, owners and unblock actions instead of inventing a next task.
- Before a full-program completion claim, run the skill's `complete` command and obtain the required independent acceptance review. Publish only through already-authorized transports; report actual failures truthfully.

These controls preserve scope and detect drift. They do not provide an always-running agent.
{END}
"""


def plan_install(project, config=None, hooks=False):
    """Return exact new/changed bytes, or reject incompatible existing files before any write."""
    project = Path(project).resolve()
    target = project / ".agents/skills/full-plan-delivery"
    changes = {}

    def propose(path, content, overwrite=False):
        path = Path(path)
        if path.is_symlink() or not path.resolve().is_relative_to(project):
            raise ValueError(f"Refusing symlink or escaped destination: {path.name}")
        if path.exists():
            if not path.is_file():
                raise ValueError(f"Destination is not a file: {path.name}")
            if path.read_bytes() == content:
                return
            if not overwrite:
                raise ValueError(f"Existing file differs; preserve and reconcile explicitly: {path.relative_to(project)}")
        changes[path] = content

    if target.resolve() != PACKAGE.resolve():
        for source in package_files(PACKAGE):
            propose(target / source.relative_to(PACKAGE), source.read_bytes())
    if config is None:
        return changes
    # Import lazily so install-only works even before a project has any tracker.
    sys.path.insert(0, str(PACKAGE / "scripts"))
    from delivery import validate_config
    validate_config(config)
    mission_path = project / ".delivery/mission.json"
    if mission_path.exists():
        if json.loads(mission_path.read_text()) != config:
            raise ValueError("Existing mission differs. Reconcile approved scope in place; bootstrap never replaces it.")
    else:
        propose(mission_path, (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode())
    agents = project / "AGENTS.md"
    old = agents.read_text() if agents.exists() else "# Agent instructions\n"
    if START in old or END in old:
        if old.count(START) != 1 or old.count(END) != 1 or old.index(START) > old.index(END):
            raise ValueError("Malformed existing full-plan-delivery block; inspect before repair.")
        existing = old[old.index(START):old.index(END) + len(END)]
        if existing != fragment().strip():
            raise ValueError("Existing delivery instructions differ; reconcile without replacing user instructions.")
    else:
        propose(agents, (old.rstrip() + "\n\n" + fragment()).encode(), overwrite=True)
    ignore = project / ".gitignore"
    old_ignore = ignore.read_text() if ignore.exists() else ""
    if ".delivery/runtime/" not in old_ignore.splitlines():
        propose(ignore, (old_ignore.rstrip() + "\n.delivery/runtime/\n").lstrip("\n").encode(), overwrite=True)
    if hooks:
        settings_path = project / ".claude/settings.json"
        settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
            raise ValueError("Existing Claude settings/hooks must be objects; preserve and inspect them.")
        settings = copy.deepcopy(settings)
        command = 'python3 "$CLAUDE_PROJECT_DIR/.agents/skills/full-plan-delivery/scripts/delivery.py" session --project "$CLAUDE_PROJECT_DIR"'
        for event in ["SessionStart", "PreCompact"]:
            groups = settings.setdefault("hooks", {}).setdefault(event, [])
            if not isinstance(groups, list) or any(not isinstance(g, dict) or not isinstance(g.get("hooks", []), list) for g in groups):
                raise ValueError(f"Existing {event} hooks have an unsupported shape.")
            if not any(h.get("command") == command for g in groups for h in g.get("hooks", []) if isinstance(h, dict)):
                groups.append({"matcher": "", "hooks": [{"type": "command", "command": command, "timeout": 240}]})
        propose(settings_path, (json.dumps(settings, indent=2) + "\n").encode(), overwrite=True)
    return changes


def apply_changes(changes):
    """Replace each preflighted file atomically; an interrupted batch can safely be repeated."""
    completed = []
    for path, content in changes.items():
        temporary = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(mode)
            os.replace(temporary, path)
            completed.append(path)
        except OSError as error:
            raise ValueError(f"Partial installation: {len(completed)} files atomically saved; remaining writes stopped ({type(error).__name__}). Repeat the identical bootstrap to fill missing files; do not delete or overwrite differing user files.") from None
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    return completed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--install-only", action="store_true")
    parser.add_argument("--mission-file", help="Complete reviewed configuration for an existing tracker.")
    parser.add_argument("--objective")
    parser.add_argument("--root", action="append", default=[], help="Existing live root ID, optionally ID=Name; repeat for every root.")
    parser.add_argument("--check", action="append", default=[], help="Existing quality command as a JSON argv array.")
    parser.add_argument("--claude-hooks", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Write the preflighted plan; default is dry-run.")
    args = parser.parse_args(argv)
    project = Path(args.project).resolve()
    if not project.is_dir():
        raise ValueError("Project directory must already exist.")
    config = None
    if not args.install_only:
        if args.mission_file:
            config = json.loads(Path(args.mission_file).read_text())
        else:
            if not args.objective or not args.root:
                raise ValueError("Provide --mission-file or an objective and every existing tracker root.")
            config = json.loads((PACKAGE / "templates/mission.json").read_text())
            config["objective"] = args.objective
            config["roots"] = [{"id": value.split("=", 1)[0], "name": value.split("=", 1)[-1]} for value in args.root]
            config["quality"]["required_commands"] = [json.loads(value) for value in args.check]
    changes = plan_install(project, config, args.claude_hooks)
    for path, content in changes.items():
        print(("WRITE " if args.apply else "WOULD WRITE ") + str(path.relative_to(project)))
    if args.apply:
        apply_changes(changes)
    print(f"{'Applied' if args.apply else 'Preflighted'} {len(changes)} file changes. No tracker initialization, task creation or application execution.")
    if config is not None:
        print("Next: review requirements, authorization and quality commands, then run " +
              shlex.join(["python3", str(project / ".agents/skills/full-plan-delivery/scripts/delivery.py"), "session", "--project", str(project)]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DeliveryError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Bootstrap stopped: {error}", file=sys.stderr)
        raise SystemExit(2)

