"""Post tool for creating Bluesky posts with optional image attachments."""
from typing import List, Optional
from pydantic import BaseModel, Field, validator


class PostArgs(BaseModel):
    text: List[str] = Field(
        ...,
        description="List of texts to create posts (each max 300 characters). Single item creates one post, multiple items create a thread."
    )
    lang: Optional[str] = Field(
        default="en-US",
        description="Language code for the posts (e.g., 'en-US', 'es', 'ja', 'th'). Defaults to 'en-US'"
    )
    image_url: Optional[str] = Field(
        default=None,
        description="URL of an image to attach to the first post. The image will be downloaded and uploaded to Bluesky."
    )
    image_alt: Optional[str] = Field(
        default=None,
        description="Alt text for the image (for accessibility). If not provided, a generic description is used."
    )
    image_aspect_ratio: Optional[str] = Field(
        default="1:1",
        description="Aspect ratio of the image (e.g., '1:1', '16:9', '9:16', '4:3'). Used for proper preview display."
    )

    @validator('text')
    def validate_text_list(cls, v):
        if not v or len(v) == 0:
            raise ValueError("Text list cannot be empty")
        return v


def create_new_bluesky_post(
    text: List[str],
    lang: str = "en-US",
    image_url: Optional[str] = None,
    image_alt: Optional[str] = None,
    image_aspect_ratio: Optional[str] = "1:1"
) -> str:
    """
    Create a NEW standalone post on Bluesky. This tool creates independent posts that
    start new conversations. Use a list of texts to create a threaded reply chain to the first post.
    When creating posts, use long, detailed sentences to provide rich context and engage readers, 
    punctuating with commas and semicolons for clarity.

    IMPORTANT: This tool is ONLY for creating new posts. To reply to an existing post,
    use reply_to_bluesky_post instead.

    To attach an image, use the generate_image tool first to create one.

    Args:
        text: List of post contents (each max 300 characters). Single item creates one post, multiple items create a thread.
        lang: Language code for the posts (e.g., 'en-US', 'es', 'ja', 'th'). Defaults to 'en-US'
        image_url: Optional URL of an image to attach to the first post.
        image_alt: Optional alt text for the image. If not provided, uses a generic description.
        image_aspect_ratio: Aspect ratio of the image (e.g., '1:1', '16:9', '9:16'). Defaults to '1:1'.

    Returns:
        Success message with post URL(s)

    Raises:
        Exception: If the post fails or list is empty
    """
    import os
    import requests
    from datetime import datetime, timezone
    
    try:
        # Validate input
        if not text or len(text) == 0:
            raise Exception("Text list cannot be empty")
        
        # Validate character limits for all posts
        for i, post_text in enumerate(text):
            if len(post_text) > 300:
                raise Exception(f"Post {i+1} exceeds 300 character limit (current: {len(post_text)} characters). Use a list to split it into a thread.")
        
        # Get credentials from environment
        username = os.getenv("BSKY_USERNAME")
        password = os.getenv("BSKY_PASSWORD")
        pds_host = os.getenv("PDS_URI", "https://bsky.social")
        
        if not username or not password:
            raise Exception("BSKY_USERNAME and BSKY_PASSWORD environment variables must be set")
        
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

        # Handle image upload if provided
        image_embed = None
        if image_url:
            try:
                # Download image from URL
                img_response = requests.get(image_url, timeout=30)
                img_response.raise_for_status()
                image_bytes = img_response.content

                # Check image size (Bluesky limit is 1MB = 1,000,000 bytes)
                if len(image_bytes) > 1_000_000:
                    # Try to resize using Pillow
                    try:
                        from PIL import Image
                        import io

                        img = Image.open(io.BytesIO(image_bytes))
                        # Convert to RGB if necessary (for JPEG)
                        if img.mode in ('RGBA', 'P'):
                            img = img.convert('RGB')

                        # Resize to fit under 1MB while maintaining aspect ratio
                        quality = 85
                        while len(image_bytes) > 1_000_000 and quality > 20:
                            output = io.BytesIO()
                            # Reduce dimensions if quality reduction isn't enough
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
                            f"Image is too large ({len(image_bytes)} bytes, max 1MB) and Pillow is not installed for resizing. "
                            "Install with: uv pip install Pillow"
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

                # Upload blob to Bluesky
                upload_url = f"{pds_host}/xrpc/com.atproto.repo.uploadBlob"
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

                # Build embed structure
                blob_ref = blob_data.get("blob")
                if not blob_ref:
                    raise Exception("Failed to get blob reference from upload response")

                # Parse aspect ratio for the embed
                aspect_width, aspect_height = 1, 1
                if image_aspect_ratio and ":" in image_aspect_ratio:
                    try:
                        parts = image_aspect_ratio.split(":")
                        aspect_width = int(parts[0])
                        aspect_height = int(parts[1])
                    except (ValueError, IndexError):
                        aspect_width, aspect_height = 1, 1  # Fallback to 1:1

                image_embed = {
                    "$type": "app.bsky.embed.images",
                    "images": [{
                        "image": blob_ref,
                        "alt": image_alt or "AI-generated image",
                        "aspectRatio": {"width": aspect_width, "height": aspect_height}
                    }]
                }

            except requests.exceptions.RequestException as e:
                raise Exception(f"Failed to download or upload image: {str(e)}")
            except Exception as e:
                if "image" in str(e).lower() or "blob" in str(e).lower():
                    raise
                raise Exception(f"Error processing image: {str(e)}")

        # Create posts (single or thread)
        import re
        headers = {"Authorization": f"Bearer {access_token}"}
        create_record_url = f"{pds_host}/xrpc/com.atproto.repo.createRecord"
        
        post_urls = []
        previous_post = None
        root_post = None
        
        for i, post_text in enumerate(text):
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            
            post_record = {
                "$type": "app.bsky.feed.post",
                "text": post_text,
                "createdAt": now,
                "langs": [lang]
            }
            
            # If this is part of a thread (not the first post), add reply references
            if previous_post:
                post_record["reply"] = {
                    "root": root_post,
                    "parent": previous_post
                }

            # Add image embed to the first post only
            if i == 0 and image_embed:
                post_record["embed"] = image_embed

            # Add facets for mentions and URLs
            facets = []
            
            # Parse mentions - fixed to handle @ at start of text
            mention_regex = rb"(?:^|[$|\W])(@([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
            text_bytes = post_text.encode("UTF-8")
            
            for m in re.finditer(mention_regex, text_bytes):
                handle = m.group(1)[1:].decode("UTF-8")  # Remove @ prefix
                # Adjust byte positions to account for the optional prefix
                mention_start = m.start(1)
                mention_end = m.end(1)
                try:
                    resolve_resp = requests.get(
                        f"{pds_host}/xrpc/com.atproto.identity.resolveHandle",
                        params={"handle": handle},
                        timeout=5
                    )
                    if resolve_resp.status_code == 200:
                        did = resolve_resp.json()["did"]
                        facets.append({
                            "index": {
                                "byteStart": mention_start,
                                "byteEnd": mention_end,
                            },
                            "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}],
                        })
                except:
                    continue
            
            # Parse URLs - fixed to handle URLs at start of text
            url_regex = rb"(?:^|[$|\W])(https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
            
            for m in re.finditer(url_regex, text_bytes):
                url = m.group(1).decode("UTF-8")
                # Adjust byte positions to account for the optional prefix
                url_start = m.start(1)
                url_end = m.end(1)
                facets.append({
                    "index": {
                        "byteStart": url_start,
                        "byteEnd": url_end,
                    },
                    "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
                })
            
            if facets:
                post_record["facets"] = facets
            
            # Create the post
            create_data = {
                "repo": user_did,
                "collection": "app.bsky.feed.post",
                "record": post_record
            }
            
            post_response = requests.post(create_record_url, headers=headers, json=create_data, timeout=10)
            post_response.raise_for_status()
            result = post_response.json()
            
            post_uri = result.get("uri")
            post_cid = result.get("cid")
            handle = session.get("handle", username)
            rkey = post_uri.split("/")[-1] if post_uri else ""
            post_url = f"https://bsky.app/profile/{handle}/post/{rkey}"
            post_urls.append(post_url)
            
            # Set up references for thread continuation
            previous_post = {"uri": post_uri, "cid": post_cid}
            if i == 0:
                root_post = previous_post
        
        # Return appropriate message based on single post or thread
        image_info = ""
        if image_embed:
            image_info = f"\nImage attached: Yes (alt text: {image_alt or 'AI-generated image'})"

        if len(text) == 1:
            return f"Successfully posted to Bluesky!\nPost URL: {post_urls[0]}\nText: {text[0]}\nLanguage: {lang}{image_info}"
        else:
            urls_text = "\n".join([f"Post {i+1}: {url}" for i, url in enumerate(post_urls)])
            return f"Successfully created thread with {len(text)} posts!\n{urls_text}\nLanguage: {lang}{image_info}"
        
    except Exception as e:
        raise Exception(f"Error posting to Bluesky: {str(e)}")