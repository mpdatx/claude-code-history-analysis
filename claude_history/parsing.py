"""JSONL parsing utilities for Claude history files."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional


def find_history_files(project_dir: Path, recent_days: Optional[int] = None) -> list[Path]:
    """Find all session JSONL files in a project directory, excluding history.jsonl.

    If recent_days is set, only return files modified within the last N days
    (uses file mtime as a fast pre-filter).
    """
    files = list(project_dir.glob("**/[0-9a-f]*-[0-9a-f]*.jsonl"))
    files = [f for f in files if f.name != "history.jsonl"]
    if recent_days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=recent_days)).timestamp()
        files = [f for f in files if f.stat().st_mtime >= cutoff]
    return files


def iter_jsonl(path: Path) -> Iterator[dict]:
    """Iterate over entries in a JSONL file, skipping blanks and bad JSON."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def iter_session_events(path: Path) -> Iterator[dict]:
    """Yield events from a session file with tool_id->name already resolved.

    Each yielded dict has keys:
        type: "user" | "assistant"
        timestamp: str
        content: list[dict]
        message: dict (original message)
        entry: dict (full original entry)

    For tool_result items in user messages, a 'tool_name' key is added
    based on the tool_use_id -> name mapping built from assistant messages.
    """
    tool_id_to_name = {}

    for entry in iter_jsonl(path):
        entry_type = entry.get("type")
        if entry_type not in ("user", "assistant"):
            continue

        msg = entry.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]

        timestamp = entry.get("timestamp", "")

        # Build tool_id -> name mapping from assistant messages
        if entry_type == "assistant" and isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    tool_id_to_name[item.get("id", "")] = item.get("name", "Unknown")

        # Resolve tool names in user messages (tool_result items)
        if entry_type == "user" and isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    tool_use_id = item.get("tool_use_id", "")
                    item["tool_name"] = tool_id_to_name.get(tool_use_id, "Unknown")

        yield {
            "type": entry_type,
            "timestamp": timestamp,
            "content": content,
            "message": msg,
            "entry": entry,
        }
