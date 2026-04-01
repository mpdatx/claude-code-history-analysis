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
from typing import Optional, Pattern

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_history.filters import extract_user_text
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


def _highlight_text(text: str, spans: list) -> str:
    """Wrap matched spans in <mark> tags. Text is HTML-escaped, spans are not."""
    if not spans:
        return html_mod.escape(text)
    parts = []
    prev = 0
    for start, end in sorted(spans):
        parts.append(html_mod.escape(text[prev:start]))
        parts.append(f"<mark>{html_mod.escape(text[start:end])}</mark>")
        prev = end
    parts.append(html_mod.escape(text[prev:]))
    return "".join(parts)


def generate_html(pattern_str: str, results: dict) -> str:
    """Generate HTML search results page."""
    from claude_history.html_theme import get_base_css

    sessions = results["sessions"]
    stats = results["stats"]
    total_scanned = results["total_scanned"]
    total_projects = results["total_projects"]
    matches_by_type = stats["matches_by_type"]

    # Sort sessions by start time (newest first for search results)
    sessions = [s for s in sessions if s["start_time"] is not None]
    sessions.sort(key=lambda s: s["start_time"], reverse=True)

    # Date range
    if sessions:
        first_date_iso = min(s["start_time"] for s in sessions).strftime("%Y-%m-%dT%H:%M:%SZ")
        last_date_iso = max(s["start_time"] for s in sessions).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        first_date_iso = last_date_iso = ""

    # Projects with matches
    projects_with_matches = len(set(s["project"] for s in sessions))

    # Heatmap: matches per day
    daily_matches = defaultdict(int)
    for s in sessions:
        day = s["start_time"].strftime("%Y-%m-%d")
        daily_matches[day] += s["match_count"]

    heatmap_html = _build_heatmap(daily_matches)

    # Stats grid
    user_matches = matches_by_type.get("user", 0)
    assistant_matches = matches_by_type.get("assistant", 0)
    tool_matches = matches_by_type.get("tool_use", 0) + matches_by_type.get("tool_result", 0)

    # Session cards
    session_cards = []
    for idx, s in enumerate(sessions):
        duration = ""
        if s["start_time"] and s["end_time"]:
            duration = format_duration(s["end_time"] - s["start_time"])

        tool_tags = ""
        for tname, tcount in s["tools_used"].most_common(6):
            tool_tags += f'<span class="tool-tag">{html_mod.escape(tname)} <small>x{tcount}</small></span> '

        # Build events HTML
        events = s["messages"]
        events_html = ""
        prev_time = None
        i = 0
        while i < len(events):
            ev = events[i]
            ev_time = ev["time"]
            iso_str = ev_time.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Gap indicator (>20 min)
            if prev_time is not None:
                gap = (ev_time - prev_time).total_seconds()
                if gap > 1200:
                    gap_mins = int(gap / 60)
                    if gap_mins < 60:
                        gap_label = f"{gap_mins} min gap"
                    else:
                        gap_h = gap_mins // 60
                        gap_m = gap_mins % 60
                        gap_label = f"{gap_h}h {gap_m}m gap" if gap_m else f"{gap_h}h gap"
                    events_html += f'<div class="event-gap"><span class="gap-line"></span><span class="gap-label">{gap_label}</span><span class="gap-line"></span></div>\n'

            matched_cls = " event-matched" if ev.get("matched") else ""
            display_text = _highlight_text(ev.get("text", ""), ev.get("match_spans", []))

            if ev["type"] == "tool_use":
                # Collapse consecutive non-matched tool_use events
                if not ev.get("matched"):
                    j = i + 1
                    tool_names = [ev.get("tool", "")]
                    while j < len(events) and events[j]["type"] == "tool_use" and not events[j].get("matched"):
                        tool_names.append(events[j].get("tool", ""))
                        j += 1
                    if j > i + 1:
                        # Collapsed group
                        seen = {}
                        order = []
                        for t in tool_names:
                            if t not in seen:
                                seen[t] = 0
                                order.append(t)
                            seen[t] += 1
                        summary = ", ".join(
                            f"{html_mod.escape(t)} x{seen[t]}" if seen[t] > 1 else html_mod.escape(t)
                            for t in order
                        )
                        events_html += f'<div class="event event-tool"><span class="ev-time" data-utc="{iso_str}"></span> <span class="ev-badge badge-tool">{len(tool_names)} TOOLS</span> {summary}</div>\n'
                        prev_time = events[j - 1]["time"]
                        i = j
                        continue
                # Single tool_use (matched or standalone)
                events_html += f'<div class="event event-tool{matched_cls}"><span class="ev-time" data-utc="{iso_str}"></span> <span class="ev-badge badge-tool">TOOL</span> {display_text}</div>\n'

            elif ev["type"] == "tool_result":
                events_html += f'<div class="event event-tool{matched_cls}"><span class="ev-time" data-utc="{iso_str}"></span> <span class="ev-badge badge-result">RESULT</span> {display_text}</div>\n'

            elif ev["type"] == "user":
                events_html += f'<div class="event event-user{matched_cls}"><span class="ev-time" data-utc="{iso_str}"></span> <span class="ev-badge badge-user">USER</span> {display_text}</div>\n'

            elif ev["type"] == "assistant":
                events_html += f'<div class="event event-assistant{matched_cls}"><span class="ev-time" data-utc="{iso_str}"></span> <span class="ev-badge badge-assistant">CLAUDE</span> {display_text}</div>\n'

            prev_time = ev_time
            i += 1

        branch_badge = ""
        if s["git_branch"]:
            branch_badge = f'<span class="branch-tag">{html_mod.escape(s["git_branch"])}</span>'

        error_badge = ""
        if s["tool_errors"] > 0:
            error_badge = f'<span class="error-count">{s["tool_errors"]} errors</span>'

        match_badge = f'<span class="match-count">{s["match_count"]} match{"es" if s["match_count"] != 1 else ""}</span>'

        start_iso = s["start_time"].strftime("%Y-%m-%dT%H:%M:%SZ")
        total_tools_session = sum(s["tools_used"].values())

        project_badge = f'<span class="project-tag">{html_mod.escape(s["project"])}</span>'

        card = f"""
        <div class="session-card" onclick="toggleDetail(this)">
            <div class="session-header">
                <div class="session-title">
                    <span class="session-num">#{idx + 1}</span>
                    <span class="session-date" data-utc="{start_iso}" data-fmt="datetime"></span>
                    <span class="session-duration">{duration}</span>
                    {project_badge}
                    {branch_badge}
                    {match_badge}
                    {error_badge}
                </div>
                <div class="session-stats">
                    <span class="stat"><b>{s['user_messages']}</b> user msgs</span>
                    <span class="stat"><b>{s['assistant_messages']}</b> assistant msgs</span>
                    <span class="stat"><b>{total_tools_session}</b> tool calls</span>
                </div>
            </div>
            <div class="session-tools">{tool_tags}</div>
            <div class="session-detail" style="display:none">
                <div class="session-nav">
                    <button class="match-nav-btn" onclick="event.stopPropagation(); jumpToMatch(this, -1)">&#9650; Prev</button>
                    <button class="match-nav-btn" onclick="event.stopPropagation(); jumpToMatch(this, 1)">&#9660; Next</button>
                </div>
                <div class="events-timeline">
                    {events_html}
                </div>
            </div>
        </div>
        """
        session_cards.append(card)

    cards_html = "\n".join(session_cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Search: {html_mod.escape(pattern_str)}</title>
<style>
{get_base_css()}

/* Session cards (from timeline) */
.session-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: border-color 0.2s;
}}
.session-card:hover {{ border-color: var(--accent); }}
.session-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
}}
.session-title {{
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}}
.session-num {{ color: var(--text2); font-size: 13px; font-weight: 600; }}
.session-date {{ font-weight: 600; font-size: 15px; }}
.session-duration {{
    color: var(--text2); font-size: 13px;
    background: var(--surface2); padding: 2px 8px; border-radius: 12px;
}}
.session-stats {{
    display: flex; gap: 14px; font-size: 13px; color: var(--text2);
}}
.session-stats b {{ color: var(--text); }}
.session-tools {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }}
.tool-tag {{
    display: inline-block; background: var(--surface2);
    border: 1px solid var(--border); padding: 2px 8px;
    border-radius: 12px; font-size: 12px; color: var(--purple);
}}
.tool-tag small {{ color: var(--text2); }}
.branch-tag {{
    background: rgba(56, 139, 253, 0.15); color: var(--accent);
    padding: 2px 8px; border-radius: 12px; font-size: 12px;
}}
.error-count {{
    background: rgba(248, 81, 73, 0.15); color: var(--red);
    padding: 2px 8px; border-radius: 12px; font-size: 12px;
}}
.match-count {{
    background: rgba(210, 153, 34, 0.25); color: var(--orange);
    padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600;
}}
.project-tag {{
    background: rgba(63, 185, 80, 0.15); color: var(--green);
    padding: 2px 8px; border-radius: 12px; font-size: 12px;
}}

