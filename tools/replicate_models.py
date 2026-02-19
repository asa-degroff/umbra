"""
Replicate model runners for image generation.

Extracted to a separate module so Letta's tool registration doesn't
lose track of the main function name.
"""


# Aspect ratio → (width, height) at 2K resolution for Seedream 4.5
SEEDREAM_DIMENSIONS = {
    "1:1":  (2048, 2048),
    "16:9": (2048, 1152),
    "9:16": (1152, 2048),
    "4:3":  (2048, 1536),
    "3:4":  (1536, 2048),
    "3:2":  (2048, 1365),
    "2:3":  (1365, 2048),
    "4:5":  (1638, 2048),
    "5:4":  (2048, 1638),
    "2:1":  (2048, 1024),
    "1:2":  (1024, 2048),
}


def run_lucid_origin(replicate_client, prompt: str, aspect_ratio: str) -> dict:
    """Run Leonardo AI Lucid Origin model. Returns dict with url, model, error."""
    try:
        output = replicate_client.run(
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
        if not output:
            return {"model": "lucid_origin", "url": None, "error": "Empty response"}
        url = str(output[0]) if hasattr(output[0], '__str__') else output[0]
        if not url or not url.startswith("http"):
            return {"model": "lucid_origin", "url": None, "error": f"Invalid URL: {url}"}
        return {"model": "lucid_origin", "url": url, "error": None}
    except Exception as e:
        return {"model": "lucid_origin", "url": None, "error": str(e)}


def run_seedream(replicate_client, prompt: str, aspect_ratio: str) -> dict:
    """Run ByteDance Seedream 4.5 model. Returns dict with url, model, error."""
    try:
        width, height = SEEDREAM_DIMENSIONS.get(aspect_ratio, (2048, 2048))
        output = replicate_client.run(
            "bytedance/seedream-4.5",
            input={
                "prompt": prompt,
                "size": "custom",
                "width": width,
                "height": height,
                "max_images": 1,
                "sequential_image_generation": "disabled",
            }
        )
        if not output:
            return {"model": "seedream", "url": None, "error": "Empty response"}
        url = str(output[0]) if hasattr(output[0], '__str__') else output[0]
        if not url or not url.startswith("http"):
            return {"model": "seedream", "url": None, "error": f"Invalid URL: {url}"}
        return {"model": "seedream", "url": url, "error": None}
    except Exception as e:
        return {"model": "seedream", "url": None, "error": str(e)}
