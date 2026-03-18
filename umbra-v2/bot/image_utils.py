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
    model: str = "unknown"  # "lucid_origin", "seedream", or "unknown"


@dataclass
class GeneratedImagePair:
    """Container for dual-model image generation results."""
    lucid_url: Optional[str]     # Lucid Origin result (may be None if failed)
    seedream_url: Optional[str]  # Seedream 4.5 result (may be None if failed)
    prompt: str
    aspect_ratio: str
    generation_time: str

    @property
    def has_both(self) -> bool:
        return bool(self.lucid_url) and bool(self.seedream_url)

    @property
    def available_count(self) -> int:
        return sum(1 for u in [self.lucid_url, self.seedream_url] if u)

    def as_single(self) -> GeneratedImage:
        """Convert to single GeneratedImage using whichever URL is available."""
        url = self.lucid_url or self.seedream_url or ""
        model = "lucid_origin" if self.lucid_url else "seedream"
        return GeneratedImage(
            url=url, prompt=self.prompt, aspect_ratio=self.aspect_ratio,
            generation_time=self.generation_time, model=model
        )


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
    """Parse an IMAGE_GENERATED signal from generate_image tool return (legacy single-model).

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


def parse_images_generated_signal(result_str: str) -> GeneratedImagePair | None:
    """Parse an IMAGES_GENERATED signal from dual-model generate_image tool return.

    The signal format is: IMAGES_GENERATED|lucid_url|seedream_url|prompt|aspect_ratio|generation_time
    URLs may be "NONE" if that model failed.

    Args:
        result_str: The tool return string to parse

    Returns:
        GeneratedImagePair dataclass if signal found, None otherwise
    """
    if not result_str:
        return None

    first_line = result_str.split('\n')[0]

    if not first_line.startswith('IMAGES_GENERATED|'):
        return None

    parts = first_line.split('|')
    if len(parts) < 5:
        logger.warning(f"IMAGES_GENERATED signal has insufficient parts: {len(parts)}")
        return None

    lucid_url = parts[1] if parts[1] != "NONE" else None
    seedream_url = parts[2] if parts[2] != "NONE" else None

    return GeneratedImagePair(
        lucid_url=lucid_url,
        seedream_url=seedream_url,
        prompt=parts[3],
        aspect_ratio=parts[4],
        generation_time=parts[5] if len(parts) > 5 else "unknown"
    )


def parse_any_image_signal(result_str: str) -> GeneratedImagePair | GeneratedImage | None:
    """Parse either IMAGES_GENERATED (dual) or IMAGE_GENERATED (single) signal.

    Returns:
        GeneratedImagePair, GeneratedImage, or None
    """
    pair = parse_images_generated_signal(result_str)
    if pair:
        return pair
    return parse_image_generated_signal(result_str)


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
                                # Parse image signal (supports both single and dual model)
                                tool_return_str = str(tool_return)
                                parsed = parse_any_image_signal(tool_return_str)
                                if parsed:
                                    new_generated_image = parsed
                                    logger.info(f"🎨 Agent regenerated image(s) - will show for review")
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


def send_dual_image_review_message(
    client: Letta,
    agent_id: str,
    image_pair: GeneratedImagePair,
    context_prompt: str,
    show_reasoning: bool = False,
    max_steps: int = 50,
    max_regenerations: int = 5
) -> bool:
    """Send a follow-up multimodal message with BOTH generated images for review.

    Downloads both images (Lucid Origin + Seedream 4.5), converts to base64,
    and sends them to the agent side-by-side with labels.

    Args:
        client: Letta client instance
        agent_id: Agent ID to send message to
        image_pair: GeneratedImagePair with both image URLs
        context_prompt: Additional context for the review
        show_reasoning: Whether to display reasoning output
        max_steps: Maximum agent steps for the follow-up
        max_regenerations: Maximum number of regeneration attempts

    Returns:
        True if images were successfully sent and agent responded
    """
    try:
        current_pair = image_pair
        regeneration_count = 0

        while regeneration_count <= max_regenerations:
            model_count = current_pair.available_count
            logger.info(
                f"🖼️ Sending {model_count} generated image(s) to agent for review "
                f"(attempt {regeneration_count + 1})..."
            )

            # Build multimodal content with both images
            image_content = []

            # Text description
            review_lines = [
                f"Here are the generated images for your review.\n",
                f"{context_prompt}\n",
                f"Prompt: {current_pair.prompt}",
                f"Aspect ratio: {current_pair.aspect_ratio}",
                f"Generation time: {current_pair.generation_time}s\n",
            ]

            if current_pair.lucid_url:
                review_lines.append(f"**Image 1 — Lucid Origin**: {current_pair.lucid_url}")
            if current_pair.seedream_url:
                review_lines.append(f"**Image 2 — Seedream 4.5**: {current_pair.seedream_url}")

            review_lines.append("")
            review_lines.append("You can:")
            review_lines.append("- Post your favorite using image_url with the chosen URL")
            review_lines.append("- Post BOTH using image_url + image_url_2")
            review_lines.append("- Regenerate with a revised prompt")

            image_content.append({"type": "text", "text": "\n".join(review_lines)})

            # Download and add Lucid Origin image
            if current_pair.lucid_url:
                lucid_result = download_and_save_image(
                    url=current_pair.lucid_url,
                    prompt=f"lucid_origin_{current_pair.prompt}",
                    aspect_ratio=current_pair.aspect_ratio
                )
                if lucid_result:
                    b64, media_type, _ = lucid_result
                    image_content.append({"type": "text", "text": "Image 1 — Lucid Origin:"})
                    image_content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64}
                    })
                else:
                    image_content.append({"type": "text", "text": "⚠️ Lucid Origin image failed to download"})

            # Download and add Seedream image
            if current_pair.seedream_url:
                seedream_result = download_and_save_image(
                    url=current_pair.seedream_url,
                    prompt=f"seedream_{current_pair.prompt}",
                    aspect_ratio=current_pair.aspect_ratio
                )
                if seedream_result:
                    b64, media_type, _ = seedream_result
                    image_content.append({"type": "text", "text": "Image 2 — Seedream 4.5:"})
                    image_content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64}
                    })
                else:
                    image_content.append({"type": "text", "text": "⚠️ Seedream 4.5 image failed to download"})

            # Small delay to ensure agent state is ready
            time.sleep(1)

            # Send follow-up with images for review
            followup_stream = client.agents.messages.create_stream(
                agent_id=agent_id,
                messages=[{"role": "user", "content": image_content}],
                stream_tokens=False,
                max_steps=max_steps
            )

            # Process follow-up response
            print(f"\n🖼️ Dual Image Review" + (f" (regeneration {regeneration_count})" if regeneration_count > 0 else ""))
            print(f"  ────────────────")
            image_posted = False
            new_image_pair = None
            new_single_image = None

            for chunk in followup_stream:
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
                                        print(f"  📎 Image 1 attached")
                                    if args.get('image_url_2'):
                                        print(f"  📎 Image 2 attached")
                                elif tool_name == 'generate_image':
                                    print(f"  🔄 Regenerating images...")
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
                                tool_return_str = str(tool_return)
                                # Try new dual-model signal first
                                pair = parse_images_generated_signal(tool_return_str)
                                if pair:
                                    new_image_pair = pair
                                    logger.info(f"🎨 Agent regenerated images (dual) — will show for review")
                                else:
                                    # Fall back to legacy single signal
                                    single = parse_image_generated_signal(tool_return_str)
                                    if single:
                                        new_single_image = single
                                        logger.info(f"🎨 Agent regenerated image (single) — will show for review")
                        elif status == 'error':
                            error_msg = str(tool_return)[:100]
                            print(f"\n✗ {tool_name}")
                            print(f"  Error: {error_msg}")

                    elif chunk.message_type not in ['ping', 'usage_statistics', 'stop_reason']:
                        logger.debug(f"Unhandled message type in image review: {chunk.message_type}")

                if str(chunk) == 'done':
                    break

            # Check if we should loop for regeneration
            if new_image_pair:
                regeneration_count += 1
                if regeneration_count > max_regenerations:
                    logger.warning(f"🎨 Max regenerations ({max_regenerations}) reached")
                    print(f"\n⚠️ Max regenerations reached")
                    break
                current_pair = new_image_pair
                continue

            if new_single_image:
                # Agent regenerated with single model — wrap in a pair for consistency
                regeneration_count += 1
                if regeneration_count > max_regenerations:
                    break
                current_pair = GeneratedImagePair(
                    lucid_url=new_single_image.url if new_single_image.model == "lucid_origin" else None,
                    seedream_url=new_single_image.url if new_single_image.model == "seedream" else new_single_image.url,
                    prompt=new_single_image.prompt,
                    aspect_ratio=new_single_image.aspect_ratio,
                    generation_time=new_single_image.generation_time
                )
                continue

            logger.info(f"✓ Dual image review completed (posted: {image_posted}, regenerations: {regeneration_count})")
            return True

        return True

    except Exception as e:
        logger.error(f"Error sending dual images to agent: {e}")
        return False
