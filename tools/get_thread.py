"""
Thread Retrieval Tool

Fetches full thread context for a post by its URI. Supports both AT Protocol URIs
and bsky.app URLs. Returns YAML-formatted thread data with all posts in chronological order.
"""
import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class GetThreadByUriArgs(BaseModel):
    """Arguments for fetching a thread by URI"""

    uri: str = Field(
        ...,
        description="Post URI - either AT Protocol URI (at://did:plc:.../app.bsky.feed.post/...) or bsky.app URL (https://bsky.app/profile/.../post/...)"
    )
    include_replies: bool = Field(
        default=True,
        description="Include reply posts below the target post (default: True)"
    )
    max_depth: int = Field(
        default=15,
        description="Maximum reply depth to fetch (default: 15, max: 25)"
    )

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, v: str) -> str:
        """Validate the URI format"""
        # Accept AT Protocol URIs
        if v.startswith("at://"):
            return v

        # Accept bsky.app URLs
        bsky_app_pattern = r'https?://bsky\.app/profile/([^/]+)/post/([a-zA-Z0-9]+)'
        if re.match(bsky_app_pattern, v):
            return v

        raise ValueError(
            "URI must be an AT Protocol URI (at://...) or bsky.app URL (https://bsky.app/profile/.../post/...)"
        )

    @field_validator("max_depth")
    @classmethod
    def validate_max_depth(cls, v: int) -> int:
        """Ensure max_depth is within bounds"""
        return max(0, min(v, 25))


