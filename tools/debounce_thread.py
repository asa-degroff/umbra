"""Thread debouncing tool for deferring responses to incomplete threads."""
from pydantic import BaseModel, Field
from typing import Optional


class DebounceThreadArgs(BaseModel):
    notification_uri: str = Field(..., description="The URI of the notification to debounce (e.g., 'at://did:plc:abc123/app.bsky.feed.post/xyz789')")
    debounce_seconds: Optional[int] = Field(600, description="How many seconds to wait before processing (default: 600 = 10 minutes)")
    reason: Optional[str] = Field("incomplete_thread", description="Reason for debouncing (default: 'incomplete_thread')")


def debounce_thread(notification_uri: str, agent_state: "AgentState", debounce_seconds: int = 600, reason: str = "incomplete_thread") -> str:
    """
    Mark a notification for later processing to allow a multi-post thread to complete.

    Use this tool when you receive a notification that appears to be the first part of an
    incomplete thread. The notification will be revisited after the debounce period, allowing
    you to see the complete thread context before responding.

    Thread indicators to look for:
    - Thread emoji (🧵) in the post
    - Phrases like "thread incoming", "a thread", "🧵👇"
    - Numbered posts (1/5, 1/n, etc.)
    - Incomplete thoughts or sentences that suggest continuation
    - Author pattern of posting multi-post threads

    Args:
        notification_uri: The URI of the notification to debounce
        debounce_seconds: How long to wait before processing (default: 600 = 10 minutes)
        reason: Reason for debouncing (default: 'incomplete_thread')
        agent_state: The agent state object

    Returns:
        String confirming the notification will be debounced (actual debouncing handled by bsky.py)
    """
    # This tool returns a signal message. The actual debouncing is handled by bsky.py
    # when it detects this tool was called, similar to how halt_activity works.
    minutes = debounce_seconds // 60
    time_msg = f"{minutes} minutes" if minutes > 0 else f"{debounce_seconds} seconds"

    return f"DEBOUNCE_REQUESTED|{notification_uri}|{debounce_seconds}|{reason}|Will revisit this thread in {time_msg} to see the complete context before responding."
