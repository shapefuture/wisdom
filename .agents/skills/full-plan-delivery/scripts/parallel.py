"""Conservative, pure planner for selecting independent ready work cells.

This module only plans a batch. It does not acquire locks, create isolated
worktrees, launch workers, or change any tracker state. Path conflict matching
uses literal prefixes before glob metacharacters, so it may report conflicts
between scopes that are actually disjoint. This conservative approximation
does not replace filesystem isolation or enforcement.
"""

from __future__ import annotations

import fnmatch
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


_GLOB_CHARS = "*?["
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_WORKER_SWEEP_ROLES = {"integrator", "shared-wiring", "shared_wiring"}


def _path_pattern(value: Any) -> bool:
    """Return whether value is a safe repository-relative path or glob."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    if value.startswith("/") or _DRIVE_PREFIX.match(value):
        return False
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    return True


def _concrete_path(value: Any) -> bool:
    return _path_pattern(value) and not any(char in value for char in _GLOB_CHARS)


def _nonempty_strings(value: Any, *, paths: bool = False) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_path_pattern(item) if paths else isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _quality_commands(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(argv, list)
            and bool(argv)
            and all(isinstance(arg, str) and bool(arg) for arg in argv)
            for argv in value
        )
    )


def _scope_prefix(pattern: str) -> str:
    """Get the conservative literal prefix of a repository-relative glob."""
    wildcard_at = min((pattern.find(char) for char in _GLOB_CHARS if char in pattern), default=-1)
    return pattern if wildcard_at < 0 else pattern[:wildcard_at]


def _scope_overlap(left: str, right: str) -> bool:
    """Conservative overlap test: literal prefixes that nest may overlap."""
    a = _scope_prefix(left)
    b = _scope_prefix(right)
    # Prefixes can end halfway through a path component when a glob is used;
    # startswith is intentionally conservative and can create false positives.
    return a.startswith(b) or b.startswith(a)


def _output_is_writable(output: str, write_scope: str) -> bool:
    # fnmatchcase handles ordinary repository globs. For literal scopes it is
    # an exact match; for directory-like glob scopes (e.g. src/**), it covers
    # nested output paths according to the platform-independent glob syntax.
    return fnmatch.fnmatchcase(output, write_scope)


def _mapping_of_versions(value: Any) -> bool:
    return isinstance(value, Mapping) and all(
        isinstance(key, str) and bool(key.strip()) and isinstance(version, str) and bool(version.strip())
        for key, version in value.items()
    )


def _valid_rank(cell: Mapping[str, Any], key: str) -> bool:
    value = cell.get(key, 4 if key == "priority" else 0)
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_cell(cell: Any, base_revision: Any, contract_versions: Any) -> str | None:
    """Return a validation error for one cell, or None when it is eligible.

    The caller must separately establish live readiness and task-ID
    uniqueness. This function has no tracker or repository side effects.
    """
    if not isinstance(cell, Mapping):
        return "cell must be an object"
    task_id = cell.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return "task_id must be a non-empty string"
    if not isinstance(cell.get("base_revision"), str) or cell["base_revision"] != base_revision:
        return "base_revision does not match current source identity"
    if not _nonempty_strings(cell.get("read_paths"), paths=True):
        return "read_paths must contain safe repository-relative paths or globs"
    if not _nonempty_strings(cell.get("write_paths"), paths=True):
        return "write_paths must contain safe repository-relative paths or globs"
    contract_reads = cell.get("contract_reads")
    if not isinstance(contract_reads, Mapping) or any(
        not isinstance(key, str) or not key.strip() or not isinstance(version, str) or not version.strip()
        for key, version in contract_reads.items()
    ):
        return "contract_reads must map contract IDs to non-empty versions"
    if not isinstance(cell.get("contract_writes"), list) or any(
        not isinstance(item, str) or not item.strip() for item in cell["contract_writes"]
    ):
        return "contract_writes must be a list of non-empty contract IDs"
    resources = cell.get("shared_resources")
    if not isinstance(resources, list) or any(not isinstance(item, str) or not item.strip() for item in resources):
        return "shared_resources must be a list of non-empty identifiers"
    if not _nonempty_strings(cell.get("acceptance")):
        return "acceptance must contain non-empty criteria"
    if not _quality_commands(cell.get("quality_commands")):
        return "quality_commands must contain non-empty argv arrays"
    outputs = cell.get("outputs")
    if not isinstance(outputs, list) or not outputs or any(not _concrete_path(path) for path in outputs):
        return "outputs must contain safe concrete repository-relative paths"
    if not all(any(_output_is_writable(output, scope) for scope in cell["write_paths"]) for output in outputs):
        return "every output must be covered by the cell's write_paths"
    if cell.get("role", "worker") not in {"worker", "integrator", "shared-wiring", "shared_wiring"}:
        return "role must be worker or integrator"
    if not _valid_rank(cell, "critical_path_rank") or not _valid_rank(cell, "priority"):
        return "critical_path_rank and priority must be finite numbers"
    if not _mapping_of_versions(contract_versions):
        return "contract_versions must map contract IDs to non-empty versions"
    for contract_id, version in contract_reads.items():
        if contract_versions.get(contract_id) != version:
            return f"stale or unknown contract version: {contract_id}"
    return None


def conflict_reason(cell: Mapping[str, Any], other: Mapping[str, Any]) -> str | None:
    """Return why two already-validated cells cannot share a worker sweep."""
    selected = other
    selected_id = selected["task_id"]
    for path in cell["write_paths"]:
        if any(_scope_overlap(path, other) for other in selected["write_paths"]):
            return f"write scope overlaps task {selected_id}"
    for path in cell["write_paths"]:
        if any(_scope_overlap(path, other) for other in selected["read_paths"]):
            return f"write scope overlaps read scope of task {selected_id}"
    for path in cell["read_paths"]:
        if any(_scope_overlap(path, other) for other in selected["write_paths"]):
            return f"read scope overlaps write scope of task {selected_id}"
    cell_reads = cell["contract_reads"]
    selected_reads = selected["contract_reads"]
    cell_writes = set(cell["contract_writes"])
    selected_writes = set(selected["contract_writes"])
    overlap = cell_writes & selected_writes
    if overlap:
        return f"contract write overlaps task {selected_id}: {sorted(overlap)[0]}"
    overlap = cell_writes & set(selected_reads)
    if overlap:
        return f"contract write overlaps read of task {selected_id}: {sorted(overlap)[0]}"
    overlap = set(cell_reads) & selected_writes
    if overlap:
        return f"contract read overlaps write of task {selected_id}: {sorted(overlap)[0]}"
    resources = set(cell["shared_resources"]) & set(selected["shared_resources"])
    if resources:
        return f"shared resource overlaps task {selected_id}: {sorted(resources)[0]}"
    return None


def _rank(cell: Mapping[str, Any]) -> tuple[float, float, str]:
    # Higher critical-path rank and lower Beads priority number are more
    # urgent; task ID breaks ties. Unspecified priority follows Beads P4.
    return (-float(cell.get("critical_path_rank", 0)), float(cell.get("priority", 4)), cell["task_id"])


def select_cells(
    cells: Sequence[Any],
    ready_ids: Iterable[str],
    base_revision: str,
    contract_versions: Mapping[str, str],
    max_workers: int = 3,
) -> dict[str, list[Any]]:
    """Greedily select a deterministic set of independent live-ready cells.

    Only IDs in the caller-supplied live ``ready_ids`` are considered; any
    static ``ready`` property carried by a cell is ignored. The greedy order
    is descending ``critical_path_rank``, ascending Beads ``priority`` (lower
    numbers are more urgent; missing priority defaults to 4), then task ID.
    It is deterministic but does not promise an optimal maximum set.

    Rejections are objects with ``task_id`` and ``reason`` fields. Selected
    entries are the original cell objects, unchanged.
    """
    if not isinstance(cells, Sequence) or isinstance(cells, (str, bytes)):
        raise TypeError("cells must be a sequence")
    if not isinstance(max_workers, int) or isinstance(max_workers, bool) or max_workers < 1:
        raise ValueError("max_workers must be a positive integer")
    if not isinstance(base_revision, str) or not base_revision:
        raise ValueError("base_revision must be a non-empty source identity")
    if not isinstance(contract_versions, Mapping):
        raise TypeError("contract_versions must be a mapping")
    try:
        ready = set(ready_ids)
    except TypeError as error:
        raise TypeError("ready_ids must be iterable") from error
    if any(not isinstance(task_id, str) for task_id in ready):
        raise TypeError("ready_ids must contain strings")

    rejected: list[dict[str, str]] = []
    id_counts: dict[str, int] = {}
    for candidate in cells:
        candidate_id = candidate.get("task_id") if isinstance(candidate, Mapping) else None
        if isinstance(candidate_id, str):
            id_counts[candidate_id] = id_counts.get(candidate_id, 0) + 1
    duplicate_ids = {task_id for task_id, count in id_counts.items() if count > 1}
    candidates: list[Mapping[str, Any]] = []
    for cell in cells:
        task_id = cell.get("task_id") if isinstance(cell, Mapping) else "<invalid>"
        if isinstance(task_id, str) and task_id in duplicate_ids:
            rejected.append({"task_id": task_id, "reason": "duplicate task_id"})
            continue
        reason = validate_cell(cell, base_revision, contract_versions)
        if reason:
            rejected.append({"task_id": task_id if isinstance(task_id, str) else "<invalid>", "reason": reason})
            continue
        assert isinstance(cell, Mapping)
        if cell["task_id"] not in ready:
            rejected.append({"task_id": cell["task_id"], "reason": "task ID is not in live ready_ids"})
            continue
        role = cell.get("role", "worker")
        if role in _WORKER_SWEEP_ROLES or cell.get("shared_wiring") is True:
            rejected.append({"task_id": cell["task_id"], "reason": "integrator/shared-wiring work is excluded from worker sweeps"})
            continue
        candidates.append(cell)

    selected: list[Mapping[str, Any]] = []
    for cell in sorted(candidates, key=_rank):
        if len(selected) >= max_workers:
            rejected.append({"task_id": cell["task_id"], "reason": "max_workers limit reached"})
            continue
        conflict = next((reason for previous in selected if (reason := conflict_reason(cell, previous))), None)
        if conflict:
            rejected.append({"task_id": cell["task_id"], "reason": conflict})
            continue
        selected.append(cell)
    return {"selected": list(selected), "rejected": rejected}


scopes_overlap = _scope_overlap

__all__ = ["select_cells", "validate_cell", "conflict_reason", "scopes_overlap"]

