"""
Umbra Dashboard Backend

FastAPI application for the Umbra operational dashboard.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.backend.websocket import ws_manager, websocket_endpoint
from dashboard.backend.services.event_listener import EventListener

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('dashboard')

# Configuration
EVENT_LISTENER_HOST = os.getenv("EVENT_LISTENER_HOST", "127.0.0.1")
EVENT_LISTENER_PORT = int(os.getenv("EVENT_LISTENER_PORT", "9876"))

# Global event listener
event_listener: EventListener | None = None


async def handle_event(event: dict) -> None:
    """Handle events from bsky.py and broadcast to WebSocket clients."""
    logger.debug(f"Broadcasting event: {event.get('type')}")
    await ws_manager.broadcast(event)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global event_listener
    
    # Start event listener
    event_listener = EventListener(
        host=EVENT_LISTENER_HOST,
        port=EVENT_LISTENER_PORT,
        on_event=handle_event,
    )
    
    # Start listener in background task
    listener_task = asyncio.create_task(event_listener.start())
    logger.info(f"Starting event listener on {EVENT_LISTENER_HOST}:{EVENT_LISTENER_PORT}")

    # Start frontier service initialization in background (non-blocking)
    try:
        from dashboard.backend.services.frontier_service import start_background_init
        start_background_init()
    except Exception as e:
        logger.warning(f"Could not start frontier background init: {e}")

    yield
    
    # Shutdown
    logger.info("Shutting down...")
    if event_listener:
        await event_listener.stop()
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass


# Create FastAPI app
app = FastAPI(
    title="Umbra Dashboard",
    description="Operational dashboard for Umbra",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else [
    "http://localhost:5173",  # Vite dev server
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://192.168.12.134:5173",  # Network access
    "http://192.168.12.134:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    """WebSocket endpoint for real-time events."""
    await websocket_endpoint(websocket)


# Health check
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "websocket_clients": ws_manager.get_connection_count(),
        "event_listener": {
            "running": event_listener.is_running if event_listener else False,
            "clients": event_listener.client_count if event_listener else 0,
        },
    }


# System status
@app.get("/api/system/status")
async def system_status():
    """Get system status."""
    return {
        "dashboard": {
            "websocket_clients": ws_manager.get_connection_count(),
            "event_history_size": len(ws_manager.event_history),
        },
        "event_listener": {
            "host": EVENT_LISTENER_HOST,
            "port": EVENT_LISTENER_PORT,
            "running": event_listener.is_running if event_listener else False,
            "connected_sources": event_listener.client_count if event_listener else 0,
        },
    }


# Recent events
@app.get("/api/events/recent")
async def get_recent_events(count: int = 50):
    """Get recent events from history."""
    return {
        "events": ws_manager.get_recent_events(count),
        "total": len(ws_manager.event_history),
    }


# Import and include routers
from dashboard.backend.routers import semantic, system
app.include_router(semantic.router, prefix="/api/semantic", tags=["semantic"])
app.include_router(system.router, prefix="/api/system", tags=["system"])


# Serve static files in production (frontend build)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the React frontend."""
        # API routes are handled above
        if full_path.startswith("api/") or full_path == "ws":
            return {"error": "Not found"}
        
        # Serve index.html for all other routes (SPA)
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"error": "Frontend not built"}


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8081,
        reload=True,
        log_level="info",
    )
