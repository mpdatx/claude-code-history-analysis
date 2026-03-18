"""SQLite-backed project catalog for Claude history analysis."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from claude_history.parsing import find_history_files, iter_session_events
from claude_history.timestamps import parse_timestamp

SCHEMA_VERSION = 1

_CREATE_META = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
)
"""

_CREATE_PROJECTS = """
CREATE TABLE IF NOT EXISTS projects (
    name              TEXT PRIMARY KEY,
    cwd               TEXT,
    session_count     INT,
    first_active      TEXT,
    last_active       TEXT,
    total_size_bytes  INT,
    user_messages     INT,
    assistant_messages INT,
    tool_calls        INT,
    tool_errors       INT,
    last_scanned      TEXT
)
"""

_CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    id                 TEXT PRIMARY KEY,
    project            TEXT REFERENCES projects(name),
    file_size          INT,
    file_mtime         TEXT,
    first_ts           TEXT,
    last_ts            TEXT,
    cwd                TEXT,
    user_messages      INT,
    assistant_messages INT,
    tool_calls         INT,
    tool_errors        INT
)
"""

_CREATE_IDX_SESSIONS_PROJECT = """
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project)
"""


class CatalogDB:
    """SQLite-backed catalog of Claude history projects and sessions."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ) if self._table_exists("meta") else None

        existing_version = None
        if cur is not None:
            row = cur.fetchone()
            if row:
                existing_version = int(row[0])

        if existing_version != SCHEMA_VERSION:
            # Drop all tables and rebuild
            self.conn.execute("DROP TABLE IF EXISTS sessions")
            self.conn.execute("DROP TABLE IF EXISTS projects")
            self.conn.execute("DROP TABLE IF EXISTS meta")

        self.conn.execute(_CREATE_META)
        self.conn.execute(_CREATE_PROJECTS)
        self.conn.execute(_CREATE_SESSIONS)
        self.conn.execute(_CREATE_IDX_SESSIONS_PROJECT)
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def _table_exists(self, name: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    # ------------------------------------------------------------------
    # Task 2: Scanning
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_session(file_path: Path) -> Optional[dict]:
        """Parse a session JSONL file and return stats, or None if no timestamps."""
        stats = {
            "first_ts": None,
            "last_ts": None,
            "cwd": None,
            "user_messages": 0,
            "assistant_messages": 0,
            "tool_calls": 0,
            "tool_errors": 0,
        }

        try:
            for event in iter_session_events(file_path):
                ts = event.get("timestamp", "")
                if ts:
                    try:
                        parse_timestamp(ts)
                        if stats["first_ts"] is None:
                            stats["first_ts"] = ts
                        stats["last_ts"] = ts
                    except ValueError:
                        pass

                entry = event.get("entry", {})
                if stats["cwd"] is None:
                    cwd = entry.get("cwd")
                    if cwd:
                        stats["cwd"] = cwd

                event_type = event.get("type")
                content = event.get("content", [])

                if event_type == "user":
                    # Count user messages only if they have text content items
                    has_text = any(
                        isinstance(item, dict) and item.get("type") == "text"
                        for item in content
                    ) if isinstance(content, list) else False
                    if has_text:
                        stats["user_messages"] += 1

                    # Count tool errors from tool_result items
                    if isinstance(content, list):
                        for item in content:
                            if (
                                isinstance(item, dict)
                                and item.get("type") == "tool_result"
                                and item.get("is_error")
                            ):
                                stats["tool_errors"] += 1

                elif event_type == "assistant":
                    stats["assistant_messages"] += 1
                    # Count tool_use items
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "tool_use":
                                stats["tool_calls"] += 1

        except Exception:
            pass

        if stats["first_ts"] is None:
            return None

        return stats

    def scan_project(self, project_name: str, project_dir: Path) -> None:
        """Scan a project directory and update the catalog incrementally."""
        files = find_history_files(project_dir)

        # Build set of current file IDs (stem = UUID)
        current_ids: set[str] = set()

        for file_path in files:
            session_id = file_path.stem
            current_ids.add(session_id)

            file_size = file_path.stat().st_size
            file_mtime = datetime.fromtimestamp(
                file_path.stat().st_mtime, tz=timezone.utc
            ).isoformat()

            # Check if already up to date
            row = self.conn.execute(
                "SELECT file_size, file_mtime FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()

            if row and row["file_size"] == file_size and row["file_mtime"] == file_mtime:
                continue  # Incremental skip

            stats = self._parse_session(file_path)
            if stats is None:
                continue

            self.conn.execute(
                """
                INSERT OR REPLACE INTO sessions
                    (id, project, file_size, file_mtime,
                     first_ts, last_ts, cwd,
                     user_messages, assistant_messages,
                     tool_calls, tool_errors)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    project_name,
                    file_size,
                    file_mtime,
                    stats["first_ts"],
                    stats["last_ts"],
                    stats["cwd"],
                    stats["user_messages"],
                    stats["assistant_messages"],
                    stats["tool_calls"],
                    stats["tool_errors"],
                ),
            )

        # Remove stale sessions (files deleted from disk)
        existing_rows = self.conn.execute(
            "SELECT id FROM sessions WHERE project=?", (project_name,)
        ).fetchall()
        for r in existing_rows:
            if r["id"] not in current_ids:
                self.conn.execute("DELETE FROM sessions WHERE id=?", (r["id"],))

        self._recompute_project(project_name)
        self.conn.commit()

    def _recompute_project(self, project_name: str) -> None:
        """Recompute project aggregates from sessions table."""
        row = self.conn.execute(
            """
            SELECT
                COUNT(*)           AS session_count,
                MIN(first_ts)      AS first_active,
                MAX(last_ts)       AS last_active,
                SUM(file_size)     AS total_size_bytes,
                SUM(user_messages) AS user_messages,
                SUM(assistant_messages) AS assistant_messages,
                SUM(tool_calls)    AS tool_calls,
                SUM(tool_errors)   AS tool_errors
            FROM sessions
            WHERE project=?
            """,
            (project_name,),
        ).fetchone()

        if not row or row["session_count"] == 0:
            self.conn.execute("DELETE FROM projects WHERE name=?", (project_name,))
            return

        # Get cwd from most recent session
        cwd_row = self.conn.execute(
            "SELECT cwd FROM sessions WHERE project=? ORDER BY last_ts DESC LIMIT 1",
            (project_name,),
        ).fetchone()
        cwd = cwd_row["cwd"] if cwd_row else None

        now_iso = datetime.now(tz=timezone.utc).isoformat()

        self.conn.execute(
            """
            INSERT OR REPLACE INTO projects
                (name, cwd, session_count, first_active, last_active,
                 total_size_bytes, user_messages, assistant_messages,
                 tool_calls, tool_errors, last_scanned)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_name,
                cwd,
                row["session_count"],
                row["first_active"],
                row["last_active"],
                row["total_size_bytes"] or 0,
                row["user_messages"] or 0,
                row["assistant_messages"] or 0,
                row["tool_calls"] or 0,
                row["tool_errors"] or 0,
                now_iso,
            ),
        )

    def scan_all(self, projects_dir: Path) -> None:
        """Scan all project subdirectories and remove stale projects."""
        if not projects_dir.exists():
            print(f"Projects directory not found: {projects_dir}", file=sys.stderr)
            return

        subdirs = [d for d in projects_dir.iterdir() if d.is_dir()]
        current_names: set[str] = set()

        for i, project_dir in enumerate(subdirs, 1):
            project_name = project_dir.name
            current_names.add(project_name)
            print(
                f"[{i}/{len(subdirs)}] Scanning {project_name}...",
                file=sys.stderr,
            )
            try:
                self.scan_project(project_name, project_dir)
            except Exception as exc:
                print(f"  Warning: failed to scan {project_name}: {exc}", file=sys.stderr)

        # Remove projects no longer on disk
        existing = self.conn.execute("SELECT name FROM projects").fetchall()
        for row in existing:
            if row["name"] not in current_names:
                self.conn.execute(
                    "DELETE FROM sessions WHERE project=?", (row["name"],)
                )
                self.conn.execute(
                    "DELETE FROM projects WHERE name=?", (row["name"],)
                )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Task 3: Queries
    # ------------------------------------------------------------------

    def get_projects(
        self,
        recent_days: Optional[int] = None,
        sort_by: str = "last_active",
        project_name: Optional[str] = None,
    ) -> list[dict]:
        """Return list of project dicts, optionally filtered and sorted."""
        conditions = []
        params: list = []

        if recent_days is not None:
            cutoff = datetime.now(tz=timezone.utc) - timedelta(days=recent_days)
            conditions.append("last_active >= ?")
            params.append(cutoff.isoformat())

        if project_name is not None:
            conditions.append("name = ?")
            params.append(project_name)

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        sort_map = {
            "last_active": "last_active DESC",
            "session_count": "session_count DESC",
            "tool_errors": "tool_errors DESC",
            "name": "name ASC",
        }
        order_clause = "ORDER BY " + sort_map.get(sort_by, "last_active DESC")

        sql = f"SELECT * FROM projects {where_clause} {order_clause}"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def has_data(self) -> bool:
        """Return True if any projects exist in the catalog."""
        row = self.conn.execute("SELECT COUNT(*) FROM projects").fetchone()
        return row[0] > 0

    # ------------------------------------------------------------------
    # Task 4: Rich Terminal Display
    # ------------------------------------------------------------------

    @staticmethod
    def print_table(projects: list[dict]) -> None:
        """Print a rich terminal table of projects."""
        try:
            from rich.console import Console
            from rich.table import Table
        except ImportError:
            # Fallback plain text
            for p in projects:
                print(p)
            return

        def fmt_size(n: int) -> str:
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f} MB"
            elif n >= 1_000:
                return f"{n / 1_000:.1f} KB"
            return f"{n} B"

        def fmt_relative(ts_str: Optional[str]) -> str:
            if not ts_str:
                return "-"
            try:
                dt = parse_timestamp(ts_str)
                now = datetime.now(tz=timezone.utc)
                delta = now - dt
                days = delta.days
                if days == 0:
                    return "today"
                elif days == 1:
                    return "yesterday"
                elif days < 60:
                    return f"{days}d ago"
                else:
                    months = days // 30
                    return f"{months}mo ago"
            except ValueError:
                return ts_str[:10] if ts_str else "-"

        def trunc(s: Optional[str], n: int = 40) -> str:
            if not s:
                return ""
            return s if len(s) <= n else "..." + s[-(n - 3):]

        console = Console()
        table = Table(show_header=True, header_style="bold cyan")

        table.add_column("Project", style="bold")
        table.add_column("Sessions", justify="right")
        table.add_column("Messages", justify="right")
        table.add_column("Tools", justify="right")
        table.add_column("Errors", justify="right")
        table.add_column("Size", justify="right")
        table.add_column("Last Active")
        table.add_column("Working Directory", no_wrap=False)

        for p in projects:
            errors_str = str(p.get("tool_errors", 0)) if p.get("tool_errors", 0) > 0 else "-"
            messages = (p.get("user_messages", 0) or 0) + (p.get("assistant_messages", 0) or 0)
            table.add_row(
                p.get("name", ""),
                str(p.get("session_count", 0)),
                str(messages),
                str(p.get("tool_calls", 0)),
                errors_str,
                fmt_size(p.get("total_size_bytes", 0) or 0),
                fmt_relative(p.get("last_active")),
                trunc(p.get("cwd"), 40),
            )

        console.print(table)

    # ------------------------------------------------------------------
    # Task 5: HTML Dashboard
    # ------------------------------------------------------------------

    @staticmethod
    def generate_html(projects: list[dict]) -> str:
        """Generate an HTML dashboard string for the project catalog."""
        total_sessions = sum(p.get("session_count", 0) or 0 for p in projects)
        total_messages = sum(
            (p.get("user_messages", 0) or 0) + (p.get("assistant_messages", 0) or 0)
            for p in projects
        )
        total_errors = sum(p.get("tool_errors", 0) or 0 for p in projects)
        total_size = sum(p.get("total_size_bytes", 0) or 0 for p in projects)

        def fmt_size_html(n: int) -> str:
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f} MB"
            elif n >= 1_000:
                return f"{n / 1_000:.1f} KB"
            return f"{n} B"

        rows_html = ""
        for p in projects:
            messages = (p.get("user_messages", 0) or 0) + (p.get("assistant_messages", 0) or 0)
            errors = p.get("tool_errors", 0) or 0
            errors_str = str(errors) if errors > 0 else "-"
            cwd = p.get("cwd") or ""
            last_active = p.get("last_active") or ""
            rows_html += (
                f"<tr>"
                f"<td>{p.get('name', '')}</td>"
                f"<td>{p.get('session_count', 0)}</td>"
                f"<td>{messages}</td>"
                f"<td>{p.get('tool_calls', 0)}</td>"
                f"<td>{errors_str}</td>"
                f"<td>{fmt_size_html(p.get('total_size_bytes', 0) or 0)}</td>"
                f"<td class='ts' data-ts='{last_active}'>{last_active[:10] if last_active else '-'}</td>"
                f"<td title='{cwd}'>{cwd}</td>"
                f"</tr>\n"
            )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude History Catalog</title>
