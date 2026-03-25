# Claude Code History Analysis

Tools for analyzing Claude Code session histories to identify tool failure patterns and generate evidence-based guidelines.

## Install

```bash
pip install -e .
```

This installs the `claude-history` command and all dependencies.

## Quick Start

```bash
# Interactive mode — pick a command and project with arrow keys
claude-history -i

# List available projects
claude-history --list

# Generate a guideline report — paste into Claude for custom CLAUDE.md rules
claude-history report
```

## Commands

| Command | Description |
|---------|-------------|
| `report` | Generate error analysis for LLM-based CLAUDE.md guideline generation |
| `timeline <project>` | Interactive HTML timeline for a project |
| `analyze` | Broad pattern analysis — errors, permissions, retries, suboptimal usage |
| `failures` | Deep tool failure analysis with root cause classification |
| `daily` | Daily failure reports by project |
| `catalog` | Project catalog with cached metadata and activity tracking |

### Global Options

| Flag | Description |
|------|-------------|
| `--project NAME` | Filter to a single project (fuzzy match) |
| `--recent N` | Only include sessions from the last N days |
| `--html / --no-html` | HTML output (default) or markdown/terminal |
| `-i` | Interactive menu mode |

### Examples

```bash
# Generate guidelines from your error data
claude-history report                          # with prompt, ready to paste into Claude
claude-history report --no-prompt              # raw data only

# Analyze recent activity
claude-history --recent 7 failures            # last week's tool failures
claude-history --recent 30 --project mc analyze  # last month, one project

# Generate HTML reports
claude-history timeline my-project            # interactive timeline
claude-history catalog                        # project dashboard

# Markdown/terminal output
claude-history --no-html failures             # markdown report
claude-history --no-html catalog              # terminal table

# Daily reports
claude-history daily --date 2026-03-17        # specific date
claude-history daily --date all               # all dates
```

## Generating CLAUDE.md Guidelines

The `report` command scans your session history and produces a compact error analysis. By default it wraps the data in a prompt template (`prompts/generate_guidelines.txt`) that you paste into Claude to get custom CLAUDE.md guidelines tailored to your actual error patterns.

```bash
# Generate and copy to clipboard (Windows)
claude-history report | clip

# Generate and copy to clipboard (macOS)
claude-history report | pbcopy

# Save to file
claude-history report --output report.txt

# Edit the prompt template to customize guideline generation
# prompts/generate_guidelines.txt
```

The `docs/guidelines/GUIDELINES.md` file also contains 14 pre-written directives if you prefer a ready-made set.

## Project Structure

```
claude_history/          # Library package
    catalog.py           # SQLite-backed project catalog
    discovery.py         # Project directory discovery
    errors.py            # Error classification (9 categories)
    filters.py           # System tag stripping, text filtering
    html_theme.py        # Shared CSS theme for HTML reports
    parsing.py           # JSONL parsing, session event iteration
    timestamps.py        # Timestamp parsing and formatting

tools/                   # Analysis tools (imported by CLI)
    cli.py               # Unified typer CLI with interactive mode
    report.py            # Error analysis for guideline generation
    analyze_history.py   # Pattern analysis (D1-D4)
    analyze_failures.py  # Deep error analysis
    daily_reports.py     # Daily failure reports
    timeline.py          # HTML timeline generator

prompts/                 # Editable prompt templates
    generate_guidelines.txt

docs/                    # Documentation
    guidelines/          # CLAUDE.md directives
    guides/              # Platform and tool guides
```

## License

MIT
