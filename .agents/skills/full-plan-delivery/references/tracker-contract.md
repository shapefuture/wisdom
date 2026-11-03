# Live tracker adapter contract

The bundle supports Beads directly and explicit command adapters. It does not implement automatic GitHub/Linear/Jira API setup. Reuse available connectors or maintained project tools; the setup agent must configure and exercise a real adapter before calling that workflow ready.

## Beads

Configure `tracker.kind=beads`, the actual `binary`, and the existing live tracker paths. `BEADS_BIN` may override the configured binary. When `beads_dir` is set, that directory is authoritative and missing paths fail closed; when omitted, Beads uses its normal workspace discovery. An absolute `dolt_root` is authoritative, must already exist as a directory, and overrides ambient `DOLT_ROOT_PATH`; a missing path fails closed without creating another database. A relative `dolt_root` is used only when `DOLT_ROOT_PATH` is unset. Both the configured relative root and an ambient `DOLT_ROOT_PATH` must already exist as directories; missing roots fail closed and are never created by the skill. The skill uses supported list/ready/recall/remember/comments commands, with sandbox mode to suppress implicit push and read-only mode for reads. Verify CLI syntax through its own help when versions differ. No `init`, import, JSONL fallback, dependency rewrite, task close or push is performed by the bundled commands.

Mission/handoff use separate named memories and task comments. Explicitly recall them at startup; a custom prime hook may supply only a pointer. A stale memory never supersedes live task state or the approved permanent mission.

## Explicit command adapter

Configure argv arrays, invoked with `shell=False` in the project directory. Each placeholder is a whole argument; secrets stay in supported environment bindings, never config/argv. Required commands:

```json
{
  "kind": "command",
  "commands": {
    "snapshot": ["python3", "tools/tracker_adapter.py", "snapshot"],
    "recall": ["python3", "tools/tracker_adapter.py", "recall", "{key}"],
    "remember": ["python3", "tools/tracker_adapter.py", "remember", "{key}", "{text}"],
    "comments": ["python3", "tools/tracker_adapter.py", "comments", "{task_id}"],
    "comment": ["python3", "tools/tracker_adapter.py", "comment", "{task_id}", "{text}"]
  }
}
```

`snapshot` performs fresh authoritative reads, resolves tracker pagination, normalizes statuses to `open`, `in_progress`, `blocked`, `deferred` or `closed`, and returns:

```json
{
  "revision": "optional-source-revision",
  "items": [
    {"id": "PROJECT-ROOT", "title": "Complete roadmap", "issue_type": "epic", "status": "open"},
    {"id": "PROJECT-1", "title": "Concrete behavior", "issue_type": "task", "status": "open",
     "parent": "PROJECT-ROOT", "priority": 1, "blocked": false,
     "dependencies": [{"depends_on_id": "PROJECT-PREREQ", "type": "blocks"}],
     "metadata": {"delivery": {}}}
  ],
  "ready_ids": []
}
```

Return all items needed for the complete hierarchy and dependency resolution, not a truncated query. Normalize completed/cancelled states deliberately; cancelled is not silently accepted. Readiness must account for real dependencies, explicit blockers and authorization-specific scheduling. Unknown dependency types are conservatively blocking, except documented relationship/hierarchy types. Active tasks are executable only when their blocking predecessors are closed and they are not explicitly blocked.

`recall` returns the stored JSON text (Beads may prefix a heading). `remember` upserts a named memory. `comments` returns an array of objects with `text` or `body` (or an object containing that array). `comment` appends exactly the supplied text. All operations preserve exit codes and return nonzero on failure; no fallback success from an unavailable service. The bundle does not print raw tracker errors or arbitrary memories.

The handoff marker is a deterministic digest. Memory is written first so a failed comment does not erase continuation; identical retries skip existing comments. This is recoverable two-step persistence, not an atomic remote transaction. If a command has an uncertain external result, inspect the actual stored marker before claiming success.

Atomic claim, dependency edits, closure, tracker sync and release-specific permissions remain tracker-native operations. Inspect supported commands and expected-revision semantics; do not guess that every tracker implements Beads grammar. A local coordinator reservation never replaces the authoritative claim.

## Scope maps

Optional `plan_maps` entries contain a repository-relative JSON `path` and top-level `key`. The selected value is either an array of task IDs or an object whose values are IDs. Every ID must still exist within declared live roots/linked IDs. Requirement mappings provide criterion coverage even when there is no generated plan file. Add a new approved root to the mission deliberately; dynamic descendants are included automatically and reviewed for unintended scope expansion.

