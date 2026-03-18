"""
Tasks API Router

Scheduled task status and control — reads from bot's SQLite DB.
"""

import logging
from fastapi import APIRouter
from dashboard.backend.services.sqlite_service import SQLiteService

logger = logging.getLogger("dashboard.api.tasks")
router = APIRouter()

sqlite_service = SQLiteService("./queue/notifications.db")


@router.get("/")
async def list_tasks():
    """Get all scheduled tasks with their state."""
    return sqlite_service.get_scheduled_tasks()


@router.get("/threads")
async def list_thread_states():
    """Get active thread debounce states."""
    return sqlite_service.get_thread_states()
