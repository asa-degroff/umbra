"""
Messages API Router

Conversation history in chat-style view.
"""

import logging
from fastapi import APIRouter, Query
from dashboard.backend.services.letta_service import get_client, get_agent_id

logger = logging.getLogger("dashboard.api.messages")
router = APIRouter()


def format_message(msg) -> dict:
    """Format a Letta message for the frontend."""
    result = {
        "id": getattr(msg, "id", None),
        "created_at": msg.created_at.isoformat() if hasattr(msg, "created_at") and msg.created_at else None,
    }

    msg_type = msg.__class__.__name__

    if msg_type == "UserMessage":
        result["type"] = "user"
        result["content"] = msg.content if hasattr(msg, "content") else str(msg)
    elif msg_type == "AssistantMessage":
        result["type"] = "assistant"
        result["content"] = msg.content if hasattr(msg, "content") else str(msg)
    elif msg_type == "ReasoningMessage":
        result["type"] = "reasoning"
        result["content"] = msg.reasoning if hasattr(msg, "reasoning") else str(msg)
    elif msg_type == "ToolCallMessage":
        result["type"] = "tool_call"
        result["tool_name"] = getattr(msg, "tool_call", {}).get("name", "unknown") if isinstance(getattr(msg, "tool_call", None), dict) else getattr(getattr(msg, "tool_call", None), "name", "unknown")
        result["arguments"] = getattr(msg, "tool_call", {}).get("arguments", "") if isinstance(getattr(msg, "tool_call", None), dict) else getattr(getattr(msg, "tool_call", None), "arguments", "")
    elif msg_type == "ToolReturnMessage":
        result["type"] = "tool_return"
        result["content"] = getattr(msg, "tool_return", str(msg))
        result["status"] = getattr(msg, "status", "success")
    else:
        result["type"] = "system"
        result["content"] = str(msg)

    return result


@router.get("/")
async def list_messages(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Get paginated message history."""
    try:
        client = get_client()
        agent_id = get_agent_id()

        kwargs = {"agent_id": agent_id, "limit": limit}
        if cursor:
            kwargs["before"] = cursor

        messages = client.agents.messages.list(**kwargs)

        formatted = [format_message(m) for m in messages]
        next_cursor = messages[-1].id if len(messages) == limit else None

        return {
            "messages": formatted,
            "next_cursor": next_cursor,
            "count": len(formatted),
        }
    except Exception as e:
        logger.error(f"Error listing messages: {e}")
        return {"error": str(e)}
