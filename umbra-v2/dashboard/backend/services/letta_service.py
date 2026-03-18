"""
Shared Letta client wrapper for dashboard API.
"""

import logging
import sys
from pathlib import Path
from functools import lru_cache

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from letta_client import Letta

logger = logging.getLogger("dashboard.letta")

_client: Letta | None = None
_agent_id: str | None = None


def _load_config() -> dict:
    """Load Letta config from config.yaml."""
    from config_loader import get_config, get_letta_config
    # Try bot/config.yaml first, then parent config.yaml
    for path in [
        Path(__file__).parent.parent.parent.parent / "config.yaml",
        Path(__file__).parent.parent.parent.parent / "bot" / "config.yaml",
    ]:
        if path.exists():
            get_config(str(path))
            return get_letta_config()
    raise FileNotFoundError("No config.yaml found")


def get_client() -> Letta:
    """Get or create the shared Letta client."""
    global _client
    if _client is None:
        config = _load_config()
        params = {"timeout": config.get("timeout", 30)}
        if config.get("api_key"):
            params["token"] = config["api_key"]
        if config.get("base_url"):
            params["base_url"] = config["base_url"]
        _client = Letta(**params)
    return _client


def get_agent_id() -> str:
    """Get the configured agent ID."""
    global _agent_id
    if _agent_id is None:
        config = _load_config()
        _agent_id = config["agent_id"]
    return _agent_id
