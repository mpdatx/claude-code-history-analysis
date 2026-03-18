"""Claude history analysis library."""

from claude_history.discovery import HISTORY_ROOT, find_projects_dir, find_project, list_projects
from claude_history.errors import ErrorCategory, classify_error
from claude_history.filters import strip_system_tags, is_injected_text, extract_user_text
from claude_history.parsing import find_history_files, iter_jsonl, iter_session_events
from claude_history.timestamps import parse_timestamp, format_duration
from claude_history.catalog import CatalogDB

__all__ = [
    "HISTORY_ROOT",
    "find_projects_dir",
    "find_project",
    "list_projects",
    "ErrorCategory",
    "classify_error",
    "strip_system_tags",
    "is_injected_text",
    "extract_user_text",
    "find_history_files",
    "iter_jsonl",
    "iter_session_events",
    "parse_timestamp",
    "format_duration",
    "CatalogDB",
]
