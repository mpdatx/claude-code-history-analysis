# Catalog Design

## Purpose

A persistent project catalog backed by SQLite that caches project metadata so the CLI doesn't need to rescan all JSONL files on every invocation. Supports incremental updates, filtered views by recency, and HTML dashboard output.

## Data Model

### Table: `meta`

| Column | Type | Description |
|--------|------|-------------|
| key | TEXT PK | e.g. `schema_version` |
| value | TEXT | e.g. `1` |

Checked on startup. If schema_version doesn't match the code's expected version, the db is rebuilt from scratch.

### Table: `projects`

All columns are aggregated from the sessions table. No direct parsing — recomputed via `SELECT SUM(...) FROM sessions WHERE project = ?`.

| Column | Type | Description |
|--------|------|-------------|
| name | TEXT PK | Directory name (e.g. `G--claude-self-consideration`) |
| cwd | TEXT | Working directory from the most recent session |
| session_count | INTEGER | Number of JSONL session files |
| first_active | TEXT | ISO timestamp of earliest message (MIN of sessions.first_ts) |
| last_active | TEXT | ISO timestamp of most recent message (MAX of sessions.last_ts) |
| total_size_bytes | INTEGER | Sum of session file sizes |
| user_messages | INTEGER | Total user messages across all sessions |
| assistant_messages | INTEGER | Total assistant messages across all sessions |
| tool_calls | INTEGER | Total tool_use items |
| tool_errors | INTEGER | Total tool_result items with is_error=true |
| last_scanned | TEXT | ISO timestamp when this project was last scanned |

### Table: `sessions`

Per-session data that enables incremental scanning and project aggregate recomputation.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | JSONL filename stem (UUID) |
| project | TEXT FK | References projects.name |
| file_size | INTEGER | File size in bytes |
| file_mtime | TEXT | File modification time (ISO) |
| first_ts | TEXT | First timestamp in session |
| last_ts | TEXT | Last timestamp in session |
| cwd | TEXT | Working directory from session entries |
| user_messages | INTEGER | User message count |
| assistant_messages | INTEGER | Assistant message count |
| tool_calls | INTEGER | tool_use item count |
| tool_errors | INTEGER | tool_result items with is_error=true |

Change detection: skip files where id + file_size + file_mtime all match. Sessions with no parseable timestamps are skipped (not stored).

## Incremental Scan Logic

Each project's updates are wrapped in a transaction for crash safety.

1. List all project directories under projects_dir.
2. For each project, use `find_history_files()` from `parsing.py` (recursive UUID-pattern glob, excludes `history.jsonl`).
3. For each file, check sessions table — skip if id + file_size + file_mtime match.
4. Parse new/changed files using `iter_session_events()`: extract timestamps, count messages/tool_calls/errors, capture cwd from `entry.get("cwd")`.
5. After removing stale sessions (files no longer on disk), recompute project aggregates from sessions table via SQL aggregation. Project `cwd` is taken from the session with the latest `last_ts`.
6. Remove project rows that have zero remaining sessions.

## CLI Interface

New `catalog` subcommand on the existing typer app:

```bash
claude-history catalog                                  # show table from cache (auto-scan on first run)
claude-history catalog --scan                           # rescan then show
claude-history --project mc catalog --scan              # rescan one project
claude-history catalog --recent 7                       # show projects active in last N days
claude-history catalog --sort last-active               # sort by last activity (default)
claude-history catalog --sort sessions                  # sort by session count
claude-history catalog --sort errors                    # sort by error count
claude-history catalog --html                           # generate HTML dashboard, open in browser
claude-history catalog --html --recent 30               # HTML filtered to last 30 days
claude-history catalog --db-path /path/to/catalog.db    # override db location
```

Project filtering uses the existing top-level `--project` flag (read from `_resolved_dir` / `_single_project` module globals), consistent with other subcommands.

Database location: `output/catalog.db` by default, overridable via `--db-path`.

Terminal table output uses `rich.table.Table` for a formatted display.

## HTML Dashboard

A single-page HTML file with:

- Summary stats (total projects, sessions, messages, errors)
- Sortable project table with all catalog fields
- Activity indicators (last active relative time)
- Reuses the same CSS variables from `tools/timeline.py` (`--bg: #0d1117`, `--surface: #161b22`, etc.)

Generated to `output/catalog.html`. In interactive mode, offers to open in browser after generation.

HTML generation lives in `claude_history/catalog.py` alongside the data logic (single-module approach — the HTML is simple table rendering, not a complex presentation layer).

## Interactive Mode Integration

When `-i` is active and a catalog db exists, the project picker:

- Shows last-active date and message counts next to each project name
- Sorts by recent activity (most recent first)
- Replaces the current simple directory listing from `_get_project_choices()`

When no catalog db exists in interactive mode, falls back to the current directory listing (same behavior as today).

## Files to Create/Modify

| File | Action |
|------|--------|
| `claude_history/catalog.py` | Create — CatalogDB class, scan logic, HTML generation |
| `tools/cli.py` | Modify — add `catalog` subcommand, update interactive project picker |
