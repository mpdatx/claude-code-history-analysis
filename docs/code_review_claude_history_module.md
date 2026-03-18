# Code Review: `claude_history` Module

All issues identified in this review have been resolved.

## Critical (2)

### 1. Session ID / project name derivation changed — RESOLVED (not a bug)

The original scripts used `file_path.parent.name` / `file_path.parent.parent.name`. The refactored tools use `file_path.stem` / `file_path.parent.name`. Verified on-disk layout: JSONL files are flat (`projects/<project>/<uuid>.jsonl`), so the **original code was wrong** — it labeled every error as project `"projects"`. The refactored code is correct.

### 2. `find_project()` and `list_projects()` use `HISTORY_ROOT` directly — FIXED

Both functions now call `find_projects_dir()` instead of hardcoding `HISTORY_ROOT`, so they work with alternative project directory locations.

---

## Important (4)

### 3. `analyze_history.py` retains its own `classify_error_type()` — FIXED

Replaced the local 4-case classifier with a thin wrapper around the shared `classify_error()` from `claude_history.errors` (10 categories).

### 4. `timeline.py` doesn't use `find_history_files()` or `iter_session_events()` — DOCUMENTED

Added docstring to `parse_session()` explaining why: timeline needs per-entry access to `gitBranch`, `version`, and raw timestamps that `iter_session_events()` doesn't expose.

### 5. `find_projects_dir()` silently returns a non-existent path — FIXED

Now prints a warning to stderr when no directory is found at any checked location.

### 6. Cross-session `tool_id_to_name` leak fixed — NOTED

The original `daily_reports` shared `tool_id_to_name` across all files. The refactored version scopes it per-session via `iter_session_events()`. This is a bug fix, not a regression.

---

## Suggestions (6)

All resolved:

| # | File | Issue | Resolution |
|---|------|-------|------------|
| 7 | `__init__.py` | Exports nothing | Added re-exports of all key symbols with `__all__` |
| 8 | `timestamps.py` | `parse_timestamp()` no error handling | Added empty-string check with `ValueError` |
| 9 | `timestamps.py` | `format_duration()` missing type annotation | Added `delta: timedelta` |
| 10 | `filters.py` | `SYSTEM_TAG_RE` misses self-closing tags | Regex now handles both `<tag .../>` and `<tag>...</tag>` |
| 11 | `filters.py` | `extract_user_text()` missing type annotation | Added `content: list[dict \| str]` |
| 12 | `filters.py` | Duplicate dict/str logic | Extracted `_clean_text()` helper |
