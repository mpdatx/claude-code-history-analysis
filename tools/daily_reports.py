#!/usr/bin/env python3
"""
Daily Tool Failure Reports

Generates daily reports of failed tool calls, organized by project and time.
Creates one markdown file per day in the output directory.

Invoked via: python tools/cli.py daily
"""

import html as html_mod
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List
from datetime import datetime
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_history.errors import classify_error
from claude_history.parsing import find_history_files, iter_session_events
from claude_history.timestamps import parse_timestamp

@dataclass
class FailedCall:
    timestamp: str
    date: str
    time: str
    tool_name: str
    session: str
    project: str
    error_text: str
    error_type: str


def scan_history_files(projects_dir: Path) -> Dict[str, List[FailedCall]]:
    history_files = find_history_files(projects_dir)
    if not history_files:
        print(f"Error: no history files found in {projects_dir}", file=sys.stderr)
        return {}

    print(f"Scanning {len(history_files)} session files for failures...", file=sys.stderr)

    failed_by_date = defaultdict(list)

    for i, file_path in enumerate(history_files, 1):
        if i % 50 == 0:
            print(f"  Processing {i}/{len(history_files)}...", file=sys.stderr)

        try:
            session_id = file_path.stem
            project = file_path.parent.name

            for event in iter_session_events(file_path):
                if event["type"] != "user":
                    continue

                for item in event["content"]:
                    if isinstance(item, dict) and item.get("type") == "tool_result" and item.get("is_error"):
                        tool_name = item.get("tool_name", "Unknown")
                        error_text = item.get("content", "")
                        ts = event["timestamp"]

                        try:
                            dt = parse_timestamp(ts)
                            date = dt.strftime('%Y-%m-%d')
                            time_str = dt.strftime('%H:%M:%S')
                        except (ValueError, AttributeError):
                            date = "unknown"
                            time_str = "unknown"

                        error_cat, _ = classify_error(error_text)

                        failed_by_date[date].append(FailedCall(
                            timestamp=ts,
                            date=date,
                            time=time_str,
                            tool_name=tool_name,
                            session=session_id,
                            project=project,
                            error_text=error_text[:300],
                            error_type=error_cat.value,
                        ))

        except Exception as e:
            print(f"Error processing {file_path}: {e}", file=sys.stderr)

    return dict(failed_by_date)


