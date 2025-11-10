"""
Bluesky Like Tool

This tool allows umbra to like posts on Bluesky using their AT Protocol URI and CID.
"""

from pydantic import BaseModel, Field, field_validator


class LikeBlueskyPostArgs(BaseModel):
    """Arguments for liking a Bluesky post"""

    uri: str = Field(
        ...,
        description="The AT Protocol URI of the post to like (e.g., at://did:plc:.../app.bsky.feed.post/...)"
    )
    cid: str = Field(
        ...,
        description="The Content ID (CID) of the post to like"
    )

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, v: str) -> str:
        """Validate that the URI is a proper AT Protocol URI"""
        if not v.startswith("at://"):
            raise ValueError("URI must be a valid AT Protocol URI starting with 'at://'")
        return v


def like_bluesky_post(uri: str, cid: str) -> str:
    """
    Like a post on Bluesky.

    This function creates an app.bsky.feed.like record in the Bluesky repository,
    which represents a "like" on a post. The function is completely self-contained
    and uses environment variables for authentication.

    Args:
        uri: The AT Protocol URI of the post to like
        cid: The Content ID of the post to like

    Returns:
        Success message with the post URI

    Raises:
        ValueError: If credentials are missing or URI is invalid
        Exception: If the API request fails
    """
    import os
    import requests
    from datetime import datetime, timezone

    # Validate inputs
    if not uri.startswith("at://"):
        raise ValueError("URI must be a valid AT Protocol URI starting with 'at://'")

    if not cid:
        raise ValueError("CID must be provided")

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

        # Step 2: Create the like record
        like_record = {
            "$type": "app.bsky.feed.like",
            "subject": {
                "uri": uri,
                "cid": cid
            },
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }

        # Step 3: Submit the like via createRecord API
        create_url = f"{pds_host}/xrpc/com.atproto.repo.createRecord"
        headers = {"Authorization": f"Bearer {access_token}"}
        create_data = {
            "repo": user_did,
            "collection": "app.bsky.feed.like",
            "record": like_record
        }

        create_response = requests.post(
            create_url,
            headers=headers,
            json=create_data,
            timeout=10
        )
        create_response.raise_for_status()

        # Return success message
        return f"Successfully liked post: {uri}"

    except requests.exceptions.RequestException as e:
        # Handle network/API errors
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                error_msg = error_data.get('message', error_msg)
            except:
                error_msg = e.response.text or error_msg
        raise Exception(f"Failed to like post: {error_msg}")
    except KeyError as e:
        # Handle missing fields in API response
        raise Exception(f"Unexpected API response format: missing field {e}")
    except Exception as e:
        # Handle any other errors
        raise Exception(f"Error liking post: {str(e)}")
