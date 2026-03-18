#!/usr/bin/env python3
"""
Claude History Analyzer

Reads through Claude Code history files (JSONL format) to detect:
- Tool call errors (D1)
- Permission denials (D2)
- Repeated retries (D3)
- Suboptimal tool usage patterns (D4)

Generates a markdown report with findings and guidelines.

Invoked via: python tools/cli.py analyze
"""

import html as html_mod
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional, List, Dict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_history.errors import classify_error
from claude_history.parsing import find_history_files, iter_session_events

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

PERMISSION_PATTERNS = re.compile(
    r"permission|denied|not allowed|allowlist|requires approval", re.I
)
SUBOPTIMAL_BASH = re.compile(r"^\s*(grep|rg|cat|head|tail|find|ls)\s")
RETRY_WINDOW = 5
RETRY_THRESHOLD = 3


@dataclass
class Finding:
    tool_name: str
    error_type: Optional[str]
    snippet: str
    project: str
    session: str
    timestamp: str


@dataclass
class RetryFinding:
    tool_name: str
    consecutive_calls: int
    session: str
    timestamp: str


@dataclass
class SuboptimalFinding:
    command_prefix: str
    full_command: str
    project: str
    session: str
    timestamp: str


@dataclass
class AnalysisResults:
    tool_errors: List[Finding] = field(default_factory=list)
    perm_denials: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    retries: List[RetryFinding] = field(default_factory=list)
    suboptimal: List[SuboptimalFinding] = field(default_factory=list)
    sessions_scanned: int = 0
    projects_scanned: set = field(default_factory=set)
    total_size_mb: float = 0.0


def classify_error_type(error_text: str) -> str:
    """Classify error using the shared ErrorCategory enum, returning a string."""
    category, _ = classify_error(error_text)
    return category.value


def parse_session_file(file_path: Path, results: AnalysisResults) -> None:
    """Parse a single session file using shared parsing."""
    session_id = file_path.stem
    project = file_path.parent.name
    results.projects_scanned.add(project)
    results.sessions_scanned += 1
    results.total_size_mb += file_path.stat().st_size / (1024 * 1024)

    session_tools = defaultdict(list)

    try:
        for event in iter_session_events(file_path):
            timestamp = event["timestamp"]

            if event["type"] == "assistant":
                for item in event["content"]:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        tool_name = item.get("name", "")
                        tool_use_id = item.get("id", "")

                        session_tools[tool_name].append({
                            "tool_use_id": tool_use_id,
                            "timestamp": timestamp,
                        })

                        # D4: Suboptimal bash usage
                        if tool_name == "Bash":
                            command = item.get("input", {}).get("command", "")
                            cmd_match = SUBOPTIMAL_BASH.match(command)
                            if cmd_match:
                                results.suboptimal.append(SuboptimalFinding(
                                    command_prefix=cmd_match.group(1),
                                    full_command=command[:100],
                                    project=project,
                                    session=session_id,
                                    timestamp=timestamp,
                                ))

            elif event["type"] == "user":
                for item in event["content"]:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        tool_name = item.get("tool_name", "Unknown")
                        content_text = item.get("content", "")

                        # D1: Tool call errors
                        if item.get("is_error"):
                            error_text = content_text[:200]
                            results.tool_errors.append(Finding(
                                tool_name=tool_name,
                                error_type=classify_error_type(error_text),
                                snippet=error_text,
                                project=project,
                                session=session_id,
                                timestamp=timestamp,
                            ))

                        # D2: Permission denials
                        if PERMISSION_PATTERNS.search(str(content_text)):
                            results.perm_denials[tool_name] += 1

        # D3: Detect retries
        for tool_name, calls in session_tools.items():
            if len(calls) >= RETRY_THRESHOLD:
                for i in range(len(calls) - RETRY_THRESHOLD + 1):
                    window = calls[i:i + RETRY_THRESHOLD]
                    if len(window) >= RETRY_THRESHOLD:
                        results.retries.append(RetryFinding(
                            tool_name=tool_name,
                            consecutive_calls=len(window),
                            session=session_id,
                            timestamp=window[0]["timestamp"],
                        ))
                        break

    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)


def scan_history(projects_dir: Path, results: AnalysisResults) -> None:
    history_files = find_history_files(projects_dir)
    print(f"Scanning {len(history_files)} session files...", file=sys.stderr)

    for i, file_path in enumerate(history_files, 1):
        if i % 10 == 0:
            print(f"  Processing {i}/{len(history_files)}...", file=sys.stderr)
        parse_session_file(file_path, results)


