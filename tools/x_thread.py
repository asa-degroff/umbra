"""Thread tool for adding posts to X threads atomically."""
from typing import Optional
from pydantic import BaseModel, Field, validator


class XThreadPostArgs(BaseModel):
    text: str = Field(
        ..., 
        description="Text content for the X post (max 280 characters)"
    )
    
    @validator('text')
    def validate_text_length(cls, v):
        if len(v) > 280:
            raise ValueError(f"Text exceeds 280 character limit (current: {len(v)} characters)")
        return v


def add_post_to_x_thread(text: str) -> str:
    """
    Add a single post to the current X reply thread. This tool indicates to the handler 
    that it should add this post to the ongoing reply thread context when responding to a mention.
    
    This is an atomic operation - each call adds exactly one post. The handler (x_bot.py or similar)
    manages the thread state and ensures proper threading when multiple posts are queued.

    Args:
        text: Text content for the post (max 280 characters)

    Returns:
        Confirmation message that the post has been queued for the reply thread

    Raises:
        Exception: If text exceeds character limit. On failure, the post will be omitted 
                  from the reply thread and the agent may try again with corrected text.
    """
    # Validate input
    if len(text) > 280:
        raise Exception(f"Text exceeds 280 character limit (current: {len(text)} characters). This post will be omitted from the thread. You may try again with shorter text.")
    
    # Return confirmation - the actual posting will be handled by x_bot.py or similar
    return f"X post queued for reply thread: {text[:50]}{'...' if len(text) > 50 else ''}"