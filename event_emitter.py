"""
Event Emitter for Umbra Dashboard

Sends events from bsky.py to the dashboard backend via TCP socket.
Falls back gracefully if the dashboard is not running.
"""

import asyncio
import json
import logging
import socket
import threading
from datetime import datetime
from typing import Any, Optional
from queue import Queue, Empty

logger = logging.getLogger('umbra.event_emitter')


class EventEmitter:
    """
    Emits events to the Umbra dashboard via TCP socket.
    
    Features:
    - Automatic reconnection if connection drops
    - Queue-based async sending to avoid blocking main loop
    - Graceful fallback if dashboard is not running
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9876,
        reconnect_interval: float = 5.0,
        enabled: bool = True,
    ):
        """
        Initialize the event emitter.
        
        Args:
            host: Dashboard backend host
            port: Dashboard event listener port
            reconnect_interval: Seconds between reconnection attempts
            enabled: Whether to emit events
        """
        self.host = host
        self.port = port
        self.reconnect_interval = reconnect_interval
        self.enabled = enabled
        
        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._running = False
        self._queue: Queue[dict] = Queue()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
    
    def start(self) -> None:
        """Start the event emitter background thread."""
        if not self.enabled:
            logger.info("Event emitter disabled")
            return
        
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"Event emitter started (target: {self.host}:{self.port})")
    
    def stop(self) -> None:
        """Stop the event emitter."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self._disconnect()
        logger.info("Event emitter stopped")
    
    def emit(self, event_type: str, **data: Any) -> None:
        """
        Emit an event to the dashboard.
        
        Args:
            event_type: Type of event (notification, response, tool_call, etc.)
            **data: Event data
        """
        if not self.enabled or not self._running:
            return
        
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            **data,
        }
        
        # Non-blocking queue put
        try:
            self._queue.put_nowait(event)
        except Exception:
            pass  # Queue full, drop event
    
    def emit_notification(
        self,
        uri: str,
        author_handle: str,
        author_did: str,
        text: str,
        reason: str,
        root_uri: Optional[str] = None,
        parent_uri: Optional[str] = None,
    ) -> None:
        """Emit a notification event."""
        self.emit(
            "notification",
            uri=uri,
            author_handle=author_handle,
            author_did=author_did,
            text=text[:500],  # Truncate for dashboard
            reason=reason,
            root_uri=root_uri,
            parent_uri=parent_uri,
        )
    
    def emit_response(
        self,
        content: str,
        thread_uri: Optional[str] = None,
        reply_to_uri: Optional[str] = None,
        post_uri: Optional[str] = None,
    ) -> None:
        """Emit a response event."""
        self.emit(
            "response",
            content=content[:500],
            thread_uri=thread_uri,
            reply_to_uri=reply_to_uri,
            post_uri=post_uri,
        )
    
    def emit_tool_call(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: Optional[str] = None,
    ) -> None:
        """Emit a tool call event."""
        # Truncate large arguments
        args_str = json.dumps(arguments)
        if len(args_str) > 500:
            arguments = {"_truncated": args_str[:500] + "..."}
        
        self.emit(
            "tool_call",
            name=name,
            arguments=arguments,
            call_id=call_id,
        )
    
    def emit_tool_result(
        self,
        name: str,
        status: str,
        result: Optional[str] = None,
        error: Optional[str] = None,
        call_id: Optional[str] = None,
    ) -> None:
        """Emit a tool result event."""
        self.emit(
            "tool_result",
            name=name,
            status=status,
            result=result[:200] if result else None,
            error=error,
            call_id=call_id,
        )
    
    def emit_reasoning(self, content: str) -> None:
        """Emit a reasoning event."""
        self.emit(
            "reasoning",
            content=content[:1000],  # Truncate long reasoning
        )
    
    def emit_status(
        self,
        state: str,
        queue_size: int = 0,
        current_task: Optional[str] = None,
        **details: Any,
    ) -> None:
        """Emit a status event."""
        self.emit(
            "status",
            state=state,
            queue_size=queue_size,
            current_task=current_task,
            details=details if details else None,
        )
    
    def emit_scheduled_task(
        self,
        task_name: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Emit a scheduled task event."""
        self.emit(
            "scheduled_task",
            task_name=task_name,
            status=status,
            error=error,
        )
    
    def emit_error(self, message: str, **details: Any) -> None:
        """Emit an error event."""
        self.emit(
            "error",
            message=message,
            details=details if details else None,
        )
    
    def _run(self) -> None:
        """Background thread main loop."""
        while self._running:
            # Try to connect if not connected
            if not self._connected:
                self._connect()
            
            # Process queue
            try:
                event = self._queue.get(timeout=0.1)
                self._send(event)
            except Empty:
                continue
            except Exception as e:
                logger.debug(f"Queue error: {e}")
    
    def _connect(self) -> None:
        """Attempt to connect to the dashboard."""
        try:
            with self._lock:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(5.0)
                self._socket.connect((self.host, self.port))
                self._connected = True
            logger.info(f"Connected to dashboard at {self.host}:{self.port}")
        except Exception as e:
            logger.debug(f"Dashboard not available: {e}")
            self._disconnect()
            # Wait before retry
            for _ in range(int(self.reconnect_interval * 10)):
                if not self._running:
                    return
                threading.Event().wait(0.1)
    
    def _disconnect(self) -> None:
        """Disconnect from the dashboard."""
        with self._lock:
            if self._socket:
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None
            self._connected = False
    
    def _send(self, event: dict) -> None:
        """Send an event to the dashboard."""
        if not self._connected or not self._socket:
            return
        
        try:
            data = json.dumps(event) + "\n"
            with self._lock:
                self._socket.sendall(data.encode('utf-8'))
        except Exception as e:
            logger.debug(f"Send failed: {e}")
            self._disconnect()
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to the dashboard."""
        return self._connected


# Global event emitter instance
_emitter: Optional[EventEmitter] = None


def get_emitter(
    host: str = "127.0.0.1",
    port: int = 9876,
    enabled: bool = True,
) -> EventEmitter:
    """
    Get or create the global event emitter.
    
    Args:
        host: Dashboard backend host
        port: Dashboard event listener port
        enabled: Whether to emit events
        
    Returns:
        EventEmitter instance
    """
    global _emitter
    if _emitter is None:
        _emitter = EventEmitter(host, port, enabled=enabled)
    return _emitter


def emit(event_type: str, **data: Any) -> None:
    """
    Convenience function to emit an event.
    
    Only works if the emitter has been initialized with get_emitter().
    """
    if _emitter:
        _emitter.emit(event_type, **data)
