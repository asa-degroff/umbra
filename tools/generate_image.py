"""
Image Generation Tool

Generate images using AI via the Replicate API with Leonardo AI's Lucid Origin model.
The generated image URL is returned in a signal format that bsky.py detects to
auto-include the image in the agent's next message for visual review.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


class GenerateImageArgs(BaseModel):
    """Arguments for generating an AI image."""

    prompt: str = Field(
        ...,
        description="Detailed prompt for image generation. This will also be used as alt text when attaching to posts."
    )
    aspect_ratio: Optional[str] = Field(
        default="1:1",
        description="Aspect ratio for the generated image. Options: '1:1' (square), '16:9' (landscape), '9:16' (portrait), '4:3', '3:4', '3:2', '2:3'"
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        """Validate that prompt is not empty or too long."""
        if not v or not v.strip():
            raise ValueError("Prompt cannot be empty")
        # Replicate doesn't have a strict limit, but keep reasonable
        if len(v) > 2000:
            raise ValueError("Prompt is too long (max 2000 characters)")
        return v.strip()

    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, v: str) -> str:
        """Validate aspect ratio is supported."""
        valid_ratios = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "4:5", "5:4", "2:1", "1:2"]
        if v not in valid_ratios:
            raise ValueError(f"Invalid aspect ratio '{v}'. Valid options: {', '.join(valid_ratios)}")
        return v


def generate_image(prompt: str, aspect_ratio: str = "1:1") -> str:
    """
    Generate an AI image using Leonardo AI's Lucid Origin model via Replicate.

    The generated image will be automatically shown to you in your next message
    so you can review it before deciding to use it in a post or reply.

    Args:
        prompt: Detailed description of the image to generate. This will also be
                used as alt text when attaching to posts.
        aspect_ratio: Aspect ratio for the image. Default is '1:1' (square).
                      Options: '1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3'

    Returns:
        Signal string containing the image URL and metadata, which triggers
        auto-display of the image in your next message.

    Raises:
        Exception: If the API call fails or credentials are missing.
    """
    import os
    import time

    # Validate inputs
    if not prompt or not prompt.strip():
        raise Exception("Prompt cannot be empty")

    prompt = prompt.strip()

    valid_ratios = ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "4:5", "5:4", "2:1", "1:2"]
    if aspect_ratio not in valid_ratios:
        raise Exception(f"Invalid aspect ratio '{aspect_ratio}'. Valid options: {', '.join(valid_ratios)}")

    # Get API token from environment
    api_token = os.getenv("REPLICATE_API_TOKEN")
    if not api_token:
        raise Exception(
            "REPLICATE_API_TOKEN environment variable not set. "
            "Please add your Replicate API token to config.yaml under image_generation.replicate_api_token"
        )

    try:
        import replicate

        # Set the API token
        replicate_client = replicate.Client(api_token=api_token)

        start_time = time.time()

        # Run the model
        # Leonardo AI Lucid Origin model
        output = replicate_client.run(
            "leonardoai/lucid-origin",
            input={
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "num_images": 1,
                "style": "none",  # Let the prompt control style
                "contrast": "medium",
                "generation_mode": "standard",
                "prompt_enhance": True
            }
        )

        generation_time = time.time() - start_time

        # Extract image URL from output
        # Output is a list of FileOutput objects
        if not output:
            raise Exception("No image was generated. The model returned an empty response.")

        # Get the URL - FileOutput can be converted to URL string
        image_url = str(output[0]) if hasattr(output[0], '__str__') else output[0]

        if not image_url or not image_url.startswith("http"):
            raise Exception(f"Invalid image URL returned: {image_url}")

        # Return the signal format that bsky.py will detect
        # Format: IMAGE_GENERATED|url|prompt|aspect_ratio|generation_time
        # Use a delimiter that won't appear in prompts (unlikely in URLs too)
        signal = f"IMAGE_GENERATED|{image_url}|{prompt}|{aspect_ratio}|{generation_time:.1f}"

        # Add human-readable instructions for the agent
        # The signal must be on the first line for bsky.py detection
        instructions = (
            f"\n\n---\n"
            f"Image generated successfully in {generation_time:.1f}s!\n\n"
            f"To attach this image to your reply, use reply_to_bluesky_post with:\n"
            f"- image_url: {image_url}\n"
            f"- image_alt: {prompt}\n\n"
            f"Or use create_new_bluesky_post with the same image_url and image_alt parameters."
        )

        return signal + instructions

    except ImportError:
        raise Exception(
            "The 'replicate' package is not installed. "
            "Please install it with: uv pip install replicate"
        )
    except replicate.exceptions.ReplicateError as e:
        error_msg = str(e)
        if "rate limit" in error_msg.lower():
            raise Exception(f"Rate limited by Replicate API. Please wait a moment and try again. Details: {error_msg}")
        elif "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
            raise Exception(f"Replicate API authentication failed. Check your API token. Details: {error_msg}")
        else:
            raise Exception(f"Replicate API error: {error_msg}")
    except Exception as e:
        if "IMAGE_GENERATED|" in str(e):
            # This is actually our success signal being raised, shouldn't happen but handle it
            raise
        raise Exception(f"Failed to generate image: {str(e)}")
