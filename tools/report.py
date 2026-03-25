"""Generate a compact error analysis report for LLM-based guideline generation."""

import sys
from pathlib import Path
from collections import defaultdict
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_history.errors import classify_error
from claude_history.parsing import find_history_files, iter_session_events


def generate_report(projects_dir: Path, recent_days=None) -> str:
    """Scan history files and return a compact text report of error patterns."""
    history_files = find_history_files(projects_dir, recent_days=recent_days)
    if not history_files:
        return "No history files found."

    print(f"Scanning {len(history_files)} session files...", file=sys.stderr)

    # Counters
    errors_by_tool = defaultdict(int)
    errors_by_category = defaultdict(int)
    errors_by_tool_category = defaultdict(lambda: defaultdict(int))
    perm_denials_by_tool = defaultdict(int)
    suboptimal_by_cmd = defaultdict(int)
    retry_tools = defaultdict(int)
    total_sessions = 0
    total_projects = set()
    total_user_msgs = 0
    total_assistant_msgs = 0
    total_tool_calls = 0
    total_errors = 0
    error_snippets_by_tool = defaultdict(list)

    import re
    PERMISSION_PAT = re.compile(
        r"permission|denied|not allowed|allowlist|requires approval", re.I
    )
    SUBOPTIMAL_PAT = re.compile(r"^\s*(grep|rg|cat|head|tail|find|ls)\s")

    for i, file_path in enumerate(history_files, 1):
        if i % 50 == 0:
            print(f"  {i}/{len(history_files)}...", file=sys.stderr)

        total_sessions += 1
        total_projects.add(file_path.parent.name)
        session_tools = defaultdict(int)

        try:
            for event in iter_session_events(file_path):
                if event["type"] == "user":
                    has_text = False
                    for item in event["content"]:
                        if isinstance(item, dict):
                            if item.get("type") == "tool_result":
                                if item.get("is_error"):
                                    tool_name = item.get("tool_name", "Unknown")
                                    error_text = str(item.get("content", ""))
                                    cat, _ = classify_error(error_text)

                                    total_errors += 1
                                    errors_by_tool[tool_name] += 1
                                    errors_by_category[cat.value] += 1
                                    errors_by_tool_category[tool_name][cat.value] += 1

                                    if len(error_snippets_by_tool[tool_name]) < 3:
                                        error_snippets_by_tool[tool_name].append(
                                            error_text[:150].replace("\n", " ")
                                        )

                                if PERMISSION_PAT.search(str(item.get("content", ""))):
                                    perm_denials_by_tool[item.get("tool_name", "Unknown")] += 1

                            elif item.get("type") == "text":
                                has_text = True
                    if has_text:
                        total_user_msgs += 1

                elif event["type"] == "assistant":
                    total_assistant_msgs += 1
                    for item in event["content"]:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            total_tool_calls += 1
                            tool_name = item.get("name", "")
                            session_tools[tool_name] += 1

                            if tool_name == "Bash":
                                command = item.get("input", {}).get("command", "")
                                m = SUBOPTIMAL_PAT.match(command)
                                if m:
                                    suboptimal_by_cmd[m.group(1)] += 1

            # Count tools with 3+ calls as potential retries
            for tool, count in session_tools.items():
                if count >= 3:
                    retry_tools[tool] += 1

        except Exception:
            pass

    # Build report
    lines = []
    lines.append("# Claude Code Error Analysis")
    lines.append("")
    lines.append(f"Sessions: {total_sessions} across {len(total_projects)} projects")
    lines.append(f"Messages: {total_user_msgs} user, {total_assistant_msgs} assistant")
    lines.append(f"Tool calls: {total_tool_calls}")
    lines.append(f"Tool errors: {total_errors}")
    lines.append("")

    # Error distribution by category
    if errors_by_category:
        lines.append("## Errors by Category")
        for cat, count in sorted(errors_by_category.items(), key=lambda x: x[1], reverse=True):
            pct = count / total_errors * 100 if total_errors else 0
            lines.append(f"- {cat}: {count} ({pct:.0f}%)")
        lines.append("")

    # Top failing tools with category breakdown
    if errors_by_tool:
        lines.append("## Top Failing Tools")
        for tool, count in sorted(errors_by_tool.items(), key=lambda x: x[1], reverse=True)[:10]:
            cats = errors_by_tool_category[tool]
            cat_str = ", ".join(
                f"{c}: {n}" for c, n in sorted(cats.items(), key=lambda x: x[1], reverse=True)
            )
            lines.append(f"- {tool}: {count} errors ({cat_str})")
            for snippet in error_snippets_by_tool.get(tool, []):
                lines.append(f"  Example: {snippet}")
        lines.append("")

    # Permission denials
    if perm_denials_by_tool:
        lines.append("## Permission Denials")
        for tool, count in sorted(perm_denials_by_tool.items(), key=lambda x: x[1], reverse=True)[:10]:
            lines.append(f"- {tool}: {count}")
        lines.append("")

    # Suboptimal tool usage
    if suboptimal_by_cmd:
        lines.append("## Suboptimal Bash Usage (should use dedicated tools)")
        for cmd, count in sorted(suboptimal_by_cmd.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- Bash {cmd}: {count} occurrences")
        lines.append("")

    # Retry patterns
    if retry_tools:
        lines.append("## Tools with Frequent Retries (3+ calls in a session)")
        for tool, sessions in sorted(retry_tools.items(), key=lambda x: x[1], reverse=True)[:10]:
            lines.append(f"- {tool}: {sessions} sessions")
        lines.append("")

    return "\n".join(lines)
