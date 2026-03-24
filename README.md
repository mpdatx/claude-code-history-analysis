# Claude Code History Analysis

Tools for analyzing Claude Code session histories to identify tool failure patterns and generate evidence-based guidelines.

## Quick Start

```bash
# Install dependencies
pip install typer InquirerPy

# Interactive mode
python tools/cli.py -i

# List available projects
python tools/cli.py --list

# Or use module invocation
python -m claude_history --help
```

## Commands

| Command | Description |
|---------|-------------|
| `timeline <project>` | Interactive HTML timeline for a project |
| `analyze` | Broad pattern analysis — errors, permissions, retries, suboptimal usage |
| `failures` | Deep tool failure analysis with root cause classification |
| `daily` | Daily failure reports by project |
| `catalog` | Project catalog with cached metadata and activity tracking |

All commands support `--html` for HTML output and `--project` for single-project filtering.

### Examples

```bash
# Generate timeline for a project
python tools/cli.py timeline my-project

# Analyze failures across all projects, output as HTML
python tools/cli.py failures --html

# Daily report for a specific date
python tools/cli.py daily --date 2026-03-17

# Project catalog (auto-scans on first run)
python tools/cli.py catalog

# Filter to one project
python tools/cli.py --project my-project analyze
```

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
    analyze_history.py   # Pattern analysis (D1-D4)
    analyze_failures.py  # Deep error analysis
    daily_reports.py     # Daily failure reports
    timeline.py          # HTML timeline generator

docs/                    # Documentation
    guidelines/          # CLAUDE.md directives
    guides/              # Platform and tool guides
```

## Guidelines

The `docs/guidelines/GUIDELINES.md` file contains 14 evidence-based directives for CLAUDE.md that address the most common tool failure patterns. See `docs/INDEX.md` for a full documentation index.

## License

MIT
