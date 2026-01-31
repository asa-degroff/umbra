"""
Text Sanitization Module

Provides functions to filter out problematic strings from text before sending to the LLM.
Blocked strings are loaded from blocked_strings.txt and cached for performance.
"""

import os
import logging
from typing import List, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# Default path to blocked strings file (relative to this module)
DEFAULT_BLOCKED_STRINGS_FILE = os.path.join(os.path.dirname(__file__), "blocked_strings.txt")

# Placeholder text for filtered content
FILTERED_PLACEHOLDER = "[content filtered]"


@lru_cache(maxsize=1)
def _load_blocked_strings_cached(file_path: str, mtime: float) -> List[str]:
    """
    Load blocked strings from file with caching based on modification time.

    Args:
        file_path: Path to the blocked strings file
        mtime: File modification time (used for cache invalidation)

    Returns:
        List of blocked strings
    """
    blocked = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n\r')
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    blocked.append(line)
        if blocked:
            logger.info(f"Loaded {len(blocked)} blocked strings from {file_path}")
    except FileNotFoundError:
        logger.debug(f"Blocked strings file not found: {file_path}")
    except Exception as e:
        logger.warning(f"Error loading blocked strings from {file_path}: {e}")
    return blocked


def load_blocked_strings(file_path: Optional[str] = None) -> List[str]:
    """
    Load blocked strings from the configuration file.

    Uses caching with automatic invalidation when the file is modified.

    Args:
        file_path: Path to blocked strings file (defaults to blocked_strings.txt)

    Returns:
        List of strings to filter out
    """
    if file_path is None:
        file_path = DEFAULT_BLOCKED_STRINGS_FILE

    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        mtime = 0.0

    return _load_blocked_strings_cached(file_path, mtime)


def sanitize_text(text: str, blocked_strings: Optional[List[str]] = None) -> str:
    """
    Sanitize text by replacing blocked strings with a placeholder.

    Args:
        text: The text to sanitize
        blocked_strings: List of strings to filter (loads from file if not provided)

    Returns:
        Sanitized text with blocked strings replaced by [content filtered]
    """
    if not text:
        return text

    if blocked_strings is None:
        blocked_strings = load_blocked_strings()

    if not blocked_strings:
        return text

    result = text
    for blocked in blocked_strings:
        if blocked in result:
            result = result.replace(blocked, FILTERED_PLACEHOLDER)
            logger.debug(f"Filtered blocked string from text")

    return result


def sanitize_dict_text_fields(data: dict, blocked_strings: Optional[List[str]] = None) -> dict:
    """
    Recursively sanitize all string values in a dictionary that might contain post text.

    This is useful for sanitizing entire post/feed data structures.

    Args:
        data: Dictionary potentially containing text fields
        blocked_strings: List of strings to filter (loads from file if not provided)

    Returns:
        Dictionary with text fields sanitized
    """
    if blocked_strings is None:
        blocked_strings = load_blocked_strings()

    if not blocked_strings:
        return data

    if isinstance(data, dict):
        return {k: sanitize_dict_text_fields(v, blocked_strings) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_dict_text_fields(item, blocked_strings) for item in data]
    elif isinstance(data, str):
        return sanitize_text(data, blocked_strings)
    else:
        return data


def clear_cache():
    """Clear the blocked strings cache (useful for testing or after file updates)."""
    _load_blocked_strings_cached.cache_clear()
    logger.debug("Blocked strings cache cleared")
