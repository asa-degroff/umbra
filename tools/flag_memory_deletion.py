"""Flag archival memory for deletion tool."""
from pydantic import BaseModel, Field


class FlagArchivalMemoryForDeletionArgs(BaseModel):
    memory_text: str = Field(
        ...,
        description="The exact text content of the archival memory to delete"
    )


def flag_archival_memory_for_deletion(memory_text: str) -> str:
    """
    Flag an archival memory for deletion based on its exact text content.

    This is a "dummy" tool that doesn't directly delete memories but signals to the system
    that the specified memory should be deleted at the end of the turn (if no halt_activity
    has been received).

    The system will search for all archival memories with this exact text and delete them.

    Args:
        memory_text: The exact text content of the archival memory to delete

    Returns:
        Confirmation message
    """
    # This is a dummy tool - it just returns a confirmation
    # The actual deletion will be handled by the bot loop after the agent's turn completes
    return f"Memory flagged for deletion. Will be removed at the end of this turn if no halt is received."
