"""
System API Router

Health checks, agent info, service status.
"""

import logging
import requests
from fastapi import APIRouter
from dashboard.backend.services.letta_service import get_client, get_agent_id
from dashboard.backend.services.sqlite_service import SQLiteService

logger = logging.getLogger("dashboard.api.system")
router = APIRouter()

OLLAMA_URL = "http://localhost:11434"
LETTA_URL = "http://localhost:8283"
PROXY_URL = "http://localhost:3456"

sqlite_service = SQLiteService("./queue/notifications.db")


@router.get("/health")
async def health():
    """Combined health check for all services."""
    results = {}

    # Letta server
    try:
        resp = requests.get(f"{LETTA_URL}/v1/health", timeout=3)
        results["letta"] = {"status": "ok" if resp.ok else "error"}
    except Exception:
        results["letta"] = {"status": "down"}

    # Ollama
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        data = resp.json()
        results["ollama"] = {
            "status": "ok",
            "models": [m["name"] for m in data.get("models", [])],
        }
    except Exception:
        results["ollama"] = {"status": "down"}

    # Claude proxy
    try:
        resp = requests.get(f"{PROXY_URL}/v1/models", timeout=3)
        results["proxy"] = {"status": "ok" if resp.ok else "error"}
    except Exception:
        results["proxy"] = {"status": "down"}

    # SQLite DB
    results["database"] = sqlite_service.get_stats()

    return results


@router.get("/agent")
async def agent_info():
    """Get agent information."""
    try:
        client = get_client()
        agent_id = get_agent_id()
        agent = client.agents.retrieve(agent_id=agent_id)
        return {
            "id": agent.id,
            "name": agent.name,
            "description": getattr(agent, "description", None),
            "model": getattr(agent.llm_config, "model", None) if hasattr(agent, "llm_config") else None,
            "embedding_model": getattr(agent.embedding_config, "embedding_model", None) if hasattr(agent, "embedding_config") else None,
            "created_at": agent.created_at.isoformat() if hasattr(agent, "created_at") and agent.created_at else None,
        }
    except Exception as e:
        logger.error(f"Error getting agent info: {e}")
        return {"error": str(e)}
