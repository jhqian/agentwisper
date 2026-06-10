# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Broker version information.

Version format: <major.minor.patch>+<git_short_hash>[.dirty]
Example: 0.2.0+abc1234.dirty
"""

from __future__ import annotations

import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def get_version() -> str:
    """Return the broker version string.

    Composed of the installed package version plus git HEAD short hash.
    Appends '.dirty' if the working tree has uncommitted changes.
    Falls back to package version alone when git info is unavailable.
    """
    try:
        pkg_version = version("agentsquad")
    except PackageNotFoundError:
        pkg_version = "0.0.0"

    git_info = _git_info()
    if git_info:
        return f"{pkg_version}+{git_info}"
    return pkg_version


def _git_info() -> str | None:
    """Extract git short hash and dirty flag from the source repository."""
    repo_root = _find_repo_root()
    if repo_root is None:
        return None

    short_hash = _run_git(["rev-parse", "--short", "HEAD"], repo_root)
    if short_hash is None:
        return None

    dirty = _run_git(["status", "--porcelain"], repo_root)
    if dirty is not None and dirty.strip():
        return f"{short_hash}.dirty"
    return short_hash


def _find_repo_root() -> Path | None:
    """Walk upward from this file to find a .git directory."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _run_git(args: list[str], cwd: Path) -> str | None:
    """Run a git command, returning stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None
