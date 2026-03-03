"""
Shared image upload utility for Bluesky post/reply tools.

Handles downloading, compressing, and uploading images to the PDS blob store.
"""

import requests


def upload_image_to_pds(url: str, alt: str, ratio: str, pds_host: str, access_token: str) -> dict:
    """Download, compress, and upload an image to Bluesky PDS.

    Args:
        url: Image URL to download
        alt: Alt text for the image
        ratio: Aspect ratio string (e.g., "1:1", "16:9")
        pds_host: PDS host URL (e.g., "https://bsky.social")
        access_token: Bearer token for the PDS

    Returns:
        Dict suitable for app.bsky.embed.images entry:
        {"image": blob_ref, "alt": ..., "aspectRatio": {...}}
    """
    img_response = requests.get(url, timeout=30)
    img_response.raise_for_status()
    image_bytes = img_response.content

    # Compress if over 1MB
    if len(image_bytes) > 1_000_000:
        try:
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(image_bytes))
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            quality = 85
            while len(image_bytes) > 1_000_000 and quality > 20:
                output = io.BytesIO()
                if quality < 50:
                    new_size = (int(img.width * 0.8), int(img.height * 0.8))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                img.save(output, format='JPEG', quality=quality, optimize=True)
                image_bytes = output.getvalue()
                quality -= 10

            if len(image_bytes) > 1_000_000:
                raise Exception("Image is too large and could not be compressed under 1MB")
        except ImportError:
            raise Exception(
                f"Image is too large ({len(image_bytes)} bytes, max 1MB) and Pillow is not installed."
            )

    # Detect content type
    content_type = img_response.headers.get('content-type', 'image/jpeg')
    if 'png' in content_type.lower():
        content_type = 'image/png'
    elif 'webp' in content_type.lower():
        content_type = 'image/webp'
    elif 'gif' in content_type.lower():
        content_type = 'image/gif'
    else:
        content_type = 'image/jpeg'

    # Upload blob
    upload_url = f"{pds_host}/xrpc/com.atproto.repo.uploadBlob"
    upload_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": content_type
    }
    upload_response = requests.post(
        upload_url, headers=upload_headers, data=image_bytes, timeout=30
    )
    upload_response.raise_for_status()
    blob_ref = upload_response.json().get("blob")
    if not blob_ref:
        raise Exception("Failed to get blob reference from upload response")

    # Detect aspect ratio from actual image dimensions
    aspect_width, aspect_height = 1, 1
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        aspect_width, aspect_height = img.width, img.height
    except Exception:
        # Fall back to caller-provided ratio
        if ratio and ":" in ratio:
            try:
                parts = ratio.split(":")
                aspect_width = int(parts[0])
                aspect_height = int(parts[1])
            except (ValueError, IndexError):
                pass

    return {
        "image": blob_ref,
        "alt": alt or "AI-generated image",
        "aspectRatio": {"width": aspect_width, "height": aspect_height}
    }


def build_image_embed(
    pds_host: str,
    access_token: str,
    image_url: str,
    image_alt: str = None,
    image_aspect_ratio: str = "1:1",
    image_url_2: str = None,
    image_alt_2: str = None,
    image_aspect_ratio_2: str = None,
) -> dict | None:
    """Build a complete app.bsky.embed.images embed with one or two images.

    Returns:
        Embed dict or None if no image_url provided.
    """
    if not image_url:
        return None

    images_list = []
    images_list.append(upload_image_to_pds(image_url, image_alt, image_aspect_ratio, pds_host, access_token))

    if image_url_2:
        ratio_2 = image_aspect_ratio_2 or image_aspect_ratio
        images_list.append(upload_image_to_pds(image_url_2, image_alt_2, ratio_2, pds_host, access_token))

    return {
        "$type": "app.bsky.embed.images",
        "images": images_list
    }
