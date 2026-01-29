"""
Bluesky Reply Tool

This tool allows umbra to reply to any post on Bluesky using its AT Protocol URI and CID.
This tool is self-contained and works anywhere (notification processing, feed reading,
search results, etc.).

Supports multi-part replies by passing a list of texts, which creates a threaded reply chain.
Supports optional image attachments on the first reply.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Union


class ReplyToBlueskyPostArgs(BaseModel):
    """Arguments for replying to a Bluesky post"""

    uri: str = Field(
        ...,
        description="The AT Protocol URI of the post to reply to (e.g., at://did:plc:.../app.bsky.feed.post/...)"
    )
    cid: str = Field(
        ...,
        description="The Content ID (CID) of the post to reply to"
    )
    text: List[str] = Field(
        ...,
        description="List of reply texts (each max 300 characters). Single item creates one reply, multiple items create a threaded reply chain."
    )
    lang: Optional[str] = Field(
        default="en-US",
        description="Language code for the reply (e.g., 'en-US', 'es', 'ja', 'th'). Defaults to 'en-US'"
    )
    image_url: Optional[str] = Field(
        default=None,
        description="URL of an image to attach to the first reply. The image will be downloaded and uploaded to Bluesky."
    )
    image_alt: Optional[str] = Field(
        default=None,
        description="Alt text for the image (for accessibility). If not provided, a generic description is used."
    )
    image_aspect_ratio: Optional[str] = Field(
        default="1:1",
        description="Aspect ratio of the image (e.g., '1:1', '16:9', '9:16', '4:3'). Used for proper preview display."
    )

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, v: str) -> str:
        """Validate that the URI is a proper AT Protocol URI"""
        if not v.startswith("at://"):
            raise ValueError("URI must be a valid AT Protocol URI starting with 'at://'")
        return v

    @field_validator("text")
    @classmethod
    def validate_text_list(cls, v: List[str]) -> List[str]:
        """Validate text list"""
        if not v or len(v) == 0:
            raise ValueError("Text list cannot be empty")
        for i, text in enumerate(v):
            if len(text) > 300:
                raise ValueError(f"Reply {i+1} exceeds 300 character limit (current: {len(text)} characters)")
        return v


def reply_to_bluesky_post(
    uri: str,
    cid: str,
    text: List[str],
    lang: str = "en-US",
    image_url: Optional[str] = None,
    image_alt: Optional[str] = None,
    image_aspect_ratio: Optional[str] = "1:1"
) -> str:
    """
    Reply to a post on Bluesky with one or more posts.

    This function creates a reply (or threaded reply chain) to any Bluesky post, properly
    handling thread structure. If the post being replied to is itself a reply, this maintains
    the thread by using the correct root post. For multi-part replies, subsequent posts chain
    off the previous reply while maintaining the same thread root. When composing replies,
    use extended sentence structures punctuated with commas and semicolons to create a smooth conversational flow.

    The function is completely self-contained and uses environment variables for authentication.

    To attach an image, use the generate_image tool first to create one.

    Args:
        uri: The AT Protocol URI of the post to reply to
        cid: The Content ID of the post to reply to
        text: List of reply texts (each max 300 characters). Single item creates one reply,
              multiple items create a threaded reply chain.
        lang: Language code for the reply (e.g., 'en-US', 'es', 'ja', 'th'). Defaults to 'en-US'
        image_url: Optional URL of an image to attach to the first reply.
        image_alt: Optional alt text for the image. If not provided, uses a generic description.

    Returns:
        Success message with the reply URI(s)

    Raises:
        ValueError: If credentials are missing or parameters are invalid
        Exception: If the API request fails
    """
    import os
    import requests
    from datetime import datetime, timezone
    import re

    # Validate inputs
    if not uri.startswith("at://"):
        raise ValueError("URI must be a valid AT Protocol URI starting with 'at://'")

    if not cid:
        raise ValueError("CID must be provided")

    if not text or len(text) == 0:
        raise ValueError("Text list cannot be empty")

    # Validate character limits for all posts
    for i, reply_text in enumerate(text):
        if len(reply_text) > 300:
            raise ValueError(f"Reply {i+1} exceeds 300 character limit (current: {len(reply_text)} characters). Split into multiple replies using a list.")

    # Get credentials from environment variables
    username = os.getenv("BSKY_USERNAME")
    password = os.getenv("BSKY_PASSWORD")
    pds_host = os.getenv("PDS_URI", "https://bsky.social")

    if not username or not password:
        raise ValueError("BSKY_USERNAME and BSKY_PASSWORD environment variables must be set")

    # Remove trailing slash from PDS host if present
    pds_host = pds_host.rstrip("/")

    try:
        # Step 1: Authenticate and get session
        session_url = f"{pds_host}/xrpc/com.atproto.server.createSession"
        session_response = requests.post(
            session_url,
            json={"identifier": username, "password": password},
            timeout=10
        )
        session_response.raise_for_status()

        session_data = session_response.json()
        access_token = session_data["accessJwt"]
        user_did = session_data["did"]

        # Step 2: Fetch the post to determine thread structure
        headers = {"Authorization": f"Bearer {access_token}"}

        # Get the post we're replying to to check if it's part of a thread
        get_posts_url = f"{pds_host}/xrpc/app.bsky.feed.getPosts"
        get_posts_response = requests.get(
            get_posts_url,
            headers=headers,
            params={"uris": uri},
            timeout=10
        )
        get_posts_response.raise_for_status()

        posts_data = get_posts_response.json()
        posts = posts_data.get("posts", [])

        # Determine root for the thread
        root_uri = uri
        root_cid = cid

        if posts:
            post = posts[0]

            # IMPORTANT: Use the CID from the fetched post as the authoritative source
            # This corrects any corruption that may have occurred in the input CID
            # (e.g., character drops during LLM transcription or serialization)
            fetched_cid = post.get("cid")
            if fetched_cid:
                # Extract CID string - may be string or $link object
                if isinstance(fetched_cid, str) and fetched_cid:
                    pass  # Already a string
                elif isinstance(fetched_cid, dict) and "$link" in fetched_cid:
                    fetched_cid = fetched_cid["$link"]
                else:
                    fetched_cid = cid  # Fallback to input

                if fetched_cid != cid:
                    # CID mismatch detected - use the authoritative one from API
                    cid = fetched_cid

            record = post.get("record", {})
            reply_info = record.get("reply")

            # If the post we're replying to is itself a reply, use its root
            if reply_info and isinstance(reply_info, dict):
                root_ref = reply_info.get("root")
                if root_ref and isinstance(root_ref, dict):
                    root_uri = root_ref.get("uri", uri)
                    # Extract CID, handling both string and $link object formats
                    root_cid_raw = root_ref.get("cid", cid)
                    if isinstance(root_cid_raw, str) and root_cid_raw:
                        root_cid = root_cid_raw
                    elif isinstance(root_cid_raw, dict) and "$link" in root_cid_raw:
                        root_cid = root_cid_raw["$link"]
                    else:
                        root_cid = cid  # Fallback
            else:
                # Post is a root post (not a reply), use the corrected cid
                root_cid = cid

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

        # Step 3: Create replies (single or threaded chain)
        create_url = f"{pds_host}/xrpc/com.atproto.repo.createRecord"
        mention_pattern = re.compile(r'@([a-zA-Z0-9.-]+)')
        url_pattern = re.compile(
            r'https?://[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]'
        )

        reply_uris = []
        # For first reply: parent is the target post
        # For subsequent replies: parent is our previous reply
        parent_uri = uri
        parent_cid = cid

        for i, reply_text in enumerate(text):
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            # Process text for rich text features (mentions, links)
            facets = []

            # Detect mentions
            for match in mention_pattern.finditer(reply_text):
                handle = match.group(1)
                start = match.start()
                end = match.end()

                try:
                    resolve_url = f"{pds_host}/xrpc/com.atproto.identity.resolveHandle"
                    resolve_response = requests.get(
                        resolve_url,
                        params={"handle": handle},
                        timeout=5
                    )

                    if resolve_response.status_code == 200:
                        did = resolve_response.json().get("did")
                        if did:
                            byte_start = len(reply_text[:start].encode('UTF-8'))
                            byte_end = len(reply_text[:end].encode('UTF-8'))

                            facets.append({
                                "index": {
                                    "byteStart": byte_start,
                                    "byteEnd": byte_end
                                },
                                "features": [{
                                    "$type": "app.bsky.richtext.facet#mention",
                                    "did": did
                                }]
                            })
                except:
                    pass

            # Detect URLs
            for match in url_pattern.finditer(reply_text):
                url = match.group(0)
                start = match.start()
                end = match.end()

                byte_start = len(reply_text[:start].encode('UTF-8'))
                byte_end = len(reply_text[:end].encode('UTF-8'))

                facets.append({
                    "index": {
                        "byteStart": byte_start,
                        "byteEnd": byte_end
                    },
                    "features": [{
                        "$type": "app.bsky.richtext.facet#link",
                        "uri": url
                    }]
                })

            # Create the reply record
            reply_record = {
                "$type": "app.bsky.feed.post",
                "text": reply_text,
                "createdAt": now,
                "reply": {
                    "parent": {
                        "uri": parent_uri,
                        "cid": parent_cid
                    },
                    "root": {
                        "uri": root_uri,
                        "cid": root_cid
                    }
                }
            }

            if lang:
                reply_record["langs"] = [lang]

            if facets:
                reply_record["facets"] = facets

            # Add image embed to the first reply only
            if i == 0 and image_embed:
                reply_record["embed"] = image_embed

            # Submit the reply
            create_data = {
                "repo": user_did,
                "collection": "app.bsky.feed.post",
                "record": reply_record
            }

            create_response = requests.post(
                create_url,
                headers=headers,
                json=create_data,
                timeout=10
            )
            create_response.raise_for_status()

            response_data = create_response.json()
            new_uri = response_data.get("uri", "")
            new_cid = response_data.get("cid", "")

            reply_uris.append(new_uri)

            # Update parent for next reply in chain
            parent_uri = new_uri
            parent_cid = new_cid

        # Return appropriate message based on single reply or thread
        image_info = ""
        if image_embed:
            image_info = f"\nImage attached: Yes (alt text: {image_alt or 'AI-generated image'})"

        if len(text) == 1:
            return f"Successfully posted reply: {reply_uris[0]} (CID: {parent_cid}){image_info}"
        else:
            uris_text = "\n".join([f"Reply {i+1}: {u}" for i, u in enumerate(reply_uris)])
            return f"Successfully created reply thread with {len(text)} posts!\n{uris_text}{image_info}"

    except requests.exceptions.RequestException as e:
        # Handle network/API errors
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                error_msg = error_data.get('message', error_msg)
            except:
                error_msg = e.response.text or error_msg
        raise Exception(f"Failed to post reply: {error_msg}")
    except KeyError as e:
        # Handle missing fields in API response
        raise Exception(f"Unexpected API response format: missing field {e}")
    except Exception as e:
        # Handle any other errors
        raise Exception(f"Error posting reply: {str(e)}")
