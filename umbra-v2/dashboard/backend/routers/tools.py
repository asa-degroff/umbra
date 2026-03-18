"""
Tools API Router

Tool management — list, attach, detach, env vars.
"""

import logging
from fastapi import APIRouter
from dashboard.backend.services.letta_service import get_client, get_agent_id

logger = logging.getLogger("dashboard.api.tools")
router = APIRouter()

# Env var keys that should be redacted in display
REDACT_KEYS = {"BSKY_PASSWORD", "R2_SECRET_ACCESS_KEY", "REPLICATE_API_TOKEN", "BLOCKED_STRINGS", "LETTA_API_KEY"}


@router.get("/attached")
async def list_attached_tools():
    """List tools attached to the agent."""
    try:
        client = get_client()
        agent_id = get_agent_id()
        tools = client.agents.tools.list(agent_id=agent_id)
        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "tags": t.tags if hasattr(t, "tags") else [],
            }
            for t in tools
        ]
    except Exception as e:
        logger.error(f"Error listing attached tools: {e}")
        return {"error": str(e)}


@router.get("/available")
async def list_available_tools():
    """List all tools registered on the Letta server."""
    try:
        client = get_client()
        tools = client.tools.list()
        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "tags": t.tags if hasattr(t, "tags") else [],
            }
            for t in tools
        ]
    except Exception as e:
        logger.error(f"Error listing available tools: {e}")
        return {"error": str(e)}


@router.post("/attach/{tool_id}")
async def attach_tool(tool_id: str):
    """Attach a tool to the agent."""
    try:
        client = get_client()
        agent_id = get_agent_id()
        client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
        return {"status": "attached", "tool_id": tool_id}
    except Exception as e:
        logger.error(f"Error attaching tool: {e}")
        return {"error": str(e)}


@router.post("/detach/{tool_id}")
async def detach_tool(tool_id: str):
    """Detach a tool from the agent."""
    try:
        client = get_client()
        agent_id = get_agent_id()
        client.agents.tools.detach(agent_id=agent_id, tool_id=tool_id)
        return {"status": "detached", "tool_id": tool_id}
    except Exception as e:
        logger.error(f"Error detaching tool: {e}")
        return {"error": str(e)}


@router.get("/env")
async def get_env_vars():
    """Get tool execution environment variables (secrets redacted)."""
    try:
        client = get_client()
        agent_id = get_agent_id()
        agent = client.agents.retrieve(agent_id=agent_id)
        env_vars = getattr(agent, "tool_exec_environment_variables", {}) or {}

        return {
            k: ("***" if k in REDACT_KEYS else v)
            for k, v in env_vars.items()
        }
    except Exception as e:
        logger.error(f"Error getting env vars: {e}")
        return {"error": str(e)}


@router.put("/env")
async def update_env_vars(body: dict):
    """Update tool execution environment variables."""
    try:
        client = get_client()
        agent_id = get_agent_id()

        # Merge with existing — don't overwrite keys sent as "***"
        agent = client.agents.retrieve(agent_id=agent_id)
        existing = getattr(agent, "tool_exec_environment_variables", {}) or {}
        for k, v in body.items():
            if v != "***":
                existing[k] = v

        client.agents.modify(
            agent_id=agent_id,
            tool_exec_environment_variables=existing,
        )
        return {"status": "updated", "count": len(existing)}
    except Exception as e:
        logger.error(f"Error updating env vars: {e}")
        return {"error": str(e)}
