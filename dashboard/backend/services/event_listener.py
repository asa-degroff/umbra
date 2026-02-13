"""
Event Listener Service

TCP socket server that receives events from bsky.py and broadcasts
them to connected WebSocket clients.
"""

import asyncio
import json
import logging
from typing import Callable, Optional
from datetime import datetime

logger = logging.getLogger('dashboard.event_listener')


class EventListener:
    """
    TCP socket server that listens for events from bsky.py.
    
    Events are JSON objects terminated by newlines.
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9876,
        on_event: Optional[Callable[[dict], None]] = None,
    ):
        """
        Initialize the event listener.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            on_event: Callback for received events
        """
        self.host = host
        self.port = port
        self.on_event = on_event
        self.server: Optional[asyncio.Server] = None
        self.clients: set[asyncio.StreamWriter] = set()
        self._running = False
    
    async def start(self) -> None:
        """Start the TCP server."""
        self.server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
        )
        self._running = True
        
        addrs = ', '.join(str(sock.getsockname()) for sock in self.server.sockets)
        logger.info(f"Event listener started on {addrs}")
        
        async with self.server:
            await self.server.serve_forever()
    
    async def stop(self) -> None:
        """Stop the TCP server."""
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Event listener stopped")
    
    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a connected client (bsky.py)."""
        addr = writer.get_extra_info('peername')
        logger.info(f"Event source connected: {addr}")
        self.clients.add(writer)
        
        try:
            while self._running:
                # Read line-delimited JSON (timeout prevents stale connections)
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=60.0)
                except asyncio.TimeoutError:
                    logger.debug(f"Read timeout from {addr}, sending keepalive check")
                    continue
                if not line:
                    break
                
                try:
                    data = json.loads(line.decode('utf-8').strip())
                    
                    # Add server timestamp if not present
                    if 'timestamp' not in data:
                        data['timestamp'] = datetime.utcnow().isoformat()
                    
                    logger.debug(f"Received event: {data.get('type')}")
                    
                    # Call the event handler
                    if self.on_event:
                        try:
                            # Handle both sync and async callbacks
                            result = self.on_event(data)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error(f"Error in event handler: {e}")
                            
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from {addr}: {e}")
                except Exception as e:
                    logger.error(f"Error processing event: {e}")
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Client connection error: {e}")
        finally:
            self.clients.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info(f"Event source disconnected: {addr}")
    
    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._running and self.server is not None
    
    @property
    def client_count(self) -> int:
        """Get the number of connected event sources."""
        return len(self.clients)


async def create_event_listener(
    host: str = "127.0.0.1",
    port: int = 9876,
    on_event: Optional[Callable[[dict], None]] = None,
) -> EventListener:
    """
    Create and return an event listener (but don't start it).
    
    Use `await listener.start()` to begin listening.
    """
    return EventListener(host, port, on_event)
