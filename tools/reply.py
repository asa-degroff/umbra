"""Reply tool for Bluesky - a simple tool for the Letta agent to indicate a reply."""
from pydantic import BaseModel, Field, validator


class ReplyArgs(BaseModel):
    message: str = Field(
        ..., 
        description="The reply message text (max 300 characters)"
    )
    
    @validator('message')
    def validate_message_length(cls, v):
        if len(v) > 300:
            raise ValueError(f"Message cannot be longer than 300 characters (current: {len(v)} characters)")
        return v


def bluesky_reply(message: str) -> str:
    """
    This is a simple function that returns a string. MUST be less than 300 characters.
    
    Args:
        message: The reply text (max 300 characters)
        
    Returns:
        Confirmation message
        
    Raises:
        Exception: If message exceeds 300 characters
    """
    if len(message) > 300:
        raise Exception(f"Message cannot be longer than 300 characters (current: {len(message)} characters)")
    
    return 'Reply sent'