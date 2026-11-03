"""Shared errors, path boundaries and immutable Git identity (no tracker side effects)."""
from pathlib import Path
import subprocess


class DeliveryError(RuntimeError):
    pass


def safe_path(project, name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or "\\" in str(name):
        raise DeliveryError("Artifact paths must be relative to the project without traversal.")
    resolved = (project / path).resolve()
    if not resolved.is_relative_to(project.resolve()):
        raise DeliveryError("Artifact path escapes the project through a symlink.")
    return resolved


def source_revision(project, clean=False):
    def git(*args):
        result = subprocess.run(["git", *args], cwd=project, capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise DeliveryError("A readable Git source baseline is required for write sweeps.")
        return result.stdout.strip()
    revision = git("rev-parse", "HEAD")
    if clean and git("status", "--porcelain", "--untracked-files=all"):
        raise DeliveryError("Parallel write sweeps require a clean, committed immutable baseline. Preserve dirty files and reconcile them; never reset or stash user changes automatically.")
    return "git:" + revision

