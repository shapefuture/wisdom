# full-plan-delivery

A portable skill for complete roadmap recovery, useful task decomposition, evidence-based quality and coordinated parallel execution. It includes actual setup/guard/planner/reservation tools; it is not a daemon or a promise of perfect autonomous software.

## Use in this repository

The skill is under `.agents/skills/full-plan-delivery`. In a new session, invoke:

```text
$full-plan-delivery Set up this project's complete planning and execution process.
Recover every approved roadmap and existing decision, prepare safe parallel
sweeps, and continue implementation within the authorization already given.
```

For setup only, say “Set up the process; do not start product implementation.” Skill discovery may require a new session after installation. Existing project continuity commands remain in place; installing this skill does not replace them or reinitialize its tracker.

## Reuse in another project

Copy the **entire** `full-plan-delivery` directory, including references/templates/scripts/tests, to `<project>/.agents/skills/full-plan-delivery`. Or extract the portable archive and run:

```bash
python3 full-plan-delivery/scripts/bootstrap.py --project /path/to/project --install-only --apply
```

Then invoke `$full-plan-delivery` in that project's Codex session. A skill can also be copied to the user's standard Codex skills directory if desired; discovery and allowed locations depend on the client. For Claude, first establish the canonical `.agents` installation with the same bootstrap, then copy the complete package under `.claude/skills/full-plan-delivery` or link it to the canonical package, and use `/full-plan-delivery`. The generated recovery commands/hooks intentionally target the canonical `.agents` installation. Do not copy only SKILL.md: the tools and references are part of the skill.

Process setup uses a reviewed mission configuration:

```bash
python3 full-plan-delivery/scripts/bootstrap.py --project /path/to/project \
  --mission-file /path/to/reviewed-mission.json --claude-hooks
python3 full-plan-delivery/scripts/bootstrap.py --project /path/to/project \
  --mission-file /path/to/reviewed-mission.json --claude-hooks --apply
```

Bootstrap is dry-run unless `--apply` is supplied. It preflights all intended writes, preserves unrelated AGENTS/settings entries and refuses conflicting installed files/mission/instruction blocks. Each write uses a temporary file and atomic replacement; an interrupted batch reports partial progress and can be resumed with the identical command. The entire multi-file batch is not one atomic transaction. Repeating the same setup changes nothing. It creates no tracker, edits no application source, starts no services, executes no product tests and grants no permission. No automatic upgrading/removal of an existing installation is attempted.

`--objective 'Complete approved outcome' --root PROJECT-ROOT=Roadmap` can create a skeleton when no mission file exists; repeat `--root` for all roots and `--check` with JSON argv arrays for real commands. The skeleton intentionally sets implementation/publication/production authorization to false and leaves criterion mapping empty. The setup agent fills these from actual authorization and the live task graph, configures the real tracker, persists the mission and verifies recovery. A skeleton is not ready evidence.

## Commands

All process commands accept `--project`. The installed path is `.agents/skills/full-plan-delivery/scripts/delivery.py`.

| Command | Behavior |
| --- | --- |
| `schema` | Validate permanent mission structure offline |
| `session` | Restore decisions/handoff and read complete live scope |
| `status --all` / `status --json` | Show the full eligible frontier without copying issue notes |
| `status --task ID` | Reject out-of-scope, blocked, finished or non-executable selection |
| `remember-mission` | Upsert sanitized scope/decisions in the configured tracker |
| `handoff ...` | Persist exact evidence and eligible next work; recover partial writes |
| `sweep --cells PATH` | Propose bounded independent cells from live readiness |
| `reserve --cells PATH --owner ID` | Atomically reserve local source/scopes/resources after live checks |
| `leases` | Inspect outstanding local reservations |
| `release --lease ID --owner ID --workers-stopped` | Release after joining workers, without changing tasks |
| `complete` | Reject unfinished scope, missing evidence/review/coverage and stale root acceptance |

The supported tracker is Beads or an explicitly configured maintained command adapter. Other connectors are not automatically implemented. See [tracker contract](references/tracker-contract.md).

Python 3.10+ and Git are sufficient for the tools; Beads/adapter access is needed for live operations. Local reservations additionally require POSIX `flock` (Linux/macOS/WSL). The planner is pure and platform independent. No package dependencies, embedded credentials or project-specific task IDs are included.

## Verify the package

```bash
python3 -m unittest discover -s .agents/skills/full-plan-delivery/tests -p 'test_*.py' -v
```

The checks exercise scope/criterion loss, blocked active tasks, false acceptance, adapter behavior, bootstrap preservation/repeatability, stale source/contracts, overlap rejection, lease ownership/WIP and handoff recovery. They validate the bundle, not a project's entire product or real-user acceptance. Run the selected project's actual applicable checks as part of delivery.

## Limits that matter in use

The scope declaration must be reconciled with the complete approved program; no script can infer a forgotten requirement absent from both the mission and tracker. Code can require evidence references and a declared independent reviewer; it cannot authenticate empirical observations or stop an agent from lying. Verify the actual artifacts.

Reservations coordinate cooperating agents in one checkout. They do not enforce capabilities, create isolated machines, coordinate disconnected checkouts, claim tasks or spawn workers. Use the platform's subagent/isolation tools and native atomic task claiming as directed by the skill. Existing higher-priority project/platform instructions remain authoritative.