def generate_summary_table(results: AnalysisResults) -> List[str]:
    lines = []
    lines.append(f"Claude History Analysis - {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(
        f"Scanned {results.sessions_scanned} sessions across {len(results.projects_scanned)} projects ({results.total_size_mb:.0f} MB)"
    )
    lines.append("")
    lines.append("Category              | Count | Top Offender")
    lines.append("---------------------+-------+---------------------")

    error_count = len(results.tool_errors)
    top_error_tool = "-"
    if results.tool_errors:
        tool_counts = defaultdict(int)
        for finding in results.tool_errors:
            tool_counts[finding.tool_name] += 1
        top_error_tool = max(tool_counts, key=tool_counts.get)
        if results.tool_errors[0].error_type:
            top_error_tool += f" ({results.tool_errors[0].error_type})"
    lines.append(f"Tool call errors      | {error_count:>5} | {top_error_tool}")

    perm_count = sum(results.perm_denials.values())
    top_perm_tool = max(results.perm_denials, key=results.perm_denials.get) if results.perm_denials else "-"
    lines.append(f"Permission denials    | {perm_count:>5} | {top_perm_tool}")

    retry_count = len(results.retries)
    top_retry_tool = "-"
    if results.retries:
        tool_counts = defaultdict(int)
        for finding in results.retries:
            tool_counts[finding.tool_name] += 1
        top_retry_tool = max(tool_counts, key=tool_counts.get)
    lines.append(f"Repeated retries      | {retry_count:>5} | {top_retry_tool}")

    subopt_count = len(results.suboptimal)
    top_subopt_cmd = "-"
    if results.suboptimal:
        cmd_counts = defaultdict(int)
        for finding in results.suboptimal:
            cmd_counts[finding.command_prefix] += 1
        top_subopt_cmd = f"Bash ({max(cmd_counts, key=cmd_counts.get)})"
    lines.append(f"Suboptimal tool use   | {subopt_count:>5} | {top_subopt_cmd}")

    return lines


