"""
System API Router

Endpoints for system status, Ollama, memory blocks, etc.
"""

import logging
import sys
from pathlib import Path

import requests
from fastapi import APIRouter

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from dashboard.backend.services.sqlite_service import SQLiteService
from dashboard.backend.services.chromadb_service import ChromaDBService

logger = logging.getLogger('dashboard.api.system')

router = APIRouter()

# Initialize services
sqlite_service = SQLiteService("./queue/notifications.db")
chromadb_service = ChromaDBService()

OLLAMA_URL = "http://localhost:11434"


@router.get("/ollama")
async def get_ollama_status():
    """Get Ollama server status and loaded models."""
    try:
        # Check if Ollama is running
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        models = []
        for model in data.get('models', []):
            models.append({
                "name": model.get("name"),
                "size": model.get("size"),
                "modified_at": model.get("modified_at"),
                "details": model.get("details", {}),
            })
        
        return {
            "status": "running",
            "url": OLLAMA_URL,
            "models": models,
            "model_count": len(models),
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "offline",
            "url": OLLAMA_URL,
            "error": "Cannot connect to Ollama",
        }
    except Exception as e:
        return {
            "status": "error",
            "url": OLLAMA_URL,
            "error": str(e),
        }


@router.get("/databases")
async def get_database_stats():
    """Get statistics for all databases."""
    return {
        "sqlite": sqlite_service.get_stats(),
        "chromadb": chromadb_service.get_stats(),
    }


@router.get("/memory")
async def get_memory_blocks():
    """Get Letta memory block contents."""
    try:
        from config_loader import get_config
        from letta_client import Letta
        
        config = get_config()
        letta_config = config._config.get('letta', {})
        
        client = Letta(
            token=letta_config.get('api_key'),
            timeout=30,
        )
        
        agent_id = letta_config.get('agent_id')
        if not agent_id:
            return {"error": "No agent_id configured"}
        
        # Get agent's memory blocks
        agent = client.agents.retrieve(agent_id)
        
        blocks = []
        if hasattr(agent, 'memory') and agent.memory:
            for block in agent.memory.blocks:
                blocks.append({
                    "label": block.label,
                    "value": block.value[:500] + "..." if len(block.value) > 500 else block.value,
                    "full_length": len(block.value),
                })
        
        return {
            "agent_id": agent_id,
            "agent_name": agent.name if hasattr(agent, 'name') else None,
            "blocks": blocks,
        }
    except Exception as e:
        logger.error(f"Error fetching memory blocks: {e}")
        return {"error": str(e)}


@router.get("/tasks")
async def get_scheduled_tasks():
    """Get scheduled task information."""
    return sqlite_service.get_scheduled_tasks()


@router.get("/threads")
async def get_thread_states():
    """Get thread debounce states."""
    return sqlite_service.get_thread_states()
