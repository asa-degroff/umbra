"""
Image Utilities Module

Shared utilities for image handling across umbra, including:
- Downloading images and converting to base64
- Parsing IMAGE_GENERATED signals from the generate_image tool
- Sending image review follow-up messages to the agent
"""

import logging
import time
import json
from typing import Optional
from dataclasses import dataclass

from letta_client import Letta

logger = logging.getLogger('umbra')


@dataclass
class GeneratedImage:
    """Container for generated image data."""
    url: str
    prompt: str
    aspect_ratio: str
    generation_time: str


def download_image_as_base64(url: str, timeout: int = 30) -> tuple[str, str] | None:
    """Download an image from URL and convert to base64.

    Args:
        url: The image URL to download
        timeout: Request timeout in seconds

    Returns:
        Tuple of (base64_data, media_type) or None if failed
    """
    import requests
    import base64

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        image_data = response.content

        # Detect media type from magic bytes (file signature), NOT URL or headers
        # This is critical because Replicate URLs may have .png extension but serve JPEG
        if image_data[:8] == b'\x89PNG\r\n\x1a\n':
            media_type = 'image/png'
        elif image_data[:3] == b'\xff\xd8\xff':
            media_type = 'image/jpeg'
        elif image_data[:6] in (b'GIF87a', b'GIF89a'):
            media_type = 'image/gif'
        elif image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
            media_type = 'image/webp'
        else:
            # Default to JPEG if unknown (most common for AI-generated images)
            media_type = 'image/jpeg'
            logger.warning(
                f"Unknown image format (magic bytes: {image_data[:8].hex()}), defaulting to JPEG"
            )

        logger.debug(f"Detected image format from magic bytes: {media_type}")

        base64_data = base64.b64encode(image_data).decode('utf-8')
        return (base64_data, media_type)

    except Exception as e:
        logger.warning(f"Failed to download image for base64: {e}")
        return None


def parse_image_generated_signal(result_str: str) -> GeneratedImage | None:
    """Parse an IMAGE_GENERATED signal from generate_image tool return.

    The signal format is: IMAGE_GENERATED|url|prompt|aspect_ratio|generation_time

    Args:
        result_str: The tool return string to parse

    Returns:
        GeneratedImage dataclass if signal found, None otherwise
    """
    if not result_str:
        return None

    # Parse only the first line (signal line)
    first_line = result_str.split('\n')[0]

    if not first_line.startswith('IMAGE_GENERATED|'):
        return None

    parts = first_line.split('|')
    if len(parts) < 4:
        logger.warning(f"IMAGE_GENERATED signal has insufficient parts: {len(parts)}")
        return None

    return GeneratedImage(
        url=parts[1],
        prompt=parts[2],
        aspect_ratio=parts[3],
        generation_time=parts[4] if len(parts) > 4 else "unknown"
    )


