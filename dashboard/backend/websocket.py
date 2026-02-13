"""
WebSocket Manager

Manages WebSocket connections from the React frontend and broadcasts
events received from bsky.py.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger('dashboard.websocket')


class WebSocketManager:
    """
    Manages WebSocket connections and broadcasts events to all clients.
    """
    
    def __init__(self, max_history: int = 100):
        """
        Initialize the WebSocket manager.
        
        Args:
            max_history: Maximum events to keep in history for new connections
        """
        self.active_connections: set[WebSocket] = set()
        self.event_history: list[dict] = []
        self.max_history = max_history
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept a new WebSocket connection.
        
        Sends recent event history to the new client.
        """
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")
        
        # Send recent history to new client
        if self.event_history:
            try:
                await websocket.send_json({
                    "type": "history",
                    "events": self.event_history[-50:],  # Last 50 events
                })
            except Exception as e:
                logger.warning(f"Failed to send history: {e}")
    
    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, event: dict) -> None:
        """
        Broadcast an event to all connected clients.
        
        Args:
            event: Event dict to broadcast
        """
        # Add to history
        async with self._lock:
            self.event_history.append(event)
            if len(self.event_history) > self.max_history:
                self.event_history = self.event_history[-self.max_history:]
        
        if not self.active_connections:
            return
        
        # Broadcast to all clients
        message = json.dumps(event, default=str)
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                disconnected.add(connection)
        
        # Remove disconnected clients
        self.active_connections -= disconnected
    
    async def broadcast_event(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Broadcast a typed event.
        
        Args:
            event_type: Type of event
            data: Event data
        """
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            **data,
        }
        await self.broadcast(event)
    
    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.active_connections)
    
    def get_recent_events(self, count: int = 50) -> list[dict]:
        """Get recent events from history."""
        return self.event_history[-count:]
    
    def clear_history(self) -> None:
        """Clear event history."""
        self.event_history.clear()


# Global WebSocket manager instance
ws_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint handler for FastAPI.
    
    Usage in FastAPI:
        @app.websocket("/ws")
        async def websocket_route(websocket: WebSocket):
            await websocket_endpoint(websocket)
    """
    await ws_manager.connect(websocket)
    
    try:
        while True:
            # Keep connection alive, handle any client messages
            data = await websocket.receive_text()
            
            # Handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
            
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)
