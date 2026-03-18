"""
Event listener service — receives JSON events from bsky.py over TCP.
"""

import asyncio
import json
import logging
from typing import Callable, Awaitable

logger = logging.getLogger("dashboard.events")


class EventListener:
    """Async TCP server that receives line-delimited JSON events from bsky.py."""

    def __init__(self, host: str, port: int, on_event: Callable[[dict], Awaitable[None]]):
        self.host = host
        self.port = port
        self.on_event = on_event
        self.is_running = False
        self.client_count = 0
        self._server = None

    async def start(self):
        """Start the TCP server."""
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        self.is_running = True
        logger.info(f"Event listener started on {self.host}:{self.port}")
        async with self._server:
            await self._server.serve_forever()

    async def stop(self):
        """Stop the TCP server."""
        self.is_running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a connected client (bsky.py)."""
        self.client_count += 1
        addr = writer.get_extra_info("peername")
        logger.info(f"Event source connected: {addr}")
        try:
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=120)
                if not line:
                    break
                try:
                    event = json.loads(line.decode().strip())
                    if event.get("type") != "keepalive":
                        await self.on_event(event)
                except json.JSONDecodeError:
                    pass
        except (asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            self.client_count -= 1
            writer.close()
            logger.info(f"Event source disconnected: {addr}")
