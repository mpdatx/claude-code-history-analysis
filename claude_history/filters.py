"""Text filtering utilities for Claude history content."""

from __future__ import annotations

import re
from typing import Union


SYSTEM_TAG_RE = re.compile(
    r"<(system-reminder|available-deferred-tools|EXTREMELY_IMPORTANT|command-name|functions|function|task-notification)"
    r"(?:\s[^>]*)?\s*/>"       # self-closing: <tag ... />
    r"|"
    r"<(system-reminder|available-deferred-tools|EXTREMELY_IMPORTANT|command-name|functions|function|task-notification)"
    r"[\s>].*?</\2>",          # paired: <tag ...>...</tag>
    re.DOTALL,
)

INJECTED_PREFIXES = (
    "Base directory for this skill:",
    "# claudeMd",
    "# currentDate",
)

TRUNCATED_PREFIXES = (
    "This session is being continued from a previous conversation",
)


def strip_system_tags(text: str) -> str:
    """Remove system-injected XML blocks from text."""
    return SYSTEM_TAG_RE.sub("", text)


def is_injected_text(text: str) -> bool:
    """Check if text is system/skill injected content rather than user input."""
    stripped = text.strip()
    return any(stripped.startswith(prefix) for prefix in INJECTED_PREFIXES)


def _clean_text(text: str) -> str | None:
    """Clean a single text string: strip injected content, system tags, truncate verbose prefixes."""
    if is_injected_text(text):
        return None
    text = strip_system_tags(text).strip()
    if not text:
        return None
    for prefix in TRUNCATED_PREFIXES:
        if text.startswith(prefix):
            text = text.split("\n", 1)[0]
            break
    return text


def extract_user_text(content: list[dict | str]) -> str:
    """Extract plain text from content array, stripping system-injected content.

    Args:
        content: A list of content items (dicts with type/text keys, or strings).

    Returns:
        Cleaned user text with system artifacts removed.
    """
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            raw = item.get("text", "")
        elif isinstance(item, str):
            raw = item
        else:
            continue
        cleaned = _clean_text(raw)
        if cleaned:
            parts.append(cleaned)
    return " ".join(parts).strip()