<style>
  :root {{
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #c9d1d9;
    --text-muted: #8b949e;
    --accent: #58a6ff;
    --error: #f85149;
    --success: #3fb950;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
    font-size: 14px;
    padding: 24px;
  }}
  h1 {{ color: var(--accent); margin-bottom: 24px; font-size: 1.6em; }}
  .stats {{
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 24px;
  }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 24px;
    min-width: 140px;
    text-align: center;
  }}
  .stat-card .value {{
    font-size: 1.8em;
    font-weight: bold;
    color: var(--accent);
  }}
  .stat-card .label {{
    color: var(--text-muted);
    font-size: 0.85em;
    margin-top: 4px;
  }}
  .controls {{
    margin-bottom: 16px;
  }}
  #filter {{
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 14px;
    width: 280px;
  }}
  #filter::placeholder {{ color: var(--text-muted); }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: var(--surface);
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid var(--border);
  }}
  thead {{ background: #1c2128; }}
  th {{
    padding: 10px 14px;
    text-align: left;
    color: var(--text-muted);
    font-weight: 600;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }}
  th:hover {{ color: var(--accent); }}
  th.sorted-asc::after {{ content: ' ▲'; }}
  th.sorted-desc::after {{ content: ' ▼'; }}
  td {{
    padding: 8px 14px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
    font-size: 13px;
  }}
  td:nth-child(8) {{
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text-muted);
    font-size: 12px;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(88,166,255,0.05); }}
  .hidden {{ display: none; }}
</style>
</head>
<body>
<h1>Claude History Catalog</h1>
<div class="stats">
  <div class="stat-card"><div class="value">{len(projects)}</div><div class="label">Projects</div></div>
  <div class="stat-card"><div class="value">{total_sessions}</div><div class="label">Sessions</div></div>
  <div class="stat-card"><div class="value">{total_messages}</div><div class="label">Messages</div></div>
  <div class="stat-card"><div class="value">{total_errors}</div><div class="label">Errors</div></div>
  <div class="stat-card"><div class="value">{fmt_size_html(total_size)}</div><div class="label">Data Size</div></div>
</div>
<div class="controls">
  <input id="filter" type="text" placeholder="Filter projects..." oninput="filterTable()">
</div>
<table id="catalog-table">
<thead>
<tr>
  <th onclick="sortTable(0)">Project</th>
  <th onclick="sortTable(1)">Sessions</th>
  <th onclick="sortTable(2)">Messages</th>
  <th onclick="sortTable(3)">Tools</th>
  <th onclick="sortTable(4)">Errors</th>
  <th onclick="sortTable(5)">Size</th>
  <th onclick="sortTable(6)">Last Active</th>
  <th onclick="sortTable(7)">Working Directory</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
<script>
(function() {{
  // Format relative times
  function relTime(isoStr) {{
    if (!isoStr) return '-';
    var now = new Date();
    var dt = new Date(isoStr);
    var days = Math.floor((now - dt) / 86400000);
    if (days === 0) return 'today';
    if (days === 1) return 'yesterday';
    if (days < 60) return days + 'd ago';
    return Math.floor(days / 30) + 'mo ago';
  }}
  document.querySelectorAll('.ts').forEach(function(td) {{
    td.textContent = relTime(td.getAttribute('data-ts'));
  }});

  // Filter
  window.filterTable = function() {{
    var q = document.getElementById('filter').value.toLowerCase();
    document.querySelectorAll('#catalog-table tbody tr').forEach(function(tr) {{
      tr.classList.toggle('hidden', q && !tr.textContent.toLowerCase().includes(q));
    }});
  }};

  // Sort
  var sortCol = -1, sortAsc = true;
  window.sortTable = function(col) {{
    var table = document.getElementById('catalog-table');
    var ths = table.querySelectorAll('th');
    ths.forEach(function(th) {{ th.className = ''; }});
    if (sortCol === col) {{ sortAsc = !sortAsc; }} else {{ sortCol = col; sortAsc = true; }}
    ths[col].className = sortAsc ? 'sorted-asc' : 'sorted-desc';

    var tbody = table.querySelector('tbody');
    var rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort(function(a, b) {{
      var av = a.cells[col] ? a.cells[col].textContent.trim() : '';
      var bv = b.cells[col] ? b.cells[col].textContent.trim() : '';
      var an = parseFloat(av.replace(/[^0-9.-]/g, ''));
      var bn = parseFloat(bv.replace(/[^0-9.-]/g, ''));
      var cmp = (!isNaN(an) && !isNaN(bn)) ? an - bn : av.localeCompare(bv);
      return sortAsc ? cmp : -cmp;
    }});
    rows.forEach(function(r) {{ tbody.appendChild(r); }});
  }};
}})();
</script>
</body>
</html>"""
        return html
