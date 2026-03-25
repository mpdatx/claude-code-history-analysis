#!/usr/bin/env python3
"""
Unified CLI for Claude history analysis tools.

Usage:
    python tools/cli.py --list
    python tools/cli.py timeline self-consideration
    python tools/cli.py analyze --project mc
    python tools/cli.py failures
    python tools/cli.py daily --date 2026-03-17
    python tools/cli.py -i                          # interactive menu
"""

import sys
from pathlib import Path
from typing import Optional

import click
import typer

# Ensure the repo root is on sys.path so claude_history is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claude_history.discovery import find_project, find_projects_dir, list_projects

app = typer.Typer(help="Claude Code history analysis tools.")

# Module-level state set by the callback
_resolved_dir: Optional[Path] = None
_single_project: bool = False
_interactive_mode: bool = False
_html_output: bool = True
_recent_days: Optional[int] = None

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"


def _get_project_choices():
    """Build project choices for the interactive picker, using catalog if available."""
    from datetime import datetime, timezone

    catalog_path = OUTPUT_DIR / "catalog.db"
    if catalog_path.exists():
        try:
            from claude_history.catalog import CatalogDB
            db = CatalogDB(catalog_path)
            projects = db.get_projects(sort_by="last_active")
            db.close()
            if projects:
                choices = []
                for p in projects:
                    last = p.get("last_active", "")
                    msgs = (p.get("user_messages", 0) or 0) + (p.get("assistant_messages", 0) or 0)
                    sessions = p.get("session_count", 0)
                    if last:
                        try:
                            from claude_history.timestamps import parse_timestamp
                            dt = parse_timestamp(last)
                            delta = datetime.now(timezone.utc) - dt
                            if delta.days == 0:
                                when = "today"
                            elif delta.days == 1:
                                when = "yesterday"
                            elif delta.days < 30:
                                when = f"{delta.days}d ago"
                            else:
                                when = f"{delta.days // 30}mo ago"
                        except (ValueError, AttributeError):
                            when = last[:10]
                    else:
                        when = "?"
                    label = f"{p['name']}  ({sessions} sessions, {msgs} msgs, {when})"
                    choices.append({"name": label, "value": p["name"]})
                return choices
        except Exception:
            pass

    # Fallback: simple directory listing
    projects_dir = find_projects_dir()
    if not projects_dir.exists():
        return []
    choices = []
    for d in sorted(projects_dir.iterdir(), key=lambda p: p.name.lower()):
        if d.is_dir():
            n_sessions = len(list(d.glob("*.jsonl")))
            choices.append({"name": f"{d.name}  ({n_sessions} sessions)", "value": d.name})
    return choices


def _prompt_for_param(name: str, param: click.Parameter):
    """Prompt the user for a single parameter value using InquirerPy. Returns None to skip."""
    from InquirerPy import inquirer

    help_text = param.help or ""
    is_bool = isinstance(param.type, click.types.BoolParamType)

    if is_bool:
        return inquirer.confirm(
            message=f"{name}: {help_text}" if help_text else name,
            default=False,
        ).execute()

    result = inquirer.text(
        message=f"{name}: {help_text}" if help_text else name,
        default="",
    ).execute()
    return result if result else None


# Params to skip in interactive mode: output paths have good defaults,
# and project_name is handled by the interactive project picker.
_INTERACTIVE_SKIP_PARAMS = {"help", "output", "output_dir", "project_name", "db_path", "scan", "html", "recent"}