/* Events timeline */
.session-detail {{ margin-top: 12px; }}
.events-timeline {{
    border-left: 2px solid var(--border);
    margin-left: 12px; padding-left: 16px;
}}
.event {{ font-size: 13px; padding: 3px 0; line-height: 1.4; }}
.event-matched {{ background: rgba(210, 153, 34, 0.08); border-radius: 4px; padding: 3px 6px; }}
.ev-time {{
    color: var(--text2); font-size: 11px; font-family: monospace; margin-right: 6px;
}}
.ev-badge {{
    display: inline-block; padding: 0 6px; border-radius: 4px;
    font-size: 10px; font-weight: 700; letter-spacing: 0.3px; margin-right: 4px;
}}
.badge-user {{ background: rgba(56,139,253,0.2); color: var(--accent); }}
.badge-assistant {{ background: rgba(63,185,80,0.2); color: var(--green); }}
.badge-tool {{ background: rgba(188,140,255,0.2); color: var(--purple); }}
.badge-result {{ background: rgba(188,140,255,0.12); color: var(--purple); }}

/* Match highlighting */
mark {{
    background: rgba(210, 153, 34, 0.3);
    color: var(--text);
    padding: 1px 3px;
    border-radius: 3px;
    border-bottom: 2px solid var(--orange);
}}

