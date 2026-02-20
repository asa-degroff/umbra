"""
Discovery Event Emitter

Bridges the synchronous discovery pipeline with the async WebSocket manager,
broadcasting real-time progress events to connected dashboard clients.
"""

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger('dashboard.discovery_emitter')


class DiscoveryEventEmitter:
    """
    Emits discovery progress events to WebSocket clients.

    Designed to be called from synchronous code (the discovery pipeline
    runs in a background thread). Uses asyncio event loop bridging
    to broadcast via the async WebSocket manager.
    """

    def __init__(self, ws_manager):
        """
        Args:
            ws_manager: The WebSocketManager instance to broadcast through.
        """
        self.ws_manager = ws_manager
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Try to get the running event loop (may not exist in background thread)
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

    def emit(self, event_type: str, data: Optional[dict[str, Any]] = None):
        """
        Emit a discovery event.

        Safe to call from any thread. If no event loop is available,
        the event is silently dropped (no crash).

        Args:
            event_type: Event type (e.g., 'discovery:llm_result')
            data: Event payload
        """
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(data or {}),
        }

        logger.debug(f"Emitting {event_type}: {data}")

        # Try multiple strategies to broadcast
        try:
            loop = self._loop or self._find_loop()
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.ws_manager.broadcast(event), loop
                )
            else:
                # Fallback: try creating a new loop (shouldn't happen often)
                asyncio.run(self.ws_manager.broadcast(event))
        except Exception as e:
            # Never crash the discovery pipeline for a broadcast failure
            logger.debug(f"Failed to emit {event_type}: {e}")

    def _find_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Try to find a running event loop."""
        try:
            loop = asyncio.get_running_loop()
            self._loop = loop
            return loop
        except RuntimeError:
            pass

        # Try to get the loop from the main thread
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._loop = loop
                return loop
        except RuntimeError:
            pass

        return None

    # --- Convenience methods for common events ---

    def discovery_started(self, params: dict):
        self.emit("discovery:started", {"params": params})

    def seed_exploring(self, seed_id: str, seed_label: str, seed_type: str):
        self.emit("discovery:seed_exploring", {
            "seed_id": seed_id,
            "seed_label": seed_label,
            "seed_type": seed_type,
        })

    def zone_exploring(self, zone_id: str, seed_label: Optional[str] = None):
        self.emit("discovery:zone_exploring", {
            "zone_id": zone_id,
            "seed_label": seed_label,
        })

    def llm_generating(self, context_preview: str):
        self.emit("discovery:llm_generating", {
            "context_preview": context_preview[:200],
        })

    def llm_result(self, queries: list[str], is_fallback: bool = False):
        self.emit("discovery:llm_result", {
            "queries": queries,
            "is_fallback": is_fallback,
        })

    def llm_detail(
        self,
        prompt: str,
        raw_response: str,
        parsed_queries: list[str],
        model: str,
        is_fallback: bool = False,
        seed_label: Optional[str] = None,
    ):
        """Emit full LLM prompt and response for dashboard inspection."""
        self.emit("discovery:llm_detail", {
            "prompt": prompt,
            "raw_response": raw_response,
            "parsed_queries": parsed_queries,
            "model": model,
            "is_fallback": is_fallback,
            "seed_label": seed_label,
        })

    def provider_searching(self, provider: str, query: str):
        self.emit("discovery:provider_searching", {
            "provider": provider,
            "query": query,
        })

    def provider_result(self, provider: str, query: str, count: int, titles: list[str]):
        self.emit("discovery:provider_result", {
            "provider": provider,
            "query": query,
            "count": count,
            "titles": titles[:5],
        })

    def source_scored(self, title: str, relevance: float, status: str, source_type: str):
        self.emit("discovery:source_scored", {
            "title": title,
            "relevance": round(relevance, 3),
            "status": status,
            "source_type": source_type,
        })

    def round_complete(self, round_num: int, total_rounds: int, sources_so_far: int, zones_explored: int):
        self.emit("discovery:round_complete", {
            "round": round_num,
            "total_rounds": total_rounds,
            "sources_so_far": sources_so_far,
            "zones_explored": zones_explored,
        })

    def discovery_complete(self, frontier_count: int, pending_count: int, total: int, zones: int, rounds: int):
        self.emit("discovery:complete", {
            "frontier_count": frontier_count,
            "pending_count": pending_count,
            "total": total,
            "zones_explored": zones,
            "rounds_completed": rounds,
        })

    def discovery_error(self, message: str):
        self.emit("discovery:error", {"message": message})
