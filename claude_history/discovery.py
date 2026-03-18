"""Project discovery utilities for Claude history files."""

import sys
from pathlib import Path
from typing import Optional


HISTORY_ROOT = Path.home() / ".claude" / "projects"


def find_projects_dir() -> Path:
    """Auto-detect the Claude projects directory.

    Checks the default location first, then alternatives. Prints a warning
    to stderr if no directory is found.
    """
    if HISTORY_ROOT.exists():
        return HISTORY_ROOT

    alternatives = [
        Path.home() / ".config" / "claude" / "projects",
        Path("C:/Users") / Path.home().name / ".claude" / "projects",
    ]

    for alt in alternatives:
        if alt.exists():
            return alt

    print(f"Warning: no Claude projects directory found (checked {HISTORY_ROOT} and alternatives)", file=sys.stderr)
    return HISTORY_ROOT


def find_project(name: str) -> Optional[Path]:
    """Find a project directory matching the given name (fuzzy)."""
    projects_dir = find_projects_dir()
    if not projects_dir.exists():
        return None
    # Exact match first
    exact = projects_dir / name
    if exact.is_dir():
        return exact
    # Substring match
    matches = [d for d in projects_dir.iterdir() if d.is_dir() and name.lower() in d.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Ambiguous project name '{name}'. Matches:")
        for m in matches:
            print(f"  {m.name}")
        return None
    print(f"No project found matching '{name}'")
    return None


def list_projects():
    """List all available project directories."""
    projects_dir = find_projects_dir()
    if not projects_dir.exists():
        print(f"No history directory found at {projects_dir}")
        return
    projects = sorted(d.name for d in projects_dir.iterdir() if d.is_dir())
    print(f"Available projects ({len(projects)}):\n")
    for p in projects:
        jsonl_count = len(list((projects_dir / p).glob("*.jsonl")))
        print(f"  {p}  ({jsonl_count} sessions)")
