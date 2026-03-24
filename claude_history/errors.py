"""Error classification for Claude tool failures."""

import re
from enum import Enum
from typing import Optional, Tuple


class ErrorCategory(Enum):
    """Categories of tool errors."""
    EXIT_CODE = "exit_code"
    TOKEN_LIMIT = "token_limit"
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    NETWORK = "network"
    SIBLING_ERROR = "sibling_error"
    UNKNOWN_SKILL = "unknown_skill"
    OTHER = "other"


def classify_error(error_text: str) -> Tuple[ErrorCategory, Optional[int]]:
    """Classify error type and extract exit code if present.

    Returns (category, exit_code) where exit_code is only set for EXIT_CODE category.
    """
    error_lower = error_text.lower()

    # Exit code errors
    match = re.search(r"exit code (\d+)", error_text, re.I)
    if match:
        return ErrorCategory.EXIT_CODE, int(match.group(1))

    # Token limit
    if "exceeds maximum allowed tokens" in error_text or "token limit" in error_lower:
        return ErrorCategory.TOKEN_LIMIT, None

    # Validation
    if "inputvalidationerror" in error_lower or "validation" in error_lower:
        return ErrorCategory.VALIDATION, None

    # Timeout
    if "timeout" in error_lower or "timed out" in error_lower:
        return ErrorCategory.TIMEOUT, None

    # Permission
    if "permission" in error_lower or "denied" in error_lower:
        return ErrorCategory.PERMISSION, None

    # Not found
    if "not found" in error_lower or "no such" in error_lower:
        return ErrorCategory.NOT_FOUND, None

    # Network
    if "network" in error_lower or "request failed" in error_lower or "http error" in error_lower or "connection refused" in error_lower or "connection reset" in error_lower:
        return ErrorCategory.NETWORK, None

    # Sibling error
    if "sibling tool call errored" in error_lower:
        return ErrorCategory.SIBLING_ERROR, None

    # Unknown skill
    if "unknown skill" in error_lower:
        return ErrorCategory.UNKNOWN_SKILL, None

    return ErrorCategory.OTHER, None
