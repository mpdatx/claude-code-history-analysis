#!/usr/bin/env python3
"""
Claude Tool Failures - Deep Analysis

Comprehensive analysis of tool call errors, failures, and error patterns
to identify systematic issues and improvement opportunities.

Invoked via: python tools/cli.py failures
"""

import html as html_mod
import sys
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional, List, Dict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_history.errors import ErrorCategory, classify_error
from claude_history.parsing import find_history_files, iter_session_events


@dataclass
class ToolError:
    tool_name: str
    error_category: ErrorCategory
    error_text: str
    full_error: str
    project: str
    session: str
    timestamp: str
    exit_code: Optional[int] = None


@dataclass
class ToolStats:
    tool_name: str
    total_errors: int = 0
    by_category: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    projects_affected: set = field(default_factory=set)
    sessions_affected: set = field(default_factory=set)
    first_error: str = ""
    last_error: str = ""
    error_samples: List[ToolError] = field(default_factory=list)


def scan_history_files(projects_dir: Path, recent_days=None) -> List[ToolError]:
    history_files = find_history_files(projects_dir, recent_days=recent_days)
    if not history_files:
        print(f"Error: no history files found in {projects_dir}", file=sys.stderr)
        return []

    print(f"Scanning {len(history_files)} session files for tool failures...", file=sys.stderr)

    all_errors = []

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
                        error_cat, exit_code = classify_error(error_text)

                        all_errors.append(ToolError(
                            tool_name=tool_name,
                            error_category=error_cat,
                            error_text=error_text[:300],
                            full_error=error_text[:1000],
                            project=project,
                            session=session_id,
                            timestamp=event["timestamp"],
                            exit_code=exit_code,
                        ))

        except Exception as e:
            print(f"Error processing {file_path}: {e}", file=sys.stderr)

    return all_errors


def compute_tool_stats(errors: List[ToolError]) -> Dict[str, ToolStats]:
    stats = {}
    for error in errors:
        tool = error.tool_name
        if tool not in stats:
            stats[tool] = ToolStats(tool_name=tool)

        tool_stat = stats[tool]
        tool_stat.total_errors += 1
        tool_stat.by_category[error.error_category.value] += 1
        tool_stat.projects_affected.add(error.project)
        tool_stat.sessions_affected.add(error.session)

        if not tool_stat.first_error:
            tool_stat.first_error = error.timestamp
        tool_stat.last_error = error.timestamp

        if len(tool_stat.error_samples) < 5:
            tool_stat.error_samples.append(error)

    return stats


