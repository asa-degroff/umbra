"""Upload an image to the PDS for use in GreenGale blog posts."""
from typing import Optional
from pydantic import BaseModel, Field


class UploadBlogImageArgs(BaseModel):
    image_url: str = Field(
        ...,
        description="URL of the image to upload"
    )
    alt: Optional[str] = Field(
        default=None,
        description="Alt text for the image (for accessibility)"
    )
    filename: Optional[str] = Field(
        default=None,
        description="Filename for the image. If not provided, derived from the URL."
    )


def upload_blog_image(
    image_url: str,
    alt: Optional[str] = None,
    filename: Optional[str] = None
) -> str:
    """
    Upload an image to the PDS for use in GreenGale blog posts.

    Downloads the image from the given URL, uploads it to the PDS blob store,
    and returns a markdown reference and blob metadata for use with
    create_greengale_blog_post.

    Args:
        image_url: URL of the image to upload
        alt: Alt text for the image (for accessibility)
        filename: Filename for the image. If not provided, derived from the URL.

    Returns:
        Formatted string with markdown reference and blob metadata JSON

    Raises:
        Exception: If the upload fails
    """
    import os
    import json
    import requests
    from urllib.parse import urlparse, quote

    try:
        # Get credentials from environment
        username = os.getenv("BSKY_USERNAME")
        password = os.getenv("BSKY_PASSWORD")
        pds_host = os.getenv("PDS_URI", "https://bsky.social")

        if not username or not password:
            raise Exception("BSKY_USERNAME and BSKY_PASSWORD environment variables must be set")

        # Derive filename from URL if not provided
        if not filename:
            parsed_url = urlparse(image_url)
            path = parsed_url.path
            filename = path.split("/")[-1] if path else "image.jpg"
            # Strip query params from filename
            if "?" in filename:
                filename = filename.split("?")[0]
            # Ensure filename has an extension
            if "." not in filename:
                filename = filename + ".jpg"

        # Create session
        session_url = f"{pds_host}/xrpc/com.atproto.server.createSession"
        session_data = {
            "identifier": username,
            "password": password
        }

        session_response = requests.post(session_url, json=session_data, timeout=10)
        session_response.raise_for_status()
        session = session_response.json()
        access_token = session.get("accessJwt")
        user_did = session.get("did")

        if not access_token or not user_did:
            raise Exception("Failed to get access token or DID from session")

        # Resolve PDS endpoint from didDoc
        pds_endpoint = pds_host
        did_doc = session.get("didDoc", {})
        for service in did_doc.get("service", []):
            if service.get("id") == "#atproto_pds":
                pds_endpoint = service.get("serviceEndpoint", pds_host)
                break

        # Download image
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        image_bytes = img_response.content

        # Detect MIME type from magic bytes
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            content_type = 'image/png'
        elif image_bytes[:3] == b'\xff\xd8\xff':
            content_type = 'image/jpeg'
        elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
            content_type = 'image/webp'
        elif image_bytes[:6] in (b'GIF87a', b'GIF89a'):
            content_type = 'image/gif'
        else:
            content_type = 'image/jpeg'  # fallback

        # Compress if image > 1MB
        if len(image_bytes) > 1_000_000:
            try:
                from PIL import Image
                import io

                img = Image.open(io.BytesIO(image_bytes))
                # Convert to RGB if necessary (for JPEG compression)
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

                # Update content type since we converted to JPEG
                content_type = 'image/jpeg'

            except ImportError:
                raise Exception(
                    f"Image is too large ({len(image_bytes)} bytes, max 1MB) and Pillow is not installed for resizing. "
                    "Install with: uv pip install Pillow"
                )

        # Upload blob to PDS
        upload_url = f"{pds_endpoint}/xrpc/com.atproto.repo.uploadBlob"
        upload_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": content_type
        }
        upload_response = requests.post(
            upload_url,
            headers=upload_headers,
            data=image_bytes,
            timeout=30
        )
        upload_response.raise_for_status()
        blob_data = upload_response.json()

        # Extract blob reference
        blob_ref = blob_data.get("blob")
        if not blob_ref:
            raise Exception("Failed to get blob reference from upload response")

        # Get CID from blob reference
        cid = blob_ref.get("ref", {}).get("$link", "")

        # Construct markdown URL
        encoded_did = quote(user_did, safe='')
        markdown_url = f"https://{pds_endpoint.replace('https://', '')}/xrpc/com.atproto.sync.getBlob?did={encoded_did}&cid={cid}"
        alt_text = alt or filename
        markdown_ref = f"![{alt_text}]({markdown_url})"

        # Construct blob metadata
        blob_metadata = {
            "name": filename,
            "alt": alt or "",
            "blobref": blob_ref
        }

        # Format return message
        result_parts = [
            "Image uploaded successfully!",
            "",
            "When composing your blog post, include this Markdown reference in the post content at the desired position:",
            markdown_ref,
            "",
            "Blob metadata (pass this as an item in the blobs parameter when creating the blog post):",
            json.dumps(blob_metadata)
        ]

        return "\n".join(result_parts)

    except Exception as e:
        raise Exception(f"Error uploading blog image: {str(e)}")