def generate_markdown_report(results: AnalysisResults, output_file: Path) -> None:
    lines = []

    lines.append(f"# Claude History Analysis — {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    summary = generate_summary_table(results)
    lines.extend(summary)
    lines.append("")
    lines.append("")

    # D1: Tool Call Errors
    lines.append("## D1: Tool Call Errors")
    lines.append("")

    if results.tool_errors:
        errors_by_type = defaultdict(list)
        for finding in results.tool_errors:
            errors_by_type[finding.error_type or "other"].append(finding)

        for error_type in sorted(errors_by_type.keys()):
            lines.append(f"### {error_type.replace('_', ' ').title()}")
            lines.append("")
            lines.append("| Tool | Snippet | Project | Session |")
            lines.append("|------|---------|---------|---------|")

            for finding in errors_by_type[error_type][:10]:
                snippet = finding.snippet.replace("|", "\\|")[:60]
                lines.append(
                    f"| {finding.tool_name} | {snippet} | {finding.project} | {finding.session[:8]} |"
                )
            lines.append("")
    else:
        lines.append("No tool call errors detected.")
        lines.append("")

    lines.append("### Guidelines")
    lines.append("")
    if results.tool_errors:
        lines.append("- Review error patterns to identify systematic issues with tool usage")
        lines.append("- Check exit code errors — may indicate incorrect command syntax")
        lines.append("- Token limit errors suggest breaking large operations into smaller steps")
        lines.append("- Validation errors indicate incorrect input formats for tool parameters")
    else:
        lines.append("- No errors found — tool usage patterns are healthy")
    lines.append("")
    lines.append("")

    # D2: Permission Denials
    lines.append("## D2: Permission Denials")
    lines.append("")

    if results.perm_denials:
        lines.append("| Tool | Times Denied |")
        lines.append("|------|------|")
        for tool, count in sorted(results.perm_denials.items(), key=lambda x: x[1], reverse=True)[:10]:
            lines.append(f"| {tool} | {count} |")
        lines.append("")
        lines.append("### Suggested settings.json Additions")
        lines.append("")
        lines.append("```json")
        lines.append("{")
        lines.append('  "permissions": {')
        lines.append('    "allow": [')
        for tool, count in sorted(results.perm_denials.items(), key=lambda x: x[1], reverse=True)[:5]:
            if tool != "Unknown":
                lines.append(f'      "{tool}",')
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append("    ]")
        lines.append("  }")
        lines.append("}")
        lines.append("```")
    else:
        lines.append("No permission denials detected.")
    lines.append("")

    lines.append("### Guidelines")
    lines.append("")
    if results.perm_denials:
        lines.append("- Most frequently denied tools should be reviewed for settings.json permissions")
        lines.append("- Consider allowing tool usage globally if it's frequently needed")
        lines.append("- Use per-project settings.json overrides for tool-specific permissions")
    else:
        lines.append("- Permission settings are well-tuned")
    lines.append("")
    lines.append("")

    # D3: Repeated Retries
    lines.append("## D3: Repeated Retries")
    lines.append("")

    if results.retries:
        lines.append("| Tool | Consecutive Calls | Session |")
        lines.append("|------|------|------|")
        for finding in results.retries[:10]:
            lines.append(f"| {finding.tool_name} | {finding.consecutive_calls} | {finding.session[:8]} |")
        lines.append("")
    else:
        lines.append("No repeated retry patterns detected.")
        lines.append("")

    lines.append("### Guidelines")
    lines.append("")
    if results.retries:
        lines.append("- Repeated tool calls in quick succession may indicate debugging loops")
        lines.append("- Consider breaking complex tasks into smaller, well-defined steps")
        lines.append("- Analyze why retries are happening — file not found, command error, etc.")
        lines.append("- Use better error handling before retrying (e.g., check file existence first)")
    else:
        lines.append("- Tool retry patterns are efficient — tasks complete on first attempt")
    lines.append("")
    lines.append("")

    # D4: Suboptimal Tool Use
    lines.append("## D4: Suboptimal Tool Use")
    lines.append("")

    if results.suboptimal:
        lines.append("| Command | Full Command | Project | Session |")
        lines.append("|---------|------|---------|---------|")
        for finding in results.suboptimal[:10]:
            cmd = finding.full_command.replace("|", "\\|")
            lines.append(f"| {finding.command_prefix} | {cmd} | {finding.project} | {finding.session[:8]} |")
        lines.append("")
    else:
        lines.append("No suboptimal tool usage patterns detected.")
        lines.append("")

    lines.append("### Guidelines")
    lines.append("")
    if results.suboptimal:
        lines.append("- **grep/rg**: Use `Grep` tool instead of Bash for file content search")
        lines.append("- **find**: Use `Glob` tool instead of Bash for file discovery")
        lines.append("- **cat/head/tail**: Use `Read` tool instead of Bash to read files")
        lines.append("- **ls**: Use `Glob` or Read tool for directory exploration")
        lines.append("- Dedicated tools provide better formatting and user experience")
    else:
        lines.append("- Tool usage patterns are optimal — using dedicated tools appropriately")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_html_report(results: AnalysisResults, output_file: Path) -> None:
    """Generate a standalone HTML report for analysis results."""
    error_count = len(results.tool_errors)
    perm_count = sum(results.perm_denials.values())
    retry_count = len(results.retries)
    subopt_count = len(results.suboptimal)

    # D1: errors grouped by type
    errors_by_type: dict = defaultdict(list)
    for finding in results.tool_errors:
        errors_by_type[finding.error_type or "other"].append(finding)

    d1_html = ""
    for error_type in sorted(errors_by_type.keys()):
        label = html_mod.escape(error_type.replace("_", " ").title())
        group = errors_by_type[error_type]
        rows = ""
        for f in group[:20]:
            rows += (
                f"<tr>"
                f"<td>{html_mod.escape(f.tool_name)}</td>"
                f"<td><code>{html_mod.escape(f.snippet[:80])}</code></td>"
                f"<td>{html_mod.escape(f.project)}</td>"
                f"<td>{html_mod.escape(f.session[:8])}</td>"
                f"</tr>\n"
            )
        d1_html += f"""<details>
<summary>{label} <span class="badge">{len(group)}</span></summary>
<table>
<thead><tr><th>Tool</th><th>Snippet</th><th>Project</th><th>Session</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</details>
"""

    # D2: permission denials
    d2_rows = ""
    for tool, count in sorted(results.perm_denials.items(), key=lambda x: x[1], reverse=True):
        d2_rows += f"<tr><td>{html_mod.escape(tool)}</td><td>{count}</td></tr>\n"
    d2_html = (
        f"<table><thead><tr><th>Tool</th><th>Times Denied</th></tr></thead>"
        f"<tbody>{d2_rows}</tbody></table>"
        if d2_rows else "<p class='empty'>No permission denials detected.</p>"
    )

    # D3: retries
    d3_rows = ""
    for f in results.retries[:30]:
        d3_rows += (
            f"<tr><td>{html_mod.escape(f.tool_name)}</td>"
            f"<td>{f.consecutive_calls}</td>"
            f"<td>{html_mod.escape(f.session[:8])}</td></tr>\n"
        )
    d3_html = (
        f"<table><thead><tr><th>Tool</th><th>Consecutive Calls</th><th>Session</th></tr></thead>"
        f"<tbody>{d3_rows}</tbody></table>"
        if d3_rows else "<p class='empty'>No repeated retry patterns detected.</p>"
    )

    # D4: suboptimal usage
    d4_rows = ""
    for f in results.suboptimal[:30]:
        d4_rows += (
            f"<tr><td>{html_mod.escape(f.command_prefix)}</td>"
            f"<td><code>{html_mod.escape(f.full_command)}</code></td>"
            f"<td>{html_mod.escape(f.project)}</td>"
            f"<td>{html_mod.escape(f.session[:8])}</td></tr>\n"
        )
    d4_html = (
        f"<table><thead><tr><th>Command</th><th>Full Command</th><th>Project</th><th>Session</th></tr></thead>"
        f"<tbody>{d4_rows}</tbody></table>"
        if d4_rows else "<p class='empty'>No suboptimal tool usage patterns detected.</p>"
    )

    date_str = datetime.now().strftime("%Y-%m-%d")
    projects_count = len(results.projects_scanned)
    size_str = f"{results.total_size_mb:.0f} MB"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude History Analysis</title>
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --surface2: #1c2129; --border: #30363d;
    --text: #e6edf3; --text2: #8b949e; --accent: #58a6ff; --accent2: #388bfd;
    --green: #3fb950; --red: #f85149; --orange: #d29922; --purple: #bc8cff;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
    font-size: 14px; padding: 24px;
  }}
  h1 {{ color: var(--accent); margin-bottom: 8px; font-size: 1.6em; }}
  .subtitle {{ color: var(--text2); margin-bottom: 24px; font-size: 0.9em; }}
  h2 {{ color: var(--accent); margin: 32px 0 12px; font-size: 1.2em; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  .stats {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
  .stat-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px 24px; min-width: 140px; text-align: center;
  }}
  .stat-card .value {{ font-size: 1.8em; font-weight: bold; color: var(--accent); }}
  .stat-card .label {{ color: var(--text2); font-size: 0.85em; margin-top: 4px; }}
  .controls {{ margin-bottom: 16px; }}
  #filter {{
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text); padding: 8px 12px; border-radius: 6px;
    font-size: 14px; width: 300px;
  }}
  #filter::placeholder {{ color: var(--text2); }}
  table {{
    width: 100%; border-collapse: collapse; background: var(--surface);
    border-radius: 8px; overflow: hidden; border: 1px solid var(--border);
    margin-bottom: 16px;
  }}
  thead {{ background: var(--surface2); }}
  th {{
    padding: 10px 14px; text-align: left; color: var(--text2);
    font-weight: 600; border-bottom: 1px solid var(--border); white-space: nowrap;
  }}
  td {{
    padding: 8px 14px; border-bottom: 1px solid var(--border);
    color: var(--text); font-size: 13px;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(88,166,255,0.05); }}
  code {{
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 3px; padding: 1px 5px; font-size: 12px;
    color: var(--orange); word-break: break-all;
  }}
  details {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; margin-bottom: 10px; overflow: hidden;
  }}
  details > summary {{
    padding: 10px 16px; cursor: pointer; color: var(--text);
    font-weight: 600; user-select: none; list-style: none;
    display: flex; align-items: center; gap: 8px;
  }}
  details > summary::-webkit-details-marker {{ display: none; }}
  details > summary::before {{ content: '▶'; color: var(--text2); font-size: 0.7em; }}
  details[open] > summary::before {{ content: '▼'; }}
  details > table {{ border-radius: 0; border: none; border-top: 1px solid var(--border); margin-bottom: 0; }}
  .badge {{
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 12px; padding: 2px 8px; font-size: 0.8em;
    color: var(--text2); font-weight: normal;
  }}
  .empty {{ color: var(--text2); padding: 12px; font-style: italic; }}
  .hidden {{ display: none; }}