/* Match navigation */
.session-nav {{
    display: flex; gap: 8px; margin-bottom: 8px;
}}
.match-nav-btn {{
    background: var(--surface2); border: 1px solid var(--border);
    color: var(--text2); padding: 4px 12px; border-radius: 6px;
    font-size: 12px; cursor: pointer;
}}
.match-nav-btn:hover {{ border-color: var(--accent); color: var(--text); }}

/* Time gap */
.event-gap {{ display: flex; align-items: center; gap: 10px; margin: 10px 0; }}
.gap-line {{ flex: 1; height: 1px; background: var(--border); }}
.gap-label {{
    font-size: 11px; color: var(--orange);
    white-space: nowrap; letter-spacing: 0.3px;
}}

/* Heatmap */
.heatmap-container {{ overflow-x: auto; padding: 10px 0; }}
.heatmap {{ display: flex; gap: 3px; flex-wrap: wrap; }}
.heatmap-cell {{
    width: 14px; height: 14px; border-radius: 2px; position: relative;
}}
.heatmap-cell:hover::after {{
    content: attr(data-tip);
    position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%);
    background: var(--surface); border: 1px solid var(--border);
    padding: 4px 8px; border-radius: 4px; font-size: 11px;
    white-space: nowrap; z-index: 10; color: var(--text);
}}
.heat-0 {{ background: var(--surface2); }}
.heat-1 {{ background: #0e4429; }}
.heat-2 {{ background: #006d32; }}
.heat-3 {{ background: #26a641; }}
.heat-4 {{ background: #39d353; }}

@media (max-width: 700px) {{
    .session-header {{ flex-direction: column; align-items: flex-start; }}
    .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
</style>
</head>
<body>
<div class="header">
    <h1>Search: <code>{html_mod.escape(pattern_str)}</code></h1>
    <div class="subtitle"><span data-utc="{first_date_iso}" data-fmt="date"></span> &mdash; <span data-utc="{last_date_iso}" data-fmt="date"></span> &middot; Generated {datetime.now().strftime("%b %d, %Y %H:%M")}</div>
</div>

<div class="container">
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-value">{stats['total_matches']}</div><div class="stat-label">Total Matches</div></div>
        <div class="stat-card"><div class="stat-value">{len(sessions)}</div><div class="stat-label">Sessions</div></div>
        <div class="stat-card"><div class="stat-value">{projects_with_matches}</div><div class="stat-label">Projects</div></div>
        <div class="stat-card"><div class="stat-value">{user_matches}</div><div class="stat-label">User Matches</div></div>
        <div class="stat-card"><div class="stat-value">{assistant_matches}</div><div class="stat-label">Assistant Matches</div></div>
        <div class="stat-card"><div class="stat-value">{tool_matches}</div><div class="stat-label">Tool Matches</div></div>
    </div>

    <div class="section">
        <div class="section-title">Match Activity</div>
        {heatmap_html}
    </div>

    <div class="section">
        <div class="section-title">Results</div>
        <div class="filter-bar">
            <input type="text" id="filterInput" placeholder="Filter results (project, branch, tool...)" oninput="filterSessions()">
        </div>
        <div id="sessionList">
            {cards_html}
        </div>
    </div>
</div>

<script>
function toggleDetail(card) {{
    const detail = card.querySelector('.session-detail');
    if (detail) {{
        detail.style.display = detail.style.display === 'none' ? 'block' : 'none';
    }}
}}
function filterSessions() {{
    const q = document.getElementById('filterInput').value.toLowerCase();
    document.querySelectorAll('.session-card').forEach(card => {{
        card.style.display = card.textContent.toLowerCase().includes(q) ? '' : 'none';
    }});
}}
function jumpToMatch(btn, direction) {{
    const card = btn.closest('.session-card');
    const marks = card.querySelectorAll('mark');
    if (!marks.length) return;
    const current = parseInt(card.dataset.matchIdx || (direction > 0 ? '-1' : '0'), 10);
    let next = current + direction;
    if (next >= marks.length) next = 0;
    if (next < 0) next = marks.length - 1;
    card.dataset.matchIdx = next;
    marks[next].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    // Flash effect
    marks[next].style.outline = '2px solid var(--orange)';
    setTimeout(() => {{ marks[next].style.outline = ''; }}, 1000);
}}

// UTC to local time
document.querySelectorAll('[data-utc]').forEach(el => {{
    const utc = el.getAttribute('data-utc');
    if (!utc) return;
    const d = new Date(utc);
    const fmt = el.getAttribute('data-fmt');
    if (fmt === 'date') {{
        el.textContent = d.toLocaleDateString(undefined, {{ year: 'numeric', month: 'short', day: 'numeric' }});
    }} else if (fmt === 'datetime') {{
        el.textContent = d.toLocaleDateString(undefined, {{ year: 'numeric', month: 'short', day: 'numeric' }})
            + ' ' + d.toLocaleTimeString(undefined, {{ hour: '2-digit', minute: '2-digit' }});
    }} else {{
        el.textContent = d.toLocaleDateString(undefined, {{ month: 'short', day: 'numeric' }})
            + ' ' + d.toLocaleTimeString(undefined, {{ hour: '2-digit', minute: '2-digit', second: '2-digit' }});
    }}
}});
</script>
</body>
</html>"""


def _build_heatmap(daily_counts: dict) -> str:
    """Build a GitHub-style heatmap from daily counts."""
    if not daily_counts:
        return '<div class="heatmap-container"><em style="color:var(--text2)">No matches</em></div>'

    all_dates = sorted(daily_counts.keys())
    start = datetime.strptime(all_dates[0], "%Y-%m-%d")
    end = datetime.strptime(all_dates[-1], "%Y-%m-%d")

    values = sorted(daily_counts.values())
    if values:
        q1 = values[len(values) // 4] if len(values) > 3 else 1
        q2 = values[len(values) // 2] if len(values) > 1 else 2
        q3 = values[3 * len(values) // 4] if len(values) > 3 else 3
    else:
        q1 = q2 = q3 = 1

    cells = []
    current = start
    while current <= end:
        day_str = current.strftime("%Y-%m-%d")
        count = daily_counts.get(day_str, 0)
        if count == 0:
            level = 0
        elif count <= q1:
            level = 1
        elif count <= q2:
            level = 2
        elif count <= q3:
            level = 3
        else:
            level = 4
        label = f"{day_str}: {count} matches"
        cells.append(f'<div class="heatmap-cell heat-{level}" data-tip="{label}"></div>')
        current += timedelta(days=1)

    return f'<div class="heatmap-container"><div class="heatmap">{"".join(cells)}</div></div>'


def generate_markdown(pattern_str: str, results: dict) -> str:
    """Generate markdown search results (terminal output)."""
    sessions = results["sessions"]
    stats = results["stats"]
    total_projects = results["total_projects"]

    sessions = [s for s in sessions if s["start_time"] is not None]
    sessions.sort(key=lambda s: s["start_time"], reverse=True)

    projects_with_matches = len(set(s["project"] for s in sessions))

    lines = []
    lines.append(f'## Search: "{pattern_str}" -- {stats["total_matches"]} matches across {len(sessions)} sessions in {projects_with_matches} projects')
    lines.append("")

    for s in sessions:
        dt = s["start_time"].strftime("%Y-%m-%d %H:%M")
        lines.append(f'### Session: {dt} ({s["project"]}) -- {s["match_count"]} matches')

        for ev in s["messages"]:
            if not ev.get("matched"):
                continue
            label = ev["type"].upper()
            text = ev.get("text", "")[:200]
            # Filter spans to fit truncated text
            spans = [(s, min(e, 200)) for s, e in ev.get("match_spans", []) if s < 200]
            highlighted = _highlight_markdown(text, spans)
            lines.append(f"  [{label:12s}] {highlighted}")

        lines.append("")

    return "\n".join(lines)


def _highlight_markdown(text: str, spans: list) -> str:
    """Wrap matched spans in **bold** for markdown."""
    if not spans:
        return text
    parts = []
    prev = 0
    for start, end in sorted(spans):
        parts.append(text[prev:start])
        parts.append(f"**{text[start:end]}**")
        prev = end
    parts.append(text[prev:])
    return "".join(parts)
