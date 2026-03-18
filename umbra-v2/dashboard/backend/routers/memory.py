"""
Memory API Router

Core memory blocks CRUD + archival memory browse/search.
"""

import logging
from fastapi import APIRouter, Query
from dashboard.backend.services.letta_service import get_client, get_agent_id

logger = logging.getLogger("dashboard.api.memory")
router = APIRouter()


@router.get("/blocks")
async def list_blocks():
    """Get all core memory blocks with full content."""
    try:
        client = get_client()
        agent_id = get_agent_id()
        blocks = client.agents.blocks.list(agent_id=agent_id)
        return [
            {
                "id": block.id,
                "label": block.label,
                "value": block.value,
                "limit": block.limit,
                "length": len(block.value) if block.value else 0,
            }
            for block in blocks
        ]
    except Exception as e:
        logger.error(f"Error listing blocks: {e}")
        return {"error": str(e)}


@router.put("/blocks/{block_id}")
async def update_block(block_id: str, body: dict):
    """Update a core memory block's value."""
    try:
        client = get_client()
        updated = client.blocks.modify(
            block_id=block_id,
            value=body["value"],
        )
        return {
            "id": updated.id,
            "label": updated.label,
            "value": updated.value,
            "limit": updated.limit,
            "length": len(updated.value) if updated.value else 0,
        }
    except Exception as e:
        logger.error(f"Error updating block: {e}")
        return {"error": str(e)}


@router.get("/archival")
async def list_archival(
    query: str | None = Query(None, description="Search query"),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Browse or search archival memory passages."""
    try:
        client = get_client()
        agent_id = get_agent_id()
        kwargs = {"agent_id": agent_id, "limit": limit}
        if cursor:
            kwargs["cursor"] = cursor
        if query:
            kwargs["query_text"] = query

        passages = client.agents.passages.list(**kwargs)
        next_cursor = passages[-1].id if len(passages) == limit else None

        return {
            "passages": [
                {
                    "id": p.id,
                    "text": p.text,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in passages
            ],
            "next_cursor": next_cursor,
            "count": len(passages),
        }
    except Exception as e:
        logger.error(f"Error listing archival: {e}")
        return {"error": str(e)}


@router.delete("/archival/{passage_id}")
async def delete_passage(passage_id: str):
    """Delete an archival memory passage."""
    try:
        client = get_client()
        agent_id = get_agent_id()
        client.agents.passages.delete(agent_id=agent_id, passage_id=passage_id)
        return {"status": "deleted", "id": passage_id}
    except Exception as e:
        logger.error(f"Error deleting passage: {e}")
        return {"error": str(e)}
