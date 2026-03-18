# Claude History Analysis Suite

Analysis tools and guidelines for identifying and preventing tool errors in Claude Code sessions.

## CLI

All tools are accessed through a unified CLI:

```bash
python tools/cli.py <command>       # direct invocation
python -m claude_history <command>   # module invocation
python tools/cli.py -i              # interactive mode
python tools/cli.py --help          # full usage
```

| Command | Description |
|---------|-------------|
| `analyze` | Broad pattern analysis — errors, permissions, retries, suboptimal usage |
| `failures` | Deep error analysis with root cause classification |
| `daily` | Daily failure reports by project |
| `timeline` | Interactive HTML timeline for a project |
| `catalog` | Project catalog with cached metadata and activity tracking |

All commands support `--html` for HTML output and `--project` for single-project filtering.

## Docs

| File | Purpose |
|------|---------|
| `ANALYSIS_TOOLS_README.md` | Architecture and classification logic for the analysis tools |
| `DAILY_FAILURE_REPORTS_README.md` | Daily report format and usage |
| `code_review_claude_history_module.md` | Design decisions from the library refactoring |
| `2026-03-21-catalog-design.md` | Catalog feature architecture spec |

## Guidelines (`guidelines/`)

| File | Purpose |
|------|---------|
| `GUIDELINES.md` | 14 evidence-based directives for CLAUDE.md with rationale and examples |

## Guides (`guides/`)

| File | Purpose |
|------|---------|
| `WINDOWS_COMPATIBILITY_GUIDE.md` | Unix → Windows command mapping and platform-specific syntax |
| `READ_TOOL_PARAMETER_GUIDE.md` | Read tool offset/limit type mismatch fix |
| `NONEXISTENT_TOOLS_ANALYSIS.md` | Categories of nonexistent tool/command errors and prevention |
