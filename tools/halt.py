"""Halt tool for terminating bsky.py activity."""
from pydantic import BaseModel, Field


class HaltArgs(BaseModel):
    reason: str = Field(
        default="User requested halt",
        description="Optional reason for halting activity"
    )


def halt_activity(reason: str = "User requested halt") -> str:
    """
    Signal to halt all bot activity and terminate bsky.py.
    
    This tool allows the agent to request termination of the bot process.
    The actual termination is handled externally by bsky.py when it detects
    this tool being called.
    
    Args:
        reason: Optional reason for halting (default: "User requested halt")
    
    Returns:
        Halt signal message
    """
    return f"Halting activity: {reason}"