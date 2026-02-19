"""
Image Generation Tool

Generate images using two AI models via the Replicate API:
  - Leonardo AI Lucid Origin (abstract/artistic)
  - ByteDance Seedream 4.5 (text/diagrams/photorealistic)

Both models are run concurrently and both URLs are returned in a signal format
that bsky.py detects to auto-include the images for visual review.
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
    Generate AI images using two models concurrently: Lucid Origin and Seedream 4.5.

    Both images will be automatically shown to you for review. You can then choose
    to post your favorite, post both, or regenerate with either model.

    Lucid Origin excels at abstract and artistic imagery.
    Seedream 4.5 excels at text rendering, diagrams, and photorealistic scenes.

    Args:
        prompt: Detailed description of the image to generate. This will also be
                used as alt text when attaching to posts.
        aspect_ratio: Aspect ratio for the image. Default is '1:1' (square).
                      Options: '1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3'

    Returns:
        Signal string containing image URLs and metadata, which triggers
        auto-display of both images for review.

    Raises:
        Exception: If the API call fails or credentials are missing.
    """
    import os
    import time
    import concurrent.futures
    import replicate

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

    replicate_client = replicate.Client(api_token=api_token)

    # Seedream 4.5 aspect ratio → (width, height)
    # Minimum 3,686,400 pixels required by Seedream 4.5, dimensions aligned to 8px
    seedream_dims = {
        "1:1":  (1920, 1920), "16:9": (2560, 1440), "9:16": (1440, 2560),
        "4:3":  (2224, 1664), "3:4":  (1664, 2224), "3:2":  (2352, 1568),
        "2:3":  (1568, 2352), "4:5":  (1720, 2152), "5:4":  (2152, 1720),
        "2:1":  (2720, 1360), "1:2":  (1360, 2720),
    }

    # --- Model runner closures (not named functions, to avoid Letta name detection) ---
    run_lucid = lambda: None  # placeholder
    run_seedream = lambda: None  # placeholder

    # Lucid Origin runner
    lucid_result = {"model": "lucid_origin", "url": None, "error": None}
    seedream_result = {"model": "seedream", "url": None, "error": None}

    start_time = time.time()

    # Run Lucid Origin
    try:
        lucid_output = replicate_client.run(
            "leonardoai/lucid-origin",
            input={
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "num_images": 1,
                "style": "none",
                "contrast": "medium",
                "generation_mode": "standard",
                "prompt_enhance": True,
            }
        )
        if lucid_output:
            url = str(lucid_output[0])
            if url and url.startswith("http"):
                lucid_result["url"] = url
            else:
                lucid_result["error"] = f"Invalid URL: {url}"
        else:
            lucid_result["error"] = "Empty response"
    except Exception as e:
        lucid_result["error"] = str(e)

    # Run Seedream 4.5
    try:
        sw, sh = seedream_dims.get(aspect_ratio, (2048, 2048))
        seedream_output = replicate_client.run(
            "bytedance/seedream-4.5",
            input={
                "prompt": prompt,
                "size": "custom",
                "width": sw,
                "height": sh,
                "max_images": 1,
                "sequential_image_generation": "disabled",
            }
        )
        if seedream_output:
            url = str(seedream_output[0])
            if url and url.startswith("http"):
                seedream_result["url"] = url
            else:
                seedream_result["error"] = f"Invalid URL: {url}"
        else:
            seedream_result["error"] = "Empty response"
    except Exception as e:
        seedream_result["error"] = str(e)

    generation_time = time.time() - start_time

    # Check results
    lucid_url = lucid_result.get("url")
    seedream_url = seedream_result.get("url")

    if not lucid_url and not seedream_url:
        errors = []
        if lucid_result.get("error"):
            errors.append(f"Lucid Origin: {lucid_result['error']}")
        if seedream_result.get("error"):
            errors.append(f"Seedream 4.5: {seedream_result['error']}")
        raise Exception(f"Both models failed. {'; '.join(errors)}")

    # Build signal — format: IMAGES_GENERATED|lucid_url|seedream_url|prompt|aspect_ratio|time
    # Use "NONE" for URLs that failed
    signal_prompt = prompt.replace('\n', ' ').replace('\r', ' ').replace('|', '-')
    signal = (
        f"IMAGES_GENERATED"
        f"|{lucid_url or 'NONE'}"
        f"|{seedream_url or 'NONE'}"
        f"|{signal_prompt}"
        f"|{aspect_ratio}"
        f"|{generation_time:.1f}"
    )

    # Build human-readable instructions
    lines = [f"\n\n---\nImages generated in {generation_time:.1f}s!\n"]

    if lucid_url:
        lines.append(f"**Lucid Origin** (abstract/artistic): {lucid_url}")
    else:
        lines.append(f"**Lucid Origin**: Failed — {lucid_result.get('error', 'unknown error')}")

    if seedream_url:
        lines.append(f"**Seedream 4.5** (text/diagrams/realistic): {seedream_url}")
    else:
        lines.append(f"**Seedream 4.5**: Failed — {seedream_result.get('error', 'unknown error')}")

    lines.append("")
    lines.append("To post your favorite, use reply_to_bluesky_post or create_new_bluesky_post with:")
    lines.append("- image_url: <chosen URL>")
    lines.append("- image_alt: <prompt>")
    lines.append("")
    lines.append("To post BOTH images in one post, use:")
    lines.append("- image_url: <first URL>")
    lines.append("- image_url_2: <second URL>")
    lines.append("- image_alt / image_alt_2: alt text for each")

    return signal + "\n".join(lines)
