"""
Bluesky Reply Tool

This tool allows umbra to reply to any post on Bluesky using its AT Protocol URI and CID.
Unlike add_post_to_bluesky_reply_thread which only works in notification processing,
this tool is self-contained and works anywhere (feed reading, search results, etc.).
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional


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
    text: str = Field(
        ...,
        description="The reply text content (max 300 characters)"
    )
    lang: Optional[str] = Field(
        default="en-US",
        description="Language code for the reply (e.g., 'en-US', 'es', 'ja', 'th'). Defaults to 'en-US'"
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
    def validate_text_length(cls, v: str) -> str:
        """Validate text length"""
        if len(v) > 300:
            raise ValueError(f"Text exceeds 300 character limit (current: {len(v)} characters)")
        return v


def reply_to_bluesky_post(uri: str, cid: str, text: str, lang: str = "en-US") -> str:
    """
    Reply to a post on Bluesky.

    This function creates a reply to any Bluesky post, properly handling thread structure.
    If the post being replied to is itself a reply, this maintains the thread by using
    the correct root post. The function is completely self-contained and uses environment
    variables for authentication.

    Args:
        uri: The AT Protocol URI of the post to reply to
        cid: The Content ID of the post to reply to
        text: The reply text (max 300 characters)
        lang: Language code for the reply (e.g., 'en-US', 'es', 'ja', 'th'). Defaults to 'en-US'

    Returns:
        Success message with the reply URI

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

    if len(text) > 300:
        raise ValueError(f"Text exceeds 300 character limit (current: {len(text)} characters)")

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
            record = post.get("record", {})
            reply_info = record.get("reply")

            # If the post we're replying to is itself a reply, use its root
            if reply_info and isinstance(reply_info, dict):
                root_ref = reply_info.get("root")
                if root_ref and isinstance(root_ref, dict):
                    root_uri = root_ref.get("uri", uri)
                    root_cid = root_ref.get("cid", cid)

        # Step 3: Process text for rich text features (mentions, links, etc.)
        # Detect mentions
        facets = []
        mention_pattern = re.compile(r'@([a-zA-Z0-9.-]+)')

        for match in mention_pattern.finditer(text):
            handle = match.group(1)
            start = match.start()
            end = match.end()

            # Resolve handle to DID
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
                        # Calculate byte positions (important for UTF-8)
                        byte_start = len(text[:start].encode('UTF-8'))
                        byte_end = len(text[:end].encode('UTF-8'))

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
                # Skip mention if resolution fails
                pass

        # Detect URLs
        url_pattern = re.compile(
            r'https?://[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]'
        )

        for match in url_pattern.finditer(text):
            url = match.group(0)
            start = match.start()
            end = match.end()

            # Calculate byte positions
            byte_start = len(text[:start].encode('UTF-8'))
            byte_end = len(text[:end].encode('UTF-8'))

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

        # Step 4: Create the reply record
        reply_record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "reply": {
                "parent": {
                    "uri": uri,
                    "cid": cid
                },
                "root": {
                    "uri": root_uri,
                    "cid": root_cid
                }
            }
        }

        # Add language if specified
        if lang:
            reply_record["langs"] = [lang]

        # Add facets if any were found
        if facets:
            reply_record["facets"] = facets

        # Step 5: Submit the reply via createRecord API
        create_url = f"{pds_host}/xrpc/com.atproto.repo.createRecord"
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
        reply_uri = response_data.get("uri", "")
        reply_cid = response_data.get("cid", "")

        # Return success message with URI and CID (CID needed for thread chaining)
        return f"Successfully posted reply: {reply_uri} (CID: {reply_cid})"

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
