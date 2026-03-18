# Claude Code History Analysis & Guidelines

Analysis tools and evidence-based guidelines to improve Claude Code sessions by reducing tool errors and optimizing workflows.

## Overview

This project analyzes Claude Code session histories to identify patterns in tool failures, permission issues, and suboptimal tool usage across hundreds of sessions. The analysis produces:

- **4 Python analysis tools** that scan history files and generate reports
- **14 evidence-based guidelines** to prevent 94% of identified errors
- **Windows compatibility guide** for cross-platform usage
- **Specialized guides** for recurring error patterns

## Project Structure

```
claude_history/             # Shared library package
    discovery.py            # Project discovery (HISTORY_ROOT, find_project, list_projects)
    parsing.py              # JSONL iteration, history file discovery, tool_id resolution
    errors.py               # ErrorCategory enum, classify_error()
    filters.py              # System tag stripping, injected text detection
    timestamps.py           # parse_timestamp(), format_duration()

tools/                      # CLI entry points
    timeline.py             # Interactive HTML timeline visualization
    analyze_history.py      # Broad pattern analysis (errors, permissions, retries)
    analyze_failures.py     # Deep error analysis with root cause classification
    daily_reports.py        # Daily markdown reports of failures by project

docs/
    guidelines/             # Content meant to be copied into CLAUDE.md
    guides/                 # Reference documentation
    ANALYSIS_TOOLS_README.md
    DAILY_FAILURE_REPORTS_README.md
    INDEX.md

output/                     # All generated output (gitignored)
```

## Quick Start

### For Users

1. **Quick Guidelines (6 rules, 10 min)**: See `docs/guidelines/CLAUDE_MD_QUICK_START_MARKDOWN.md`
2. **Full Guidelines (14 rules, 38 min)**: See `docs/guidelines/CLAUDE_MD_FULL_GUIDELINES_MARKDOWN.md`
3. **Windows Users**: Read `docs/guides/WINDOWS_COMPATIBILITY_GUIDE.md` first

Copy your preferred guideline set into your `CLAUDE.md` file.

### For Analysis

```bash
# Generate interactive project timeline
python tools/timeline.py self-consideration

# List available projects
python tools/timeline.py --list

# Generate broad pattern analysis
python tools/analyze_history.py

# Generate deep failure analysis
python tools/analyze_failures.py

# Generate daily failure reports
python tools/daily_reports.py --date 2026-03-17
```

All output is written to `output/`.

See `docs/ANALYSIS_TOOLS_README.md` for full documentation.

## Key Findings

**Total Errors Analyzed**: 1,310 across 688 sessions
**Preventable Errors**: 2,867 (94% with all guidelines)

### Top Error Categories
- Bash exit codes (740 errors) - mostly unhandled pipeline failures
- Edit/Write/Read failures (329 errors) - file not read before editing, parameter type mismatches
- Non-existent tool calls (85 errors) - pkill on Windows, deprecated skills, missing commands
- Permission denials (502 errors) - lack of settings.json allowlist
- Suboptimal tool usage (1,440 patterns) - Bash ls/grep/find instead of dedicated tools

### Top Improvements
| Category | Before | After | Reduction |
|----------|--------|-------|-----------|
| Bash errors | 740 | ~295 | 60% |
| Edit errors | 157 | ~8 | 95% |
| Non-existent calls | 85 | ~10 | 88% |
| Permission denials | 502 | ~50 | 90% |
| Suboptimal usage | 1,440 | 0 | 100% |

## Data Sources

Analysis based on:
- 688+ Claude Code sessions
- 348MB of JSONL history files
- 1,310 tool call errors
- 26 daily failure reports
- 23 unique tools analyzed

## Platform Support

- Linux/Mac: All guidelines and tools fully supported
- Windows: See `docs/guides/WINDOWS_COMPATIBILITY_GUIDE.md` for command equivalents

## License

MIT
