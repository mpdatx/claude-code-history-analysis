#!/usr/bin/env python3
"""
Claude Project Timeline Generator

Parses JSONL history files for a given Claude project and generates
an interactive HTML timeline visualization.

Invoked via: python tools/cli.py timeline <project-name>
"""

import sys
import html
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_history.filters import extract_user_text, is_injected_text, strip_system_tags, TRUNCATED_PREFIXES
from claude_history.timestamps import parse_timestamp, format_duration
from claude_history.parsing import iter_jsonl

def parse_session(jsonl_path: Path) -> dict:
    """Parse a single JSONL session file and extract timeline data.

    Note: Uses iter_jsonl() directly instead of iter_session_events() because
    timeline needs per-entry access to gitBranch, version, and raw timestamps
    that the higher-level iterator doesn't expose.
    """
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
                        if item.get("is_error"):
                            session["tool_errors"] += 1
                    elif item.get("type") == "text":
                        has_text = True
            if has_text:
                session["user_messages"] += 1
                text = extract_user_text(content)
                if text:
                    session["messages"].append({
                        "time": ts,
                        "type": "user",
                        "text": text,
                    })

        elif entry_type == "assistant":
            session["assistant_messages"] += 1
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "tool_use":
                        tname = item.get("name", "unknown")
                        session["tools_used"][tname] += 1
                        tool_id_to_name[item.get("id", "")] = tname
                        session["messages"].append({
                            "time": ts,
                            "type": "tool_use",
                            "tool": tname,
                        })
                    elif item.get("type") == "text" and item.get("text", "").strip():
                        session["messages"].append({
                            "time": ts,
                            "type": "assistant",
                            "text": item["text"][:200],
                        })

    return session


