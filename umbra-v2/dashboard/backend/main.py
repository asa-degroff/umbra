"""
Umbra V2 Dashboard Backend

FastAPI application with Letta agent management, real-time events, and bot monitoring.
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

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.backend.websocket import ws_manager, websocket_endpoint
from dashboard.backend.services.event_listener import EventListener

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("dashboard")

EVENT_LISTENER_HOST = os.getenv("EVENT_LISTENER_HOST", "127.0.0.1")
EVENT_LISTENER_PORT = int(os.getenv("EVENT_LISTENER_PORT", "9876"))

event_listener: EventListener | None = None


async def handle_event(event: dict) -> None:
    await ws_manager.broadcast(event)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global event_listener
    event_listener = EventListener(
        host=EVENT_LISTENER_HOST,
        port=EVENT_LISTENER_PORT,
        on_event=handle_event,
    )
    listener_task = asyncio.create_task(event_listener.start())
    logger.info(f"Event listener on {EVENT_LISTENER_HOST}:{EVENT_LISTENER_PORT}")
    yield
    if event_listener:
        await event_listener.stop()
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Umbra V2 Dashboard", version="0.2.0", lifespan=lifespan)

# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# WebSocket
@app.websocket("/ws")
async def ws_route(websocket: WebSocket):
    await websocket_endpoint(websocket)


# Health
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "ws_clients": ws_manager.get_connection_count(),
        "event_listener": event_listener.is_running if event_listener else False,
    }


# Recent events
@app.get("/api/events/recent")
async def recent_events(count: int = 50):
    return {"events": ws_manager.get_recent_events(count)}


# Routers
from dashboard.backend.routers import memory, messages, tools, tasks, system

app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(system.router, prefix="/api/system", tags=["system"])


# Static frontend in production
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path == "ws":
            return {"error": "Not found"}
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"error": "Frontend not built"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8081, reload=True, log_level="info")
