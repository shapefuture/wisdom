#!/usr/bin/env python3
"""Build a portable skill archive containing only package source, references and tests."""
import argparse
import hashlib
from pathlib import Path
import sys
import zipfile

PACKAGE = Path(__file__).resolve().parents[1]


def package_files(package=PACKAGE):
    roots = {"SKILL.md", "README.md", ".gitignore"}
    for file in sorted(package.rglob("*")):
        if not file.is_file() or file.is_symlink() or "__pycache__" in file.parts:
            continue
        relative = file.relative_to(package)
        allowed = (str(relative) in roots or (relative.parts[0] in {"scripts", "tests"} and file.suffix == ".py")
                   or (relative.parts[0] == "references" and file.suffix == ".md")
                   or (relative.parts[0] == "templates" and file.suffix == ".json"))
        if allowed:
            yield file


def build(output, replace=False):
    destination = Path(output).absolute()
    if destination.is_symlink():
        raise ValueError("Archive destination must not be a symlink.")
    output = destination.resolve()
    if output.is_relative_to(PACKAGE):
        raise ValueError("Archive destination must be outside the skill directory and not a symlink.")
    if output.exists() and not replace:
        raise ValueError("Archive already exists; use --replace only for the intended generated artifact.")
    output.parent.mkdir(parents=True, exist_ok=True)
    files = list(package_files())
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            info = zipfile.ZipInfo("full-plan-delivery/" + file.relative_to(PACKAGE).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, file.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"Packaged {len(files)} files: {output.name}; sha256={digest}")
    return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    try:
        build(args.output, args.replace)
    except (OSError, ValueError) as error:
        print(f"Packaging stopped: {error}", file=sys.stderr)
        raise SystemExit(2)