def run_interactive(ctx: typer.Context):
    """Present an interactive menu with arrow-key navigation."""
    from InquirerPy import inquirer
    from InquirerPy.separator import Separator

    # Resolve the click Group so we can introspect commands
    click_group = ctx.parent.command if ctx.parent else ctx.command
    if not isinstance(click_group, click.Group):
        click_group = ctx.command
    commands = click_group.list_commands(ctx)
    cmd_objects = {name: click_group.get_command(ctx, name) for name in commands}

    print()
    print("Claude History -- Interactive Mode")
    print()

    # -- Command selection (first) --
    cmd_choices = []
    for name in commands:
        cmd = cmd_objects[name]
        desc = (cmd.get_short_help_str() if cmd else "") or ""
        label = f"{name:12s} {desc}"
        cmd_choices.append({"name": label, "value": name})

    cmd_name = inquirer.select(
        message="Command:",
        choices=cmd_choices,
    ).execute()

    cmd = cmd_objects[cmd_name]
    print(f"  > {cmd_name}")
    print()

    # -- Project selection (second) --
    scope = inquirer.select(
        message="Project scope:",
        choices=[
            {"name": "All projects (no filter)", "value": "all"},
            {"name": "Pick a specific project...", "value": "pick"},
        ],
    ).execute()

    global _resolved_dir, _single_project
    if scope == "pick":
        project_choices = _get_project_choices()
        if not project_choices:
            print("No projects found.")
            raise typer.Exit(1)

        chosen = inquirer.fuzzy(
            message="Select project (type to filter):",
            choices=project_choices,
            max_height="60%",
        ).execute()

        resolved = find_project(chosen)
        if not resolved:
            raise typer.Exit(1)
        _resolved_dir = resolved
        _single_project = True
        print(f"  Project: {resolved.name}")
    else:
        _resolved_dir = find_projects_dir()
        _single_project = False
    print()

    # -- Collect remaining parameters --
    kwargs = {}
    params = [p for p in cmd.params if p.name not in _INTERACTIVE_SKIP_PARAMS]
    if params:
        print(f"  {cmd_name} options (Enter to skip)")
        for param in params:
            value = _prompt_for_param(param.human_readable_name, param)
            if value is not None:
                kwargs[param.name] = value
        print()

    summary = f"Running: {cmd_name}"
    if kwargs:
        opts = " ".join(f"--{k}={v}" for k, v in kwargs.items())
        summary += f" {opts}"
    print(summary)
    print()

    # Invoke the selected command through click's context
    ctx.invoke(cmd, **kwargs)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    project: Optional[str] = typer.Option(None, help="Filter to a single project (fuzzy match)"),
    projects_dir: Optional[Path] = typer.Option(None, help="Override projects directory"),
    list_projects_flag: bool = typer.Option(False, "--list", help="List available projects and exit"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive menu mode"),
    html: bool = typer.Option(True, "--html/--no-html", help="HTML output (default) or markdown/terminal"),
    recent: Optional[int] = typer.Option(None, "--recent", help="Only include sessions from the last N days"),
):
    """Claude Code history analysis tools."""
    global _resolved_dir, _single_project, _interactive_mode, _html_output, _recent_days
    _html_output = html
    _recent_days = recent
    if list_projects_flag:
        list_projects()
        raise typer.Exit()
    if interactive:
        _interactive_mode = True
        run_interactive(ctx)
        raise typer.Exit()
    if project:
        resolved = find_project(project)
        if not resolved:
            raise typer.Exit(1)
        _resolved_dir = resolved
        _single_project = True
    else:
        _resolved_dir = projects_dir or find_projects_dir()
        _single_project = False
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        raise typer.Exit()


@app.command()
def timeline(
    project_name: Optional[str] = typer.Argument(None, help="Project name (positional shorthand)"),
    output: Optional[Path] = typer.Option(None, help="Output file path"),
):
    """Generate interactive HTML timeline for a project."""
    from tools.timeline import parse_session, generate_html

    # Resolve which project to use: positional arg > --project flag
    if project_name:
        project_dir = find_project(project_name)
        if not project_dir:
            raise typer.Exit(1)
    elif _single_project and _resolved_dir:
        project_dir = _resolved_dir
    else:
        typer.echo("Error: timeline requires a project. Use positional arg or --project flag.", err=True)
        typer.echo("  claude-history timeline <project-name>", err=True)
        typer.echo("  claude-history --project <name> timeline", err=True)
        raise typer.Exit(1)

    print(f"Project: {project_dir.name}")

    from claude_history.parsing import find_history_files
    jsonl_files = sorted(find_history_files(project_dir, recent_days=_recent_days))
    if not jsonl_files:
        typer.echo("No JSONL session files found.", err=True)
        raise typer.Exit(1)

    print(f"Parsing {len(jsonl_files)} session files...")
    sessions = []
    for jf in jsonl_files:
        s = parse_session(jf)
        if s["start_time"] is not None:
            sessions.append(s)

    print(f"Parsed {len(sessions)} sessions with data.")

    html_content = generate_html(project_dir.name, sessions)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = output or (OUTPUT_DIR / f"timeline_{project_dir.name}.html")
    output_file.write_text(html_content, encoding="utf-8")
    resolved_path = output_file.resolve()
    print(f"Timeline written to: {resolved_path}")

    _offer_open_in_browser(resolved_path)


def _offer_open_in_browser(path: Path):
    """In interactive mode, offer to open a file in the default browser."""
    if _interactive_mode:
        from InquirerPy import inquirer
        if inquirer.confirm(message="Open in browser?", default=True).execute():
            import webbrowser
            webbrowser.open(path.as_uri())


