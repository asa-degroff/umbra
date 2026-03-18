"""
WebSocket manager for broadcasting real-time events to frontend clients.
"""

import asyncio
import json
import logging
from collections import deque
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("dashboard.ws")


class WebSocketManager:
    """Manages WebSocket connections and event broadcasting."""

    def __init__(self, history_size: int = 100):
        self.connections: list[WebSocket] = []
        self.event_history: deque = deque(maxlen=history_size)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)
        # Send recent history to new client
        for event in self.event_history:
            try:
                await websocket.send_json(event)
            except Exception:
                break
        logger.info(f"WebSocket client connected ({len(self.connections)} total)")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)
        logger.info(f"WebSocket client disconnected ({len(self.connections)} total)")

    async def broadcast(self, event: dict):
        """Broadcast event to all connected clients."""
        self.event_history.append(event)
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def get_connection_count(self) -> int:
        return len(self.connections)

    def get_recent_events(self, count: int = 50) -> list[dict]:
        return list(self.event_history)[-count:]


ws_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket):
    """Handle a WebSocket connection."""
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