def generate_html(project_name: str, sessions: list) -> str:
    """Generate the HTML timeline."""
    # Sort sessions by start time
    sessions = [s for s in sessions if s["start_time"] is not None]
    sessions.sort(key=lambda s: s["start_time"])

    # Compute project-level stats
    total_sessions = len(sessions)
    total_messages = sum(s["user_messages"] + s["assistant_messages"] for s in sessions)
    total_tool_calls = sum(sum(s["tools_used"].values()) for s in sessions)
    total_errors = sum(s["tool_errors"] for s in sessions)
    all_tools = Counter()
    for s in sessions:
        all_tools.update(s["tools_used"])
    top_tools = all_tools.most_common(10)

    # Date range (ISO for JS conversion)
    if sessions:
        first_date_iso = sessions[0]["start_time"].strftime("%Y-%m-%dT%H:%M:%SZ")
        last_date_iso = sessions[-1]["start_time"].strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        first_date_iso = last_date_iso = ""

    # Group sessions by date
    sessions_by_date = defaultdict(list)
    for s in sessions:
        day = s["start_time"].strftime("%Y-%m-%d")
        sessions_by_date[day].append(s)

    # Activity heatmap data (messages per day)
    daily_activity = {}
    for day, day_sessions in sessions_by_date.items():
        daily_activity[day] = sum(
            s["user_messages"] + s["assistant_messages"] for s in day_sessions
        )

    # Build session cards HTML
    session_cards = []
    for idx, s in enumerate(sessions):
        duration = ""
        if s["start_time"] and s["end_time"]:
            duration = format_duration(s["end_time"] - s["start_time"])

        tool_tags = ""
        for tname, tcount in s["tools_used"].most_common(6):
            tool_tags += f'<span class="tool-tag">{html.escape(tname)} <small>x{tcount}</small></span> '

        # Build events HTML, collapsing consecutive tool_use into single lines
        events = s["messages"]
        events_html = ""
        prev_time = None
        i = 0
        while i < len(events):
            ev = events[i]
            ev_time = ev["time"]
            iso_str = ev_time.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Insert gap indicator for significant pauses (>20 minutes)
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

            if ev["type"] == "tool_use":
                # Collect consecutive tool_use events
                tool_names = [ev.get("tool", "")]
                j = i + 1
                while j < len(events) and events[j]["type"] == "tool_use":
                    tool_names.append(events[j].get("tool", ""))
                    j += 1
                last_iso = events[j - 1]["time"].strftime("%Y-%m-%dT%H:%M:%SZ")
                if len(tool_names) == 1:
                    events_html += f'<div class="event event-tool"><span class="ev-time" data-utc="{iso_str}"></span> <span class="ev-badge badge-tool">TOOL</span> {html.escape(tool_names[0])}</div>\n'
                    prev_time = ev_time
                else:
                    seen = {}
                    order = []
                    for t in tool_names:
                        if t not in seen:
                            seen[t] = 0
                            order.append(t)
                        seen[t] += 1
                    summary = ", ".join(
                        f"{html.escape(t)} x{seen[t]}" if seen[t] > 1 else html.escape(t)
                        for t in order
                    )
                    events_html += f'<div class="event event-tool"><span class="ev-time" data-utc="{iso_str}"></span>&ndash;<span class="ev-time" data-utc="{last_iso}"></span> <span class="ev-badge badge-tool">{len(tool_names)} TOOLS</span> {summary}</div>\n'
                prev_time = events[j - 1]["time"]
                i = j
            elif ev["type"] == "user":
                text = html.escape(ev.get("text", ""))
                events_html += f'<div class="event event-user"><span class="ev-time" data-utc="{iso_str}"></span> <span class="ev-badge badge-user">USER</span> {text}</div>\n'
                prev_time = ev_time
                i += 1
            elif ev["type"] == "assistant":
                text = html.escape(ev.get("text", "")[:120])
                events_html += f'<div class="event event-assistant"><span class="ev-time" data-utc="{iso_str}"></span> <span class="ev-badge badge-assistant">CLAUDE</span> {text}</div>\n'
                prev_time = ev_time
                i += 1
            else:
                prev_time = ev_time
                i += 1

        branch_badge = ""
        if s["git_branch"]:
            branch_badge = f'<span class="branch-tag">{html.escape(s["git_branch"])}</span>'

        error_badge = ""
        if s["tool_errors"] > 0:
            error_badge = f'<span class="error-count">{s["tool_errors"]} errors</span>'

        start_iso = s["start_time"].strftime("%Y-%m-%dT%H:%M:%SZ")
        total_tools_session = sum(s["tools_used"].values())

        card = f"""
        <div class="session-card" onclick="toggleDetail(this)">
            <div class="session-header">
                <div class="session-title">
                    <span class="session-num">#{idx + 1}</span>
                    <span class="session-date" data-utc="{start_iso}" data-fmt="datetime"></span>
                    <span class="session-duration">{duration}</span>
                    {branch_badge}
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
                <div class="events-timeline">
                    {events_html}
                </div>
            </div>
        </div>
        """
        session_cards.append(card)

    cards_html = "\n".join(session_cards)

    # Top tools chart (simple CSS bar chart)
    max_tool_count = top_tools[0][1] if top_tools else 1
    tools_bars = ""
    for tname, tcount in top_tools:
        pct = (tcount / max_tool_count) * 100
        tools_bars += f"""
        <div class="bar-row">
            <span class="bar-label">{html.escape(tname)}</span>
            <div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>
            <span class="bar-value">{tcount}</span>
        </div>"""

    # Heatmap
    heatmap_html = _build_heatmap(daily_activity)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Timeline — {html.escape(project_name)}</title>
<style>
:root {{
    --bg: #0d1117;
    --surface: #161b22;
    --surface2: #1c2129;
    --border: #30363d;
    --text: #e6edf3;
    --text2: #8b949e;
    --accent: #58a6ff;
    --accent2: #388bfd;
    --green: #3fb950;
    --red: #f85149;
    --orange: #d29922;
    --purple: #bc8cff;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    padding: 0;
}}
.container {{ max-width: 1100px; margin: 0 auto; padding: 24px 20px; }}