@app.command()
def analyze(
    output: Optional[Path] = typer.Option(None, help="Output file path"),
):
    """Broad pattern analysis (errors, permissions, retries, suboptimal usage)."""
    from datetime import datetime
    from tools.analyze_history import (
        AnalysisResults,
        scan_history,
        generate_summary_table,
        generate_markdown_report,
        generate_html_report,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = AnalysisResults()
    scan_history(_resolved_dir, results, recent_days=_recent_days)

    summary = generate_summary_table(results)
    for line in summary:
        print(line)

    if _html_output:
        output_file = output or (OUTPUT_DIR / f"claude_history_report_{datetime.now().strftime('%Y-%m-%d')}.html")
        generate_html_report(results, output_file)
        resolved = output_file.resolve()
        print(f"\nHTML report: {resolved}")
        _offer_open_in_browser(resolved)
    else:
        output_file = output or (OUTPUT_DIR / f"claude_history_report_{datetime.now().strftime('%Y-%m-%d')}.md")
        generate_markdown_report(results, output_file)
        print(f"\nReport written to {output_file}")


@app.command()
def failures(
    output: Optional[Path] = typer.Option(None, help="Output file path"),
):
    """Deep analysis of tool call failures."""
    from datetime import datetime
    from tools.analyze_failures import (
        scan_history_files,
        compute_tool_stats,
        generate_detailed_report,
        generate_html_report,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Scanning history files...", file=sys.stderr)
    errors = scan_history_files(_resolved_dir, recent_days=_recent_days)
    print(f"Found {len(errors)} tool errors", file=sys.stderr)

    stats = compute_tool_stats(errors)
    print(f"Analyzed {len(stats)} unique tools", file=sys.stderr)

    if _html_output:
        output_file = output or (OUTPUT_DIR / f"claude_tool_failures_{datetime.now().strftime('%Y-%m-%d')}.html")
        generate_html_report(errors, stats, output_file)
        resolved = output_file.resolve()
        print(f"HTML report: {resolved}")
        _offer_open_in_browser(resolved)
    else:
        output_file = output or (OUTPUT_DIR / f"claude_tool_failures_{datetime.now().strftime('%Y-%m-%d')}.md")
        print(f"Generating report: {output_file}", file=sys.stderr)
        generate_detailed_report(errors, stats, output_file)
        print(f"Report complete: {output_file}")


@app.command()
def daily(
    date: Optional[str] = typer.Option(None, help="Date (YYYY-MM-DD) or 'all'"),
    output_dir: Optional[Path] = typer.Option(None, help="Output directory"),
):
    """Generate daily failure reports."""
    from tools.daily_reports import scan_history_files, generate_daily_report, generate_html_report

    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Reports directory: {out_dir}", file=sys.stderr)

    print("Scanning history files...", file=sys.stderr)
    failures_by_date = scan_history_files(_resolved_dir, recent_days=_recent_days)

    if not failures_by_date:
        print("No failures found", file=sys.stderr)
        return

    print(f"Found failures on {len(failures_by_date)} days", file=sys.stderr)

    if date:
        if date.lower() == "all":
            dates_to_report = sorted(failures_by_date.keys())
        else:
            dates_to_report = [date] if date in failures_by_date else []
            if not dates_to_report:
                print(f"No failures found for date: {date}", file=sys.stderr)
                return
    else:
        dates_to_report = [max(failures_by_date.keys())] if failures_by_date else []

    last_file = None
    for d in dates_to_report:
        f = failures_by_date[d]
        if _html_output:
            output_file = out_dir / f"failures_{d}.html"
            generate_html_report(d, f, output_file)
        else:
            output_file = out_dir / f"failures_{d}.md"
            generate_daily_report(d, f, output_file)
        last_file = output_file

    print(f"\nGenerated {len(dates_to_report)} report(s)", file=sys.stderr)
    print(f"View reports in: {out_dir}", file=sys.stderr)

    if html and last_file:
        resolved = last_file.resolve()
        _offer_open_in_browser(resolved)


@app.command()
def catalog(
    scan: bool = typer.Option(False, "--scan", help="Rescan projects before displaying"),
    sort: str = typer.Option("last_active", "--sort", help="Sort by: last_active, sessions, errors, name"),
    db_path: Optional[Path] = typer.Option(None, "--db-path", help="Override catalog database path"),
):
    """Project catalog with cached metadata and activity tracking."""
    from claude_history.catalog import CatalogDB

    catalog_path = db_path or (OUTPUT_DIR / "catalog.db")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    db = CatalogDB(catalog_path)

    try:
        # Auto-scan on first run or when --scan requested
        if scan or not db.has_data():
            if _single_project and _resolved_dir:
                print(f"Scanning project: {_resolved_dir.name}", file=sys.stderr)
                db.scan_project(_resolved_dir.name, _resolved_dir)
            else:
                db.scan_all(_resolved_dir)

        # Query
        project_filter = _resolved_dir.name if _single_project else None
        projects = db.get_projects(
            recent_days=_recent_days,
            sort_by=sort,
            project_name=project_filter,
        )

        if _html_output:
            html_content = CatalogDB.generate_html(projects)
            html_file = OUTPUT_DIR / "catalog.html"
            html_file.write_text(html_content, encoding="utf-8")
            resolved_path = html_file.resolve()
            print(f"Catalog written to: {resolved_path}")
            _offer_open_in_browser(resolved_path)
        else:
            CatalogDB.print_table(projects)
    finally:
        db.close()


@app.command()
def report(
    output: Optional[Path] = typer.Option(None, help="Save report to file instead of stdout"),
    prompt: bool = typer.Option(True, "--prompt/--no-prompt", help="Wrap data in guideline generation prompt"),
):
    """Generate error analysis for LLM-based guideline generation."""
    from tools.report import generate_report

    data = generate_report(_resolved_dir, recent_days=_recent_days)

    if prompt:
        prompt_file = REPO_ROOT / "prompts" / "generate_guidelines.txt"
        if prompt_file.exists():
            template = prompt_file.read_text(encoding="utf-8")
            text = template.replace("{data}", data)
        else:
            print(f"Warning: prompt template not found at {prompt_file}", file=sys.stderr)
            text = data
    else:
        text = data

    if output:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(f"Report saved to: {output.resolve()}")
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    app()