def generate_detailed_report(
    errors: List[ToolError],
    stats: Dict[str, ToolStats],
    output_file: Path,
) -> None:
    lines = []

    lines.append(f"# Claude Tool Failures - Deep Analysis")
    lines.append(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- **Total Errors Found**: {len(errors)}")
    lines.append(f"- **Tools Affected**: {len(stats)}")
    lines.append(f"- **Unique Projects**: {len(set(e.project for e in errors))}")
    lines.append(f"- **Unique Sessions**: {len(set(e.session for e in errors))}")
    lines.append("")

    sorted_tools = sorted(stats.items(), key=lambda x: x[1].total_errors, reverse=True)
    lines.append("## Top Offending Tools")
    lines.append("")
    lines.append("| Tool | Errors | Projects | Sessions |")
    lines.append("|------|--------|----------|----------|")
    for tool_name, tool_stat in sorted_tools[:15]:
        lines.append(
            f"| {tool_name} | {tool_stat.total_errors} | {len(tool_stat.projects_affected)} | {len(tool_stat.sessions_affected)} |"
        )
    lines.append("")

    # Error distribution by category
    lines.append("## Error Distribution by Category")
    lines.append("")
    category_counts = defaultdict(int)
    for error in errors:
        category_counts[error.error_category.value] += 1

    lines.append("| Category | Count | Percentage |")
    lines.append("|----------|-------|-----------|")
    for cat in sorted(category_counts.keys()):
        count = category_counts[cat]
        pct = (count / len(errors) * 100) if errors else 0
        lines.append(f"| {cat.replace('_', ' ').title()} | {count} | {pct:.1f}% |")
    lines.append("")

    # Detailed per-tool analysis
    lines.append("## Detailed Analysis by Tool")
    lines.append("")

    for tool_name, tool_stat in sorted_tools[:20]:
        lines.append(f"### {tool_name}")
        lines.append("")
        lines.append(f"**Total Errors**: {tool_stat.total_errors}")
        lines.append(f"**Projects Affected**: {len(tool_stat.projects_affected)}")
        lines.append(f"**Sessions Affected**: {len(tool_stat.sessions_affected)}")
        lines.append(f"**Error Range**: {tool_stat.first_error} to {tool_stat.last_error}")
        lines.append("")

        lines.append("**Error Types**:")
        lines.append("")
        lines.append("| Type | Count |")
        lines.append("|------|-------|")
        for cat in sorted(tool_stat.by_category.keys()):
            count = tool_stat.by_category[cat]
            lines.append(f"| {cat.replace('_', ' ').title()} | {count} |")
        lines.append("")

        if tool_stat.error_samples:
            lines.append("**Recent Error Examples**:")
            lines.append("")
            for i, sample in enumerate(tool_stat.error_samples[:3], 1):
                lines.append(f"**Example {i}** (Project: {sample.project})")
                lines.append("")
                lines.append("```")
                lines.append(sample.error_text.replace("```", "~~~"))
                lines.append("```")
                lines.append("")

        if tool_name == "Bash":
            bash_errors = [e for e in errors if e.tool_name == "Bash" and e.exit_code is not None]
            if bash_errors:
                exit_codes = defaultdict(int)
                for error in bash_errors:
                    exit_codes[error.exit_code] += 1
                lines.append("**Exit Code Distribution**:")
                lines.append("")
                for code in sorted(exit_codes.keys()):
                    lines.append(f"- Exit code {code}: {exit_codes[code]} occurrences")
                lines.append("")

        lines.append("---")
        lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")

    for tool_name, tool_stat in sorted_tools[:10]:
        if tool_stat.total_errors > 10:
            lines.append(f"### {tool_name} ({tool_stat.total_errors} errors)")
            lines.append("")

            if tool_name == "Bash":
                lines.append("- Consider breaking complex shell commands into multiple smaller commands")
                lines.append("- Add error checking with `set -e` or explicit `||` handlers")
                exit_code_count = tool_stat.by_category.get('exit_code', 0)
                if exit_code_count:
                    lines.append(f"- Exit code errors: {exit_code_count} occurrences (most common category)")
                lines.append("- Review PATH and environment variable setup at session start")
            elif tool_name == "Read":
                lines.append("- Token limit errors suggest files are too large — use limit/offset parameters")
                lines.append("- Verify file paths are correct before attempting to read")
                lines.append("- Consider reading file in sections for large files")
            elif tool_name == "Grep":
                lines.append("- Ensure regex patterns are correctly escaped")
                lines.append("- Use simpler patterns first to verify they work")
                lines.append("- Check file encoding if searching fails")
            elif tool_name == "Write":
                lines.append("- Ensure parent directories exist before writing")
                lines.append("- Use Read first if editing — verify file exists and structure")
                lines.append("- Check file permissions and disk space")
            elif tool_name == "Edit":
                lines.append("- Verify old_string matches exactly (including indentation)")
                lines.append("- Use Read first to check actual indentation in file")
                lines.append("- Make sure old_string is unique or use replace_all parameter")
            elif tool_name == "Glob":
                lines.append("- Patterns must use forward slashes even on Windows")
                lines.append("- Verify path exists before globbing")
                lines.append("- Consider permission issues if glob returns no results")
            elif tool_name == "Agent":
                lines.append("- Check that subagent type is valid (Explore, Plan, general-purpose)")
                lines.append("- Ensure prompt is clear and specific")
                lines.append("- Review agent isolation requirements")
            else:
                most_common_cat = max(tool_stat.by_category.items(), key=lambda x: x[1])[0]
                lines.append(f"- Most common error type: {most_common_cat}")
                lines.append("- Review tool documentation for typical error causes")
                lines.append(f"- Affects {len(tool_stat.projects_affected)} projects — may be systemic")
            lines.append("")

    # Common error patterns
    lines.append("## Common Error Patterns")
    lines.append("")
    error_patterns = defaultdict(int)
    for error in errors:
        pattern = " ".join(error.error_text.split()[:3])
        error_patterns[pattern] += 1

    lines.append("**Most Frequently Occurring Error Messages**:")
    lines.append("")
    for pattern, count in sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)[:20]:
        if count >= 3:
            lines.append(f"- \"{pattern}...\" — {count} occurrences")
    lines.append("")

    # Statistics
    lines.append("## Error Statistics")
    lines.append("")
    errors_by_project = defaultdict(int)
    for error in errors:
        errors_by_project[error.project] += 1

    lines.append("**Projects with Most Errors**:")
    lines.append("")
    for project, count in sorted(errors_by_project.items(), key=lambda x: x[1], reverse=True)[:15]:
        lines.append(f"- {project}: {count} errors")
    lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_html_report(
    errors: List[ToolError],
    stats: Dict[str, ToolStats],
    output_file: Path,
) -> None:
    """Generate a standalone HTML report for deep failure analysis."""
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_errors = len(errors)
    unique_projects = len(set(e.project for e in errors))
    unique_sessions = len(set(e.session for e in errors))

    sorted_tools = sorted(stats.items(), key=lambda x: x[1].total_errors, reverse=True)

    # Top offending tools table
    top_tools_rows = ""
    for tool_name, ts in sorted_tools[:15]:
        top_tools_rows += (
            f"<tr>"
            f"<td>{html_mod.escape(tool_name)}</td>"
            f"<td>{ts.total_errors}</td>"
            f"<td>{len(ts.projects_affected)}</td>"
            f"<td>{len(ts.sessions_affected)}</td>"
            f"</tr>\n"
        )

    # Error distribution by category (horizontal bar chart)
    category_counts: dict = defaultdict(int)
    for error in errors:
        category_counts[error.error_category.value] += 1
    max_cat_count = max(category_counts.values()) if category_counts else 1

    cat_bars = ""
    for cat in sorted(category_counts.keys()):
        count = category_counts[cat]
        pct = (count / total_errors * 100) if total_errors else 0
        bar_pct = (count / max_cat_count * 100)
        label = html_mod.escape(cat.replace("_", " ").title())
        cat_bars += f"""<div class="bar-row">
  <div class="bar-label">{label}</div>
  <div class="bar-track"><div class="bar-fill" style="width:{bar_pct:.1f}%"></div></div>
  <div class="bar-count">{count} ({pct:.1f}%)</div>
</div>
"""

    # Per-tool detail sections
    tool_sections = ""
    for tool_name, ts in sorted_tools[:20]:
        cat_rows = ""
        for cat in sorted(ts.by_category.keys()):
            count = ts.by_category[cat]
            cat_rows += f"<tr><td>{html_mod.escape(cat.replace('_', ' ').title())}</td><td>{count}</td></tr>\n"

        samples_html = ""
        for i, sample in enumerate(ts.error_samples[:3], 1):
            samples_html += (
                f"<p class='sample-header'>Example {i} (Project: {html_mod.escape(sample.project)})</p>"
                f"<pre>{html_mod.escape(sample.error_text)}</pre>"
            )

        tool_sections += f"""<details>
<summary>{html_mod.escape(tool_name)} <span class="badge">{ts.total_errors} errors</span></summary>
<div class="detail-body">
  <div class="meta-row">
    <span>Projects: <strong>{len(ts.projects_affected)}</strong></span>
    <span>Sessions: <strong>{len(ts.sessions_affected)}</strong></span>
  </div>
  <h4>Error Types</h4>
  <table><thead><tr><th>Type</th><th>Count</th></tr></thead><tbody>{cat_rows}</tbody></table>
  <h4>Error Samples</h4>
  {samples_html}
</div>
</details>
"""

    # Common error patterns
    error_patterns: dict = defaultdict(int)
    for error in errors:
        pattern = " ".join(error.error_text.split()[:3])
        error_patterns[pattern] += 1
    pattern_items = ""
    for pattern, count in sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)[:20]:
        if count >= 3:
            pattern_items += f"<li><code>{html_mod.escape(pattern)}...</code> &mdash; {count} occurrences</li>\n"

    # Projects with most errors
    errors_by_project: dict = defaultdict(int)
    for error in errors:
        errors_by_project[error.project] += 1
    project_items = ""
    for project, count in sorted(errors_by_project.items(), key=lambda x: x[1], reverse=True)[:15]:
        project_items += f"<li>{html_mod.escape(project)}: {count} errors</li>\n"

    from claude_history.html_theme import get_base_css
    base_css = get_base_css()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Tool Failures — Deep Analysis</title>
