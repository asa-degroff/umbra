"""
Replicate model runners for image generation.

Extracted to a separate module so Letta's tool registration doesn't
lose track of the main function name.
"""


# Aspect ratio → (width, height) at 2K resolution for Seedream 4.5
# Minimum 3,686,400 pixels required by Seedream 4.5, dimensions aligned to 8px
SEEDREAM_DIMENSIONS = {
    "1:1":  (1920, 1920),
    "16:9": (2560, 1440),
    "9:16": (1440, 2560),
    "4:3":  (2224, 1664),
    "3:4":  (1664, 2224),
    "3:2":  (2352, 1568),
    "2:3":  (1568, 2352),
    "4:5":  (1720, 2152),
    "5:4":  (2152, 1720),
    "2:1":  (2720, 1360),
    "1:2":  (1360, 2720),
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
