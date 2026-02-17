"""
Disk Cache for Frontier Service

Persists seeds and zones data to JSON files so the dashboard loads
instantly on startup without needing to regenerate (which requires
LLM model swaps and UMAP computation).
"""

import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path("/home/asa/umbra/data/cache")


class DiskCache:
    """Read/write JSON cache files for frontier data."""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Optional[dict]:
        """
        Load cached data from disk.

        Returns:
            Dict with 'data', 'cached_at', 'config_hash' keys, or None if not found.
        """
        path = self._path(key)
        if not path.exists():
            return None

        try:
            with open(path, "r") as f:
                wrapper = json.load(f)

            # Validate structure
            if not isinstance(wrapper, dict) or "data" not in wrapper:
                logger.warning(f"Disk cache {key}: invalid structure, ignoring")
                return None

            logger.info(
                f"Disk cache hit: {key} "
                f"(cached {wrapper.get('cached_at', 'unknown')})"
            )
            return wrapper

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Disk cache {key}: read error: {e}")
            return None

    def put(self, key: str, data: dict, config_hash: str = "") -> bool:
        """
        Write data to disk cache.

        Args:
            key: Cache key (becomes filename)
            data: The data dict to cache
            config_hash: Optional hash of config (model name, etc.) for staleness detection

        Returns:
            True if written successfully
        """
        wrapper = {
            "data": data,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "config_hash": config_hash,
        }

        path = self._path(key)
        try:
            # Write atomically via temp file
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(wrapper, f, indent=None, default=str)
            tmp_path.rename(path)

            size_kb = path.stat().st_size / 1024
            logger.info(f"Disk cache write: {key} ({size_kb:.1f} KB)")
            return True

        except OSError as e:
            logger.error(f"Disk cache {key}: write error: {e}")
            return False

    def is_fresh(self, key: str, max_age_seconds: int, config_hash: str = "") -> bool:
        """
        Check if cached data exists and is fresh enough.

        Args:
            key: Cache key
            max_age_seconds: Maximum age in seconds before considered stale
            config_hash: If provided, cache is stale if hash doesn't match

        Returns:
            True if cache exists, is recent enough, and config matches
        """
        wrapper = self.get(key)
        if wrapper is None:
            return False

        # Check config hash (model change invalidates cache)
        if config_hash and wrapper.get("config_hash") != config_hash:
            logger.info(f"Disk cache {key}: config hash mismatch, stale")
            return False

        # Check age
        cached_at_str = wrapper.get("cached_at")
        if not cached_at_str:
            return False

        try:
            cached_at = datetime.fromisoformat(cached_at_str)
            age = (datetime.now(timezone.utc) - cached_at).total_seconds()
            if age > max_age_seconds:
                logger.info(f"Disk cache {key}: {age:.0f}s old (max {max_age_seconds}s), stale")
                return False
            return True
        except (ValueError, TypeError):
            return False

    def invalidate(self, key: str) -> bool:
        """Delete a cache entry."""
        path = self._path(key)
        try:
            if path.exists():
                path.unlink()
                logger.info(f"Disk cache invalidated: {key}")
            return True
        except OSError as e:
            logger.warning(f"Disk cache invalidate {key}: {e}")
            return False


def get_config_hash() -> str:
    """
    Generate a hash of the current model config.
    If models change, cached data should be regenerated.
    """
    from semantic_analysis.embeddings import DEFAULT_MODEL as EMBED_MODEL
    from semantic_analysis.analyzer import DEFAULT_LLM_MODEL as LLM_MODEL

    config_str = f"embed={EMBED_MODEL},llm={LLM_MODEL}"
    return hashlib.md5(config_str.encode()).hexdigest()[:12]


# Module-level singleton
disk_cache = DiskCache()