def get_thread_by_uri(uri: str, include_replies: bool = True, max_depth: int = 15) -> str:
    """
    Fetch the full thread context for a post by its URI.

    Use this tool when you encounter a quote post or linked post and want to see the full
    thread context before responding. This is especially useful for:
    - Understanding the full conversation when someone quotes a post from a longer thread
    - Seeing parent posts that provide context for a quoted reply
    - Viewing the complete discussion around a linked post

    Args:
        uri: Post URI - either AT Protocol (at://...) or bsky.app URL
        include_replies: Include replies below the target post (default: True)
        max_depth: Maximum reply depth to fetch (default: 15, max: 25)

    Returns:
        YAML-formatted thread data with all posts in chronological order

    Raises:
        ValueError: If credentials are missing or URI is invalid
        Exception: If the API request fails
    """
    import os
    import re
    import yaml
    import requests

    # Get credentials from environment
    username = os.getenv("BSKY_USERNAME")
    password = os.getenv("BSKY_PASSWORD")
    pds_host = os.getenv("PDS_URI", "https://bsky.social")

    if not username or not password:
        raise ValueError("BSKY_USERNAME and BSKY_PASSWORD environment variables must be set")

    pds_host = pds_host.rstrip("/")

    try:
        # Step 1: Authenticate
        session_url = f"{pds_host}/xrpc/com.atproto.server.createSession"
        session_response = requests.post(
            session_url,
            json={"identifier": username, "password": password},
            timeout=10
        )
        session_response.raise_for_status()

        session_data = session_response.json()
        access_token = session_data["accessJwt"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # Step 2: Convert bsky.app URL to AT URI if needed
        at_uri = uri
        if uri.startswith("http"):
            bsky_app_pattern = r'https?://bsky\.app/profile/([^/]+)/post/([a-zA-Z0-9]+)'
            match = re.match(bsky_app_pattern, uri)
            if match:
                handle_or_did = match.group(1)
                rkey = match.group(2)

                # Resolve handle to DID if needed
                if not handle_or_did.startswith("did:"):
                    resolve_url = f"{pds_host}/xrpc/com.atproto.identity.resolveHandle"
                    resolve_response = requests.get(
                        resolve_url,
                        params={"handle": handle_or_did},
                        timeout=5
                    )
                    if resolve_response.status_code == 200:
                        handle_or_did = resolve_response.json().get("did", handle_or_did)
                    else:
                        raise ValueError(f"Could not resolve handle: {handle_or_did}")

                at_uri = f"at://{handle_or_did}/app.bsky.feed.post/{rkey}"
            else:
                raise ValueError(f"Invalid bsky.app URL format: {uri}")

        # Step 3: Fetch thread
        depth = max_depth if include_replies else 0
        thread_url = f"{pds_host}/xrpc/app.bsky.feed.getPostThread"
        thread_response = requests.get(
            thread_url,
            headers=headers,
            params={
                "uri": at_uri,
                "parentHeight": 80,  # Get all parents
                "depth": depth
            },
            timeout=15
        )
        thread_response.raise_for_status()
        thread_data = thread_response.json()

        # Step 4: Flatten and format thread
        # Process thread structure into chronological post list
        thread = thread_data.get("thread", {})
        posts = []

        # Collect parent posts by traversing up (recursive collection, then reverse)
        parent_nodes = []
        current = thread.get("parent")
        while current and current.get("post"):
            parent_nodes.append(current)
            current = current.get("parent")

        # Add parents in chronological order (oldest first)
        for node in reversed(parent_nodes):
            post = node.get("post", {})
            author = post.get("author", {})
            record = post.get("record", {})

            post_info = {
                "author": author.get("handle", "unknown"),
                "display_name": author.get("displayName", ""),
                "text": record.get("text", ""),
                "created_at": record.get("createdAt", ""),
                "uri": post.get("uri", ""),
                "cid": post.get("cid", ""),
                "likes": post.get("likeCount", 0),
                "reposts": post.get("repostCount", 0),
                "replies": post.get("replyCount", 0)
            }

            reply = record.get("reply", {})
            if reply and reply.get("parent", {}).get("uri"):
                post_info["reply_to"] = reply["parent"]["uri"]

            posts.append(post_info)

        parent_count = len(posts)

        # Add the target post
        if thread.get("post"):
            post = thread.get("post", {})
            author = post.get("author", {})
            record = post.get("record", {})

            post_info = {
                "author": author.get("handle", "unknown"),
                "display_name": author.get("displayName", ""),
                "text": record.get("text", ""),
                "created_at": record.get("createdAt", ""),
                "uri": post.get("uri", ""),
                "cid": post.get("cid", ""),
                "likes": post.get("likeCount", 0),
                "reposts": post.get("repostCount", 0),
                "replies": post.get("replyCount", 0),
                "is_target": True
            }

            reply = record.get("reply", {})
            if reply and reply.get("parent", {}).get("uri"):
                post_info["reply_to"] = reply["parent"]["uri"]

            posts.append(post_info)

        # Add replies if requested (breadth-first traversal with depth limit)
        if include_replies:
            reply_queue = [(thread, 0)]  # (node, depth)
            while reply_queue:
                current_node, current_depth = reply_queue.pop(0)
                if current_depth >= max_depth:
                    continue

                for reply_node in current_node.get("replies", []):
                    if reply_node.get("post"):
                        post = reply_node.get("post", {})
                        author = post.get("author", {})
                        record = post.get("record", {})

                        post_info = {
                            "author": author.get("handle", "unknown"),
                            "display_name": author.get("displayName", ""),
                            "text": record.get("text", ""),
                            "created_at": record.get("createdAt", ""),
                            "uri": post.get("uri", ""),
                            "cid": post.get("cid", ""),
                            "likes": post.get("likeCount", 0),
                            "reposts": post.get("repostCount", 0),
                            "replies": post.get("replyCount", 0)
                        }

                        reply = record.get("reply", {})
                        if reply and reply.get("parent", {}).get("uri"):
                            post_info["reply_to"] = reply["parent"]["uri"]

                        posts.append(post_info)
                        reply_queue.append((reply_node, current_depth + 1))

        # Calculate reply count
        reply_count = len(posts) - parent_count - 1

        # Build result
        result = {
            "thread_summary": {
                "target_uri": at_uri,
                "parent_posts": parent_count,
                "reply_posts": max(0, reply_count),
                "total_posts": len(posts)
            },
            "posts": posts
        }

        return yaml.dump(result, default_flow_style=False, sort_keys=False, allow_unicode=True)

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                error_msg = error_data.get('message', error_msg)
            except:
                error_msg = e.response.text or error_msg
        raise Exception(f"Failed to fetch thread: {error_msg}")
    except Exception as e:
        if "Failed to fetch thread" in str(e):
            raise
        raise Exception(f"Error fetching thread: {str(e)}")
