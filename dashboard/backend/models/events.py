"""
Event models for the real-time activity stream.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events emitted by bsky.py."""
    NOTIFICATION = "notification"
    RESPONSE = "response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    REASONING = "reasoning"
    STATUS = "status"
    SCHEDULED_TASK = "scheduled_task"
    ERROR = "error"


class BaseEvent(BaseModel):
    """Base event model."""
    type: EventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    

class NotificationEvent(BaseEvent):
    """Incoming Bluesky notification."""
    type: EventType = EventType.NOTIFICATION
    uri: str
    author_handle: str
    author_did: str
    text: str
    reason: str  # mention, reply, like, etc.
    root_uri: Optional[str] = None
    parent_uri: Optional[str] = None


class ResponseEvent(BaseEvent):
    """Umbra's response to a notification."""
    type: EventType = EventType.RESPONSE
    content: str
    thread_uri: Optional[str] = None
    reply_to_uri: Optional[str] = None
    post_uri: Optional[str] = None  # URI of created post


class ToolCallEvent(BaseEvent):
    """Tool invocation by the agent."""
    type: EventType = EventType.TOOL_CALL
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: Optional[str] = None


class ToolResultEvent(BaseEvent):
    """Result of a tool call."""
    type: EventType = EventType.TOOL_RESULT
    name: str
    status: str  # success, error
    result: Optional[str] = None
    error: Optional[str] = None
    call_id: Optional[str] = None


class ReasoningEvent(BaseEvent):
    """Reasoning trace from the agent."""
    type: EventType = EventType.REASONING
    content: str


class StatusEvent(BaseEvent):
    """System status update."""
    type: EventType = EventType.STATUS
    state: str  # idle, processing, waiting
    queue_size: int = 0
    current_task: Optional[str] = None
    details: Optional[dict[str, Any]] = None


class ScheduledTaskEvent(BaseEvent):
    """Scheduled task execution."""
    type: EventType = EventType.SCHEDULED_TASK
    task_name: str
    status: str  # started, completed, failed
    error: Optional[str] = None


class ErrorEvent(BaseEvent):
    """Error event."""
    type: EventType = EventType.ERROR
    message: str
    details: Optional[dict[str, Any]] = None


# Union type for all events
Event = NotificationEvent | ResponseEvent | ToolCallEvent | ToolResultEvent | ReasoningEvent | StatusEvent | ScheduledTaskEvent | ErrorEvent


def parse_event(data: dict) -> Event:
    """Parse a raw event dict into the appropriate event type."""
    event_type = data.get('type')
    
    if event_type == EventType.NOTIFICATION:
        return NotificationEvent(**data)
    elif event_type == EventType.RESPONSE:
        return ResponseEvent(**data)
    elif event_type == EventType.TOOL_CALL:
        return ToolCallEvent(**data)
    elif event_type == EventType.TOOL_RESULT:
        return ToolResultEvent(**data)
    elif event_type == EventType.REASONING:
        return ReasoningEvent(**data)
    elif event_type == EventType.STATUS:
        return StatusEvent(**data)
    elif event_type == EventType.SCHEDULED_TASK:
        return ScheduledTaskEvent(**data)
    elif event_type == EventType.ERROR:
        return ErrorEvent(**data)
    else:
        raise ValueError(f"Unknown event type: {event_type}")