def generate_daily_report(date: str, failures: List[FailedCall], output_file: Path) -> None:
    lines = []

    lines.append(f"# Failed Tool Calls — {date}")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    total_failures = len(failures)
    by_tool = defaultdict(int)
    by_error_type = defaultdict(int)
    by_project = defaultdict(int)

    for failure in failures:
        by_tool[failure.tool_name] += 1
        by_error_type[failure.error_type] += 1
        by_project[failure.project] += 1

    lines.append("## Summary")
    lines.append("")
    lines.append(f"**Total Failures**: {total_failures}")
    lines.append(f"**Affected Projects**: {len(by_project)}")
    lines.append(f"**Affected Tools**: {len(by_tool)}")
    lines.append("")

    lines.append("### By Tool")
    for tool, count in sorted(by_tool.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {tool}: {count}")
    lines.append("")

    lines.append("### By Error Type")
    for error_type, count in sorted(by_error_type.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {error_type.replace('_', ' ').title()}: {count}")
    lines.append("")

    # Failures grouped by project
    lines.append("## Failures by Project")
    lines.append("")

    by_proj = defaultdict(list)
    for failure in failures:
        by_proj[failure.project].append(failure)

    for project in sorted(by_proj.keys()):
        project_failures = sorted(by_proj[project], key=lambda x: x.time)
        lines.append(f"### {project}")
        lines.append(f"**Total**: {len(project_failures)} failures")
        lines.append("")

        lines.append("| Time | Tool | Error Type | Session |")
        lines.append("|------|------|-----------|---------|")

        for failure in project_failures:
            session_short = failure.session[:8]
            lines.append(
                f"| {failure.time} | {failure.tool_name} | {failure.error_type} | {session_short} |"
            )
        lines.append("")

        lines.append("**Error Samples**:")
        lines.append("")
        for i, failure in enumerate(project_failures[:5], 1):
            lines.append(f"**{i}. {failure.tool_name} at {failure.time}** ({failure.error_type})")
            lines.append("")
            lines.append("```")
            lines.append(failure.error_text.replace("```", "~~~"))
            lines.append("```")
            lines.append("")

        lines.append("---")
        lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Created: {output_file} ({total_failures} failures)")


def generate_html_report(date: str, failures: List[FailedCall], output_file: Path) -> None:
    """Generate a standalone HTML report for daily failed tool calls."""
    total_failures = len(failures)
    by_tool: dict = defaultdict(int)
    by_error_type: dict = defaultdict(int)
    by_project: dict = defaultdict(list)

    for failure in failures:
        by_tool[failure.tool_name] += 1
        by_error_type[failure.error_type] += 1
        by_project[failure.project].append(failure)

    max_tool_count = max(by_tool.values()) if by_tool else 1
    max_err_count = max(by_error_type.values()) if by_error_type else 1

    # By Tool bar chart
    tool_bars = ""
    for tool, count in sorted(by_tool.items(), key=lambda x: x[1], reverse=True):
        bar_pct = (count / max_tool_count * 100)
        tool_bars += f"""<div class="bar-row">
  <div class="bar-label">{html_mod.escape(tool)}</div>
  <div class="bar-track"><div class="bar-fill" style="width:{bar_pct:.1f}%"></div></div>
  <div class="bar-count">{count}</div>
</div>
"""

    # By Error Type bar chart
    err_bars = ""
    for error_type, count in sorted(by_error_type.items(), key=lambda x: x[1], reverse=True):
        bar_pct = (count / max_err_count * 100)
        label = html_mod.escape(error_type.replace("_", " ").title())
        err_bars += f"""<div class="bar-row">
  <div class="bar-label">{label}</div>
  <div class="bar-track"><div class="bar-fill" style="width:{bar_pct:.1f}%"></div></div>
  <div class="bar-count">{count}</div>
</div>
"""

    # Per-project collapsible sections
    project_sections = ""
    for project in sorted(by_project.keys()):
        project_failures = sorted(by_project[project], key=lambda x: x.time)
        table_rows = ""
        for f in project_failures:
            table_rows += (
                f"<tr>"
                f"<td>{html_mod.escape(f.time)}</td>"
                f"<td>{html_mod.escape(f.tool_name)}</td>"
                f"<td>{html_mod.escape(f.error_type)}</td>"
                f"<td>{html_mod.escape(f.session[:8])}</td>"
                f"</tr>\n"
            )
        samples_html = ""
        for i, f in enumerate(project_failures[:5], 1):
            samples_html += (
                f"<p class='sample-header'>{i}. {html_mod.escape(f.tool_name)} at {html_mod.escape(f.time)} "
                f"({html_mod.escape(f.error_type)})</p>"
                f"<pre>{html_mod.escape(f.error_text)}</pre>"
            )
        project_sections += f"""<details>
<summary>{html_mod.escape(project)} <span class="badge">{len(project_failures)} failures</span></summary>
<div class="detail-body">
  <table>
  <thead><tr><th>Time</th><th>Tool</th><th>Error Type</th><th>Session</th></tr></thead>
  <tbody>{table_rows}</tbody>
  </table>
  <h4>Error Samples</h4>
  {samples_html}
</div>
</details>
"""

    from claude_history.html_theme import get_base_css
    base_css = get_base_css()

    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Failed Tool Calls &mdash; {html_mod.escape(date)}</title>
<style>
{base_css}
  body {{ font-size: 14px; padding: 24px; }}
  h1 {{ color: var(--accent); margin-bottom: 8px; font-size: 1.6em; }}
  .subtitle {{ color: var(--text2); margin-bottom: 24px; font-size: 0.9em; }}
  h2 {{ color: var(--accent); margin: 32px 0 12px; font-size: 1.2em; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  h4 {{ color: var(--text2); margin: 12px 0 6px; font-size: 0.95em; }}
  .stats {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
  .detail-body {{ padding: 12px 16px; }}
  .detail-body > table {{ border-radius: 0; }}
  .badge {{
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 12px; padding: 2px 8px; font-size: 0.8em;
    color: var(--text2); font-weight: normal;
  }}
  .sample-header {{ color: var(--text2); font-size: 0.85em; margin-bottom: 4px; }}
  .bar-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
  .bar-label {{ width: 180px; color: var(--text2); font-size: 13px; flex-shrink: 0; }}
  .bar-track {{ flex: 1; background: var(--surface2); border-radius: 4px; height: 16px; border: 1px solid var(--border); }}
  .bar-fill {{ background: var(--accent2); border-radius: 4px; height: 100%; min-width: 2px; }}
  .bar-count {{ width: 60px; color: var(--text2); font-size: 12px; flex-shrink: 0; }}
</style>
</head>
<body>
<h1>Failed Tool Calls &mdash; {html_mod.escape(date)}</h1>
<p class="subtitle">Generated: {html_mod.escape(gen_time)}</p>

<div class="stats">
  <div class="stat-card"><div class="value">{total_failures}</div><div class="label">Total Failures</div></div>
  <div class="stat-card"><div class="value">{len(by_project)}</div><div class="label">Projects</div></div>
  <div class="stat-card"><div class="value">{len(by_tool)}</div><div class="label">Tools</div></div>
</div>

<h2>By Tool</h2>
<div class="bar-chart">
{tool_bars if tool_bars else "<p style='color:var(--text2)'>No data.</p>"}
</div>

<h2>By Error Type</h2>
<div class="bar-chart">
{err_bars if err_bars else "<p style='color:var(--text2)'>No data.</p>"}
</div>

<h2>Failures by Project</h2>
{project_sections if project_sections else "<p style='color:var(--text2)'>No failures.</p>"}

</body>
</html>"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Created: {output_file} ({total_failures} failures, HTML)")

