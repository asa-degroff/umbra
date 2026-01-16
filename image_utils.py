"""
Image Utilities Module

Shared utilities for image handling across umbra, including:
- Downloading images and converting to base64
- Saving generated images to local storage for backup/review
- Parsing IMAGE_GENERATED signals from the generate_image tool
- Sending image review follow-up messages to the agent
"""

import logging
import time
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from letta_client import Letta

logger = logging.getLogger('umbra')

# Default folder for saving generated images
DEFAULT_GENERATED_IMAGES_DIR = Path(__file__).parent / "generated_images"


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


def get_extension_from_media_type(media_type: str) -> str:
    """Get file extension from media type."""
    extensions = {
        'image/png': '.png',
        'image/jpeg': '.jpg',
        'image/gif': '.gif',
        'image/webp': '.webp',
    }
    return extensions.get(media_type, '.jpg')


def sanitize_filename(text: str, max_length: int = 50) -> str:
    """Sanitize text for use in filename."""
    # Remove or replace problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*\n\r\t]', '', text)
    # Replace spaces and multiple underscores
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = re.sub(r'_+', '_', sanitized)
    # Truncate and strip
    return sanitized[:max_length].strip('_')


def save_generated_image(
    image_data: bytes,
    media_type: str,
    prompt: str,
    aspect_ratio: str = "",
    save_dir: Path | str | None = None
) -> Path | None:
    """Save generated image to local storage.

    Args:
        image_data: Raw image bytes
        media_type: MIME type (e.g., 'image/png')
        prompt: The prompt used to generate the image
        aspect_ratio: The aspect ratio used (optional, for metadata)
        save_dir: Directory to save images (defaults to generated_images/)

    Returns:
        Path to saved file, or None if failed
    """
    try:
        # Use default directory if not specified
        if save_dir is None:
            save_dir = DEFAULT_GENERATED_IMAGES_DIR
        save_dir = Path(save_dir)

        # Create directory if it doesn't exist
        save_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename: timestamp_prompt-snippet.ext
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prompt_snippet = sanitize_filename(prompt)
        extension = get_extension_from_media_type(media_type)
        filename = f"{timestamp}_{prompt_snippet}{extension}"

        filepath = save_dir / filename

        # Save the image
        with open(filepath, 'wb') as f:
            f.write(image_data)

        # Save metadata alongside the image
        metadata_path = filepath.with_suffix('.json')
        metadata = {
            'prompt': prompt,
            'aspect_ratio': aspect_ratio,
            'media_type': media_type,
            'generated_at': datetime.now().isoformat(),
            'file_size_bytes': len(image_data),
        }
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"💾 Saved generated image: {filepath.name}")
        return filepath

    except Exception as e:
        logger.error(f"Failed to save generated image: {e}")
        return None


def download_and_save_image(
    url: str,
    prompt: str,
    aspect_ratio: str = "",
    save_dir: Path | str | None = None,
    timeout: int = 30
) -> tuple[str, str, Path | None] | None:
    """Download image, save to local storage, and return base64.

    This is a convenience function that combines downloading, saving,
    and base64 encoding in one operation.

    Args:
        url: The image URL to download
        prompt: The prompt used to generate the image
        aspect_ratio: The aspect ratio used
        save_dir: Directory to save images
        timeout: Request timeout in seconds

    Returns:
        Tuple of (base64_data, media_type, saved_path) or None if download failed.
        saved_path may be None if saving failed but download succeeded.
    """
    import requests
    import base64

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        image_data = response.content

        # Detect media type from magic bytes
        if image_data[:8] == b'\x89PNG\r\n\x1a\n':
            media_type = 'image/png'
        elif image_data[:3] == b'\xff\xd8\xff':
            media_type = 'image/jpeg'
        elif image_data[:6] in (b'GIF87a', b'GIF89a'):
            media_type = 'image/gif'
        elif image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
            media_type = 'image/webp'
        else:
            media_type = 'image/jpeg'
            logger.warning(
                f"Unknown image format (magic bytes: {image_data[:8].hex()}), defaulting to JPEG"
            )

        logger.debug(f"Detected image format from magic bytes: {media_type}")

        # Save the image
        saved_path = save_generated_image(
            image_data=image_data,
            media_type=media_type,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            save_dir=save_dir
        )

        # Convert to base64
        base64_data = base64.b64encode(image_data).decode('utf-8')

        return (base64_data, media_type, saved_path)

    except Exception as e:
        logger.warning(f"Failed to download image: {e}")
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

            # Download image, save to local storage, and convert to base64
            download_result = download_and_save_image(
                url=current_image.url,
                prompt=current_image.prompt,
                aspect_ratio=current_image.aspect_ratio
            )
            if not download_result:
                logger.error(f"❌ Failed to download image for review")
                print(f"\n❌ Failed to download generated image for review")
                return False

            base64_data, media_type, saved_path = download_result
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
                # Handle error messages first (may not have message_type attribute)
                msg_type = getattr(chunk, 'message_type', None)
                if msg_type == 'error_message':
                    error_msg = getattr(chunk, 'message', None)
                    error_detail = getattr(chunk, 'detail', None)
                    logger.error(f"❌ Image review error: {error_msg} - {error_detail}")
                    print(f"\n❌ Image Review Error: {error_msg or error_detail or 'Unknown error'}")

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

                    # Log unexpected message types for debugging
                    elif chunk.message_type not in ['ping', 'usage_statistics', 'stop_reason']:
                        logger.debug(f"Unhandled message type in image review: {chunk.message_type}")

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
