"""Atomic coordinator reservations for one shared checkout; not a distributed lock or sandbox."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import uuid

from support import DeliveryError, safe_path, source_revision
from parallel import conflict_reason


def read_leases(project):
    path = safe_path(Path(project), ".delivery/runtime/leases.json")
    if not path.exists():
        return []
    value = json.loads(path.read_text())
    if not isinstance(value, list):
        raise DeliveryError("Lease state is invalid; inspect without clearing reservations.")
    return value


@contextmanager
def locked(project):
    try:
        import fcntl
    except ImportError:
        raise DeliveryError("Atomic local reservations require POSIX flock (Linux/macOS/WSL); use an existing lease broker on other platforms.") from None
    runtime = safe_path(Path(project), ".delivery/runtime")
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / "coordinator.lock"
    if path.is_symlink():
        raise DeliveryError("Coordinator lock must not be a symlink.")
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DeliveryError("Another coordinator is changing reservations; reread after it completes.") from None
        try:
            yield runtime
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_leases(runtime, records):
    target = runtime / "leases.json"
    if target.is_symlink():
        raise DeliveryError("Lease state must not be a symlink.")
    with tempfile.NamedTemporaryFile(mode="w", dir=runtime, delete=False) as handle:
        name = handle.name
        json.dump(records, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def reserve(project, cells, owner, max_workers):
    """Called only after the guard validates cells and live readiness; rechecks source and conflicts under lock."""
    if not isinstance(owner, str) or not owner.strip() or not cells:
        raise DeliveryError("Reservation needs an owning coordinator and validated cells.")
    with locked(project) as runtime:
        existing = read_leases(project)
        revision = source_revision(project, clean=True)
        if any(cell["base_revision"] != revision for cell in cells):
            raise DeliveryError("Source advanced before reservation; recompute candidates.")
        active = [cell for record in existing for cell in record["cells"]]
        if len(active) + len(cells) > max_workers:
            raise DeliveryError("Reservation would exceed the configured WIP limit.")
        if any(cell["base_revision"] != revision for cell in active):
            raise DeliveryError("An older source generation still has active reservations; join and reconcile before advancing.")
        staged = list(active)
        for cell in cells:
            for previous in staged:
                if cell["task_id"] == previous["task_id"]:
                    raise DeliveryError("Task already reserved; no duplicate worker ownership.")
                reason = conflict_reason(cell, previous)
                if reason:
                    raise DeliveryError("Reservation conflicts with active or same-batch work: " + reason)
            staged.append(cell)
        record = {"lease_id": uuid.uuid4().hex, "owner": owner, "created_at": datetime.now(timezone.utc).isoformat(), "cells": cells}
        write_leases(runtime, [*existing, record])
        return record["lease_id"]


def release(project, lease_id, owner):
    """The coordinator must stop/join workers before release. No automatic expiry or force release."""
    with locked(project) as runtime:
        existing = read_leases(project)
        matching = [row for row in existing if row["lease_id"] == lease_id]
        if not matching or matching[0]["owner"] != owner:
            raise DeliveryError("Lease is missing or belongs to another coordinator; inspect instead of force clearing.")
        write_leases(runtime, [row for row in existing if row["lease_id"] != lease_id])