/* Header */
.header {{
    text-align: center;
    padding: 40px 20px 30px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 30px;
}}
.header h1 {{
    font-size: 28px;
    font-weight: 600;
    margin-bottom: 6px;
}}
.header .subtitle {{
    color: var(--text2);
    font-size: 15px;
}}

/* Stats grid */
.stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 14px;
    margin-bottom: 30px;
}}
.stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px;
    text-align: center;
}}
.stat-card .stat-value {{
    font-size: 28px;
    font-weight: 700;
    color: var(--accent);
}}
.stat-card .stat-label {{
    font-size: 12px;
    color: var(--text2);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 2px;
}}

/* Sections */
.section {{ margin-bottom: 30px; }}
.section-title {{
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
}}

/* Bar chart */
.bar-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
}}
.bar-label {{
    width: 120px;
    text-align: right;
    font-size: 13px;
    color: var(--text2);
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}
.bar-track {{
    flex: 1;
    height: 20px;
    background: var(--surface2);
    border-radius: 4px;
    overflow: hidden;
}}
.bar-fill {{
    height: 100%;
    background: linear-gradient(90deg, var(--accent2), var(--accent));
    border-radius: 4px;
    transition: width 0.5s;
}}
.bar-value {{
    width: 50px;
    font-size: 13px;
    color: var(--text2);
}}

/* Heatmap */
.heatmap-container {{
    overflow-x: auto;
    padding: 10px 0;
}}
.heatmap {{
    display: flex;
    gap: 3px;
    flex-wrap: wrap;
}}
.heatmap-cell {{
    width: 14px;
    height: 14px;
    border-radius: 2px;
    position: relative;
}}
.heatmap-cell:hover::after {{
    content: attr(data-tip);
    position: absolute;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
    white-space: nowrap;
    z-index: 10;
    color: var(--text);
}}
.heat-0 {{ background: var(--surface2); }}
.heat-1 {{ background: #0e4429; }}
.heat-2 {{ background: #006d32; }}
.heat-3 {{ background: #26a641; }}
.heat-4 {{ background: #39d353; }}

/* Session cards */
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
.session-num {{
    color: var(--text2);
    font-size: 13px;
    font-weight: 600;
}}
.session-date {{
    font-weight: 600;
    font-size: 15px;
}}
.session-duration {{
    color: var(--text2);
    font-size: 13px;
    background: var(--surface2);
    padding: 2px 8px;
    border-radius: 12px;
}}
.session-stats {{
    display: flex;
    gap: 14px;
    font-size: 13px;
    color: var(--text2);
}}
.session-stats b {{ color: var(--text); }}
.session-tools {{
    margin-top: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}}
.tool-tag {{
    display: inline-block;
    background: var(--surface2);
    border: 1px solid var(--border);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 12px;
    color: var(--purple);
}}
.tool-tag small {{ color: var(--text2); }}
.branch-tag {{
    background: rgba(56, 139, 253, 0.15);
    color: var(--accent);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 12px;
}}
.error-count {{
    background: rgba(248, 81, 73, 0.15);
    color: var(--red);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 12px;
}}

/* Events timeline */
.session-detail {{ margin-top: 12px; }}
.events-timeline {{
    border-left: 2px solid var(--border);
    margin-left: 12px;
    padding-left: 16px;
}}
.event {{
    font-size: 13px;
    padding: 3px 0;
    line-height: 1.4;
}}
.ev-time {{
    color: var(--text2);
    font-size: 11px;
    font-family: monospace;
    margin-right: 6px;
}}
.ev-badge {{
    display: inline-block;
    padding: 0 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.3px;
    margin-right: 4px;
}}
.badge-user {{ background: rgba(56,139,253,0.2); color: var(--accent); }}
.badge-assistant {{ background: rgba(63,185,80,0.2); color: var(--green); }}
.badge-tool {{ background: rgba(188,140,255,0.2); color: var(--purple); }}
.badge-error {{ background: rgba(248,81,73,0.2); color: var(--red); }}
.event-error {{ color: var(--red); }}

/* Time gap divider */
.event-gap {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 10px 0;
}}
.gap-line {{
    flex: 1;
    height: 1px;
    background: var(--border);
}}
.gap-label {{
    font-size: 11px;
    color: var(--orange);
    white-space: nowrap;
    letter-spacing: 0.3px;
}}

/* Filter */
.filter-bar {{
    display: flex;
    gap: 10px;
    margin-bottom: 16px;
    align-items: center;
}}
.filter-bar input {{
    flex: 1;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    color: var(--text);
    font-size: 14px;
    outline: none;
}}
.filter-bar input:focus {{ border-color: var(--accent); }}
.filter-bar input::placeholder {{ color: var(--text2); }}

@media (max-width: 700px) {{
    .session-header {{ flex-direction: column; align-items: flex-start; }}
    .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .bar-label {{ width: 80px; }}
}}
</style>
</head>
<body>
<div class="header">
    <h1>{html.escape(project_name)}</h1>
    <div class="subtitle"><span data-utc="{first_date_iso}" data-fmt="date"></span> &mdash; <span data-utc="{last_date_iso}" data-fmt="date"></span> &middot; Generated {datetime.now().strftime("%b %d, %Y %H:%M")}</div>
</div>

<div class="container">
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-value">{total_sessions}</div><div class="stat-label">Sessions</div></div>
        <div class="stat-card"><div class="stat-value">{total_messages:,}</div><div class="stat-label">Messages</div></div>
        <div class="stat-card"><div class="stat-value">{total_tool_calls:,}</div><div class="stat-label">Tool Calls</div></div>
        <div class="stat-card"><div class="stat-value">{total_errors}</div><div class="stat-label">Tool Errors</div></div>
        <div class="stat-card"><div class="stat-value">{len(all_tools)}</div><div class="stat-label">Unique Tools</div></div>
        <div class="stat-card"><div class="stat-value">{len(sessions_by_date)}</div><div class="stat-label">Active Days</div></div>
    </div>

    <div class="section">
        <div class="section-title">Activity Heatmap</div>
        {heatmap_html}
    </div>

    <div class="section">
        <div class="section-title">Top Tools</div>
        {tools_bars}
    </div>

    <div class="section">
        <div class="section-title">Sessions</div>
        <div class="filter-bar">
            <input type="text" id="filterInput" placeholder="Filter sessions (branch, tool, date...)" oninput="filterSessions()">
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

// Convert all UTC timestamps to local time
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
        // Default: date + time (for event timestamps)
        el.textContent = d.toLocaleDateString(undefined, {{ month: 'short', day: 'numeric' }})
            + ' ' + d.toLocaleTimeString(undefined, {{ hour: '2-digit', minute: '2-digit', second: '2-digit' }});
    }}
}});
</script>
</body>
</html>"""


def _build_heatmap(daily_activity: dict) -> str:
    """Build a GitHub-style contribution heatmap."""
    if not daily_activity:
        return '<div class="heatmap-container"><em style="color:var(--text2)">No activity data</em></div>'

    all_dates = sorted(daily_activity.keys())
    start = datetime.strptime(all_dates[0], "%Y-%m-%d")
    end = datetime.strptime(all_dates[-1], "%Y-%m-%d")

    # Quantile thresholds
    values = sorted(daily_activity.values())
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
        count = daily_activity.get(day_str, 0)
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
        label = f"{day_str}: {count} messages"
        cells.append(f'<div class="heatmap-cell heat-{level}" data-tip="{label}"></div>')
        current += timedelta(days=1)

    return f'<div class="heatmap-container"><div class="heatmap">{"".join(cells)}</div></div>'