def send_image_review_message(
    client: Letta,
    agent_id: str,
    generated_image: GeneratedImage,
    context_prompt: str,
    show_reasoning: bool = False,
    max_steps: int = 50,
    max_regenerations: int = 5
) -> bool:
    """Send a follow-up multimodal message for the agent to review a generated image.

    Downloads the image, converts to base64, and sends it to the agent with
    instructions on how to proceed (post or regenerate).

    If the agent calls generate_image again (regeneration), this function will
    detect the new IMAGE_GENERATED signal and loop back to show the new image
    for review, up to max_regenerations times.

    Args:
        client: Letta client instance
        agent_id: Agent ID to send message to
        generated_image: GeneratedImage dataclass with image details
        context_prompt: Additional context for the review (e.g., original request info)
        show_reasoning: Whether to display reasoning output
        max_steps: Maximum agent steps for the follow-up
        max_regenerations: Maximum number of regeneration attempts (default 5)

    Returns:
        True if image was successfully sent and agent responded, False otherwise
    """
    try:
        current_image = generated_image
        regeneration_count = 0

        while regeneration_count <= max_regenerations:
            logger.info(f"🖼️ Sending generated image to agent for visual review (attempt {regeneration_count + 1})...")

            # Download image and convert to base64
            base64_result = download_image_as_base64(current_image.url)
            if not base64_result:
                logger.error(f"❌ Failed to download image for review")
                print(f"\n❌ Failed to download generated image for review")
                return False

            base64_data, media_type = base64_result
            logger.info(f"🖼️ Prepared image for review ({media_type})")

            # Build review prompt
            image_review_prompt = (
                f"Here's the generated image for your review.\n\n"
                f"{context_prompt}\n\n"
                f"Image details:\n"
                f"- URL: {current_image.url}\n"
                f"- Alt text: {current_image.prompt}\n"
                f"- Aspect ratio: {current_image.aspect_ratio}"
            )

            # Create multimodal content with base64 image
            image_content = [
                {"type": "text", "text": image_review_prompt},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64_data
                    }
                }
            ]

            # Small delay to ensure agent state is ready
            time.sleep(1)

            # Send follow-up with image for review
            followup_stream = client.agents.messages.create_stream(
                agent_id=agent_id,
                messages=[{"role": "user", "content": image_content}],
                stream_tokens=False,
                max_steps=max_steps
            )

            # Process follow-up response
            print(f"\n🖼️ Image Review" + (f" (regeneration {regeneration_count})" if regeneration_count > 0 else ""))
            print(f"  ────────────")
            image_posted = False
            new_generated_image = None

            for chunk in followup_stream:
                if hasattr(chunk, 'message_type'):
                    if chunk.message_type == 'reasoning_message':
                        if show_reasoning:
                            reasoning = getattr(chunk, 'reasoning', '')
                            if reasoning:
                                print(f"\n◆ Image Review Reasoning")
                                print(f"  ─────────────────────")
                                for line in reasoning.split('\n'):
                                    print(f"  {line}")

                    elif chunk.message_type == 'assistant_message':
                        content = getattr(chunk, 'content', '')
                        if content:
                            print(f"\n▶ Agent Response (Image Review)")
                            print(f"  ──────────────────────────────")
                            for line in content.split('\n'):
                                print(f"  {line}")

                    elif chunk.message_type == 'tool_call_message':
                        tool_call = getattr(chunk, 'tool_call', None)
                        if tool_call:
                            tool_name = tool_call.name
                            print(f"\n⚙ Tool call: {tool_name}")
                            try:
                                args = json.loads(tool_call.arguments)
                                if tool_name in ['reply_to_bluesky_post', 'create_new_bluesky_post']:
                                    texts = args.get('text', [])
                                    if texts:
                                        print(f"  ─────────────")
                                        for i, text in enumerate(texts, 1):
                                            print(f"  [{i}] {text}")
                                    if args.get('image_url'):
                                        print(f"  📎 Image attached")
                                elif tool_name == 'generate_image':
                                    print(f"  🔄 Regenerating image...")
                            except:
                                pass

                    elif chunk.message_type == 'tool_return_message':
                        status = getattr(chunk, 'status', '')
                        tool_name = getattr(chunk, 'name', 'unknown')
                        tool_return = getattr(chunk, 'tool_return', '')

                        if status == 'success':
                            print(f"\n✓ {tool_name}")
                            print(f"  Success")
                            if tool_name in ['create_new_bluesky_post', 'reply_to_bluesky_post']:
                                image_posted = True
                                logger.info(f"🎨 Agent posted with generated image via {tool_name}")
                            elif tool_name == 'generate_image':
                                # Parse the new IMAGE_GENERATED signal
                                tool_return_str = str(tool_return)
                                if 'IMAGE_GENERATED|' in tool_return_str:
                                    parsed = parse_image_generated_signal(tool_return_str)
                                    if parsed:
                                        new_generated_image = parsed
                                        logger.info(f"🎨 Agent regenerated image - will show new image for review")
                        elif status == 'error':
                            error_msg = str(tool_return)[:100]
                            print(f"\n✗ {tool_name}")
                            print(f"  Error: {error_msg}")

                if str(chunk) == 'done':
                    break

            # Check if we should loop for a regenerated image
            if new_generated_image:
                regeneration_count += 1
                if regeneration_count > max_regenerations:
                    logger.warning(f"🎨 Max regenerations ({max_regenerations}) reached, stopping image review loop")
                    print(f"\n⚠️ Max regenerations reached")
                    break
                current_image = new_generated_image
                logger.info(f"🎨 Looping back to show regenerated image (attempt {regeneration_count + 1}/{max_regenerations + 1})")
                continue

            # No regeneration requested, we're done
            logger.info(f"✓ Image review completed (posted: {image_posted}, regenerations: {regeneration_count})")
            return True

        return True

    except Exception as e:
        logger.error(f"Error sending generated image to agent: {e}")
        return False