</style>
</head>
<body>
<h1>Claude History Analysis</h1>
<p class="subtitle">{date_str} &mdash; {results.sessions_scanned} sessions across {projects_count} projects ({size_str})</p>

<div class="stats">
  <div class="stat-card"><div class="value">{error_count}</div><div class="label">Tool Errors</div></div>
  <div class="stat-card"><div class="value">{perm_count}</div><div class="label">Permission Denials</div></div>
  <div class="stat-card"><div class="value">{retry_count}</div><div class="label">Retries</div></div>
  <div class="stat-card"><div class="value">{subopt_count}</div><div class="label">Suboptimal Usage</div></div>
</div>

<div class="controls">
  <input id="filter" type="text" placeholder="Filter table rows..." oninput="filterAll()">
</div>

<h2>D1: Tool Call Errors</h2>
{d1_html if d1_html else "<p class='empty'>No tool call errors detected.</p>"}

<h2>D2: Permission Denials</h2>
{d2_html}

<h2>D3: Repeated Retries</h2>
{d3_html}

<h2>D4: Suboptimal Tool Use</h2>
{d4_html}

<script>
window.filterAll = function() {{
  var q = document.getElementById('filter').value.toLowerCase();
  document.querySelectorAll('table tbody tr').forEach(function(tr) {{
    tr.classList.toggle('hidden', q ? !tr.textContent.toLowerCase().includes(q) : false);
  }});
}};
</script>
</body>
</html>"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

