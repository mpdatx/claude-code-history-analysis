"""Timestamp parsing and formatting utilities."""

from datetime import datetime, timedelta


def parse_timestamp(ts_str: str) -> datetime:
    """Parse an ISO timestamp string, handling Z suffix.

    Raises ValueError if ts_str is empty or malformed.
    """
    if not ts_str:
        raise ValueError("empty timestamp string")
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def format_duration(delta: timedelta) -> str:
    """Format a timedelta into a human-readable duration string."""
    mins = int(delta.total_seconds() / 60)
    if mins < 1:
        return "<1 min"
    elif mins < 60:
        return f"{mins} min"
    else:
        hours = mins // 60
        remainder = mins % 60
        return f"{hours}h {remainder}m"
