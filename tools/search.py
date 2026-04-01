#!/usr/bin/env python3
"""
Claude History Search

Full-text regex search across session history with match highlighting.

Invoked via: python tools/cli.py search <pattern>
"""

import json
import re
import sys
import html as html_mod
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import List, Optional, Pattern

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_history.filters import strip_system_tags, extract_user_text
from claude_history.timestamps import parse_timestamp, format_duration
from claude_history.parsing import find_history_files, iter_jsonl


def scan_sessions(
    projects_dir: Path,
    pattern: Pattern,
    recent_days: Optional[int] = None,
) -> dict:
    """Scan JSONL files and return sessions with regex matches.

    Returns a dict with:
        sessions: list of session dicts (only those with matches)
        total_scanned: total number of sessions scanned
        total_projects: set of all project names scanned
        stats: {total_matches, matches_by_type: {user, assistant, tool_use, tool_result}}
    """
    history_files = find_history_files(projects_dir, recent_days=recent_days)
    if not history_files:
        return {
            "sessions": [],
            "total_scanned": 0,
            "total_projects": set(),
            "stats": {"total_matches": 0, "matches_by_type": {}},
        }

    print(f"Scanning {len(history_files)} session files...", file=sys.stderr)

    all_sessions = []
    total_scanned = 0
    total_projects = set()
    total_matches = 0
    matches_by_type = defaultdict(int)

    for i, jsonl_path in enumerate(history_files, 1):
        if i % 50 == 0:
            print(f"  {i}/{len(history_files)}...", file=sys.stderr)

        total_scanned += 1
        project_name = jsonl_path.parent.name
        total_projects.add(project_name)

        session = _scan_one_session(jsonl_path, pattern)
        if session["match_count"] > 0:
            session["project"] = project_name
            all_sessions.append(session)
            total_matches += session["match_count"]
            for ev in session["messages"]:
                if ev.get("matched"):
                    matches_by_type[ev["type"]] += len(ev.get("match_spans", []))

    print(f"Found {total_matches} matches in {len(all_sessions)} sessions", file=sys.stderr)

    return {
        "sessions": all_sessions,
        "total_scanned": total_scanned,
        "total_projects": total_projects,
        "stats": {
            "total_matches": total_matches,
            "matches_by_type": dict(matches_by_type),
        },
    }


def _scan_one_session(jsonl_path: Path, pattern: Pattern) -> dict:
    """Parse a single JSONL file, tagging events that match the pattern."""
    session = {
        "id": jsonl_path.stem,
        "file": str(jsonl_path),
        "messages": [],
        "tools_used": Counter(),
        "tool_errors": 0,
        "start_time": None,
        "end_time": None,
        "user_messages": 0,
        "assistant_messages": 0,
        "total_entries": 0,
        "git_branch": None,
        "version": None,
        "match_count": 0,
    }

    tool_id_to_name = {}

    for entry in iter_jsonl(jsonl_path):
        session["total_entries"] += 1
        ts_str = entry.get("timestamp")
        if not ts_str:
            continue

        try:
            ts = parse_timestamp(ts_str)
        except (ValueError, AttributeError):
            continue

        if session["start_time"] is None or ts < session["start_time"]:
            session["start_time"] = ts
        if session["end_time"] is None or ts > session["end_time"]:
            session["end_time"] = ts

        if not session["git_branch"]:
            session["git_branch"] = entry.get("gitBranch")
        if not session["version"]:
            session["version"] = entry.get("version")

        entry_type = entry.get("type")
        msg = entry.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]

        if entry_type == "user":
            has_text = False
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "tool_result":
                        tool_use_id = item.get("tool_use_id", "")
                        tool_name = tool_id_to_name.get(tool_use_id, "Unknown")
                        if item.get("is_error"):
                            session["tool_errors"] += 1
                        # Search tool result content
                        result_text = str(item.get("content", ""))
                        display_text = f"{tool_name}: {result_text[:300]}"
                        display_spans = _find_matches(pattern, display_text)
                        ev = {
                            "time": ts,
                            "type": "tool_result",
                            "text": display_text,
                            "tool": tool_name,
                            "matched": len(display_spans) > 0,
                            "match_spans": display_spans,
                        }
                        session["messages"].append(ev)
                        session["match_count"] += len(display_spans)

                    elif item.get("type") == "text":
                        has_text = True

            if has_text:
                session["user_messages"] += 1
                text = extract_user_text(content)
                if text:
                    spans = _find_matches(pattern, text)
                    ev = {
                        "time": ts,
                        "type": "user",
                        "text": text,
                        "matched": len(spans) > 0,
                        "match_spans": spans,
                    }
                    session["messages"].append(ev)
                    session["match_count"] += len(spans)

        elif entry_type == "assistant":
            session["assistant_messages"] += 1
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "tool_use":
                        tname = item.get("name", "unknown")
                        session["tools_used"][tname] += 1
                        tool_id_to_name[item.get("id", "")] = tname
                        # Search tool name + input
                        tool_input = json.dumps(item.get("input", {}), default=str)
                        display_text = f"{tname}: {tool_input[:300]}"
                        spans = _find_matches(pattern, display_text)
                        ev = {
                            "time": ts,
                            "type": "tool_use",
                            "text": display_text,
                            "tool": tname,
                            "matched": len(spans) > 0,
                            "match_spans": spans,
                        }
                        session["messages"].append(ev)
                        session["match_count"] += len(spans)

                    elif item.get("type") == "text" and item.get("text", "").strip():
                        text = item["text"][:200]
                        spans = _find_matches(pattern, text)
                        ev = {
                            "time": ts,
                            "type": "assistant",
                            "text": text,
                            "matched": len(spans) > 0,
                            "match_spans": spans,
                        }
                        session["messages"].append(ev)
                        session["match_count"] += len(spans)

    return session


def _find_matches(pattern: Pattern, text: str) -> list:
    """Return list of (start, end) spans for all regex matches in text."""
    return [(m.start(), m.end()) for m in pattern.finditer(text)]