<style>
{base_css}
  body {{ font-size: 14px; padding: 24px; }}
  h1 {{ color: var(--accent); margin-bottom: 8px; font-size: 1.6em; }}
  .subtitle {{ color: var(--text2); margin-bottom: 24px; font-size: 0.9em; }}
  h2 {{ color: var(--accent); margin: 32px 0 12px; font-size: 1.2em; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  h4 {{ color: var(--text2); margin: 12px 0 6px; font-size: 0.95em; }}
  .stats {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
  th {{ cursor: pointer; user-select: none; white-space: nowrap; }}
  th:hover {{ color: var(--accent); }}
  th.sorted-asc::after {{ content: ' \u25b2'; }}
  th.sorted-desc::after {{ content: ' \u25bc'; }}
  code {{
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 3px; padding: 1px 5px; font-size: 12px; color: var(--orange);
  }}
  .detail-body {{ padding: 12px 16px; }}
  .detail-body > table {{ border-radius: 0; }}
  .meta-row {{ display: flex; gap: 24px; color: var(--text2); margin-bottom: 10px; font-size: 13px; }}
  .meta-row strong {{ color: var(--text); }}
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
  .bar-count {{ width: 120px; color: var(--text2); font-size: 12px; flex-shrink: 0; }}
  ul {{ padding-left: 20px; }}
  li {{ margin-bottom: 4px; color: var(--text2); font-size: 13px; }}
  li code {{ color: var(--orange); }}
</style>
</head>
<body>
<h1>Claude Tool Failures &mdash; Deep Analysis</h1>
<p class="subtitle">Analysis Date: {html_mod.escape(date_str)}</p>

<div class="stats">
  <div class="stat-card"><div class="value">{total_errors}</div><div class="label">Total Errors</div></div>
  <div class="stat-card"><div class="value">{len(stats)}</div><div class="label">Tools Affected</div></div>
  <div class="stat-card"><div class="value">{unique_projects}</div><div class="label">Projects</div></div>
  <div class="stat-card"><div class="value">{unique_sessions}</div><div class="label">Sessions</div></div>
</div>

<h2>Top Offending Tools</h2>
<table id="tools-table">
<thead>
<tr>
  <th onclick="sortTable('tools-table',0)">Tool</th>
  <th onclick="sortTable('tools-table',1)">Errors</th>
  <th onclick="sortTable('tools-table',2)">Projects</th>
  <th onclick="sortTable('tools-table',3)">Sessions</th>
</tr>
</thead>
<tbody>{top_tools_rows}</tbody>
</table>

<h2>Error Distribution by Category</h2>
<div class="bar-chart">
{cat_bars}
</div>

<h2>Per-Tool Detail</h2>
{tool_sections}

<h2>Common Error Patterns</h2>
<ul>
{pattern_items if pattern_items else "<li>No repeated patterns found.</li>"}
</ul>

<h2>Projects with Most Errors</h2>
<ul>
{project_items if project_items else "<li>No data.</li>"}
</ul>

<script>
(function() {{
  var sortState = {{}};
  window.sortTable = function(tableId, col) {{
    var table = document.getElementById(tableId);
    if (!table) return;
    var ths = table.querySelectorAll('th');
    var key = tableId + ':' + col;
    var asc = sortState[key] = !sortState[key];
    ths.forEach(function(th) {{ th.className = ''; }});
    ths[col].className = asc ? 'sorted-asc' : 'sorted-desc';
    var tbody = table.querySelector('tbody');
    var rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort(function(a, b) {{
      var av = a.cells[col] ? a.cells[col].textContent.trim() : '';
      var bv = b.cells[col] ? b.cells[col].textContent.trim() : '';
      var an = parseFloat(av.replace(/[^0-9.-]/g, ''));
      var bn = parseFloat(bv.replace(/[^0-9.-]/g, ''));
      var cmp = (!isNaN(an) && !isNaN(bn)) ? an - bn : av.localeCompare(bv);
      return asc ? cmp : -cmp;
    }});
    rows.forEach(function(r) {{ tbody.appendChild(r); }});
  }};
}})();
</script>
</body>
</html>"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

