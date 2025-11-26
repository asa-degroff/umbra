"""Author feed tool for retrieving posts from a specific Bluesky user's profile."""
from pydantic import BaseModel, Field


class AuthorFeedArgs(BaseModel):
    actor: str = Field(..., description="User handle (e.g., 'user.bsky.social') or DID (e.g., 'did:plc:xyz')")
    limit: int = Field(default=10, description="Number of posts to retrieve (max 100)")


def get_author_feed(actor: str, limit: int = 10) -> str:
    """
    Retrieve recent posts from a Bluesky user's profile.

    Args:
        actor: User handle or DID
        limit: Number of posts to retrieve (max 100, default 10)

    Returns:
        YAML-formatted list of posts with metadata for interactions
    """
    import os
    import yaml
    import requests

    try:
        # Validate limit
        limit = min(max(limit, 1), 100)

        # Get credentials from environment
        username = os.getenv("BSKY_USERNAME")
        password = os.getenv("BSKY_PASSWORD")
        pds_host = os.getenv("PDS_URI", "https://bsky.social")

        if not username or not password:
            raise Exception("BSKY_USERNAME and BSKY_PASSWORD environment variables must be set")

        # Normalize actor - strip @ if present
        if actor.startswith("@"):
            actor = actor[1:]

        # Create session
        session_url = f"{pds_host}/xrpc/com.atproto.server.createSession"
        try:
            session_response = requests.post(
                session_url,
                json={"identifier": username, "password": password},
                timeout=10
            )
            session_response.raise_for_status()
            session = session_response.json()
            access_token = session.get("accessJwt")

            if not access_token:
                raise Exception("Failed to get access token from session")
        except Exception as e:
            raise Exception(f"Authentication failed: {str(e)}")

        # Fetch author feed
        headers = {"Authorization": f"Bearer {access_token}"}
        feed_url = f"{pds_host}/xrpc/app.bsky.feed.getAuthorFeed"

        # Request more posts than limit to account for reposts we'll filter out
        params = {
            "actor": actor,
            "limit": min(limit * 2, 100),  # Request extra to account for filtered reposts
            "filter": "posts_no_replies"  # Only original posts, no replies
        }

        try:
            response = requests.get(feed_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            feed_data = response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                raise Exception(f"Invalid actor: '{actor}' - user not found or invalid handle/DID")
            raise Exception(f"Failed to fetch author feed: {str(e)}")

        # Get author info from the first post
        author_info = None

        # Format results, filtering out reposts
        results = []
        for item in feed_data.get("feed", []):
            post = item.get("post", {})

            # Skip reposts (where reason indicates repost)
            if item.get("reason") and item["reason"].get("$type") == "app.bsky.feed.defs#reasonRepost":
                continue

            author = post.get("author", {})
            record = post.get("record", {})

            # Capture author info from first post
            if author_info is None:
                author_info = {
                    "handle": author.get("handle", ""),
                    "display_name": author.get("displayName", ""),
                    "did": author.get("did", "")
                }

            post_data = {
                "author": {
                    "handle": author.get("handle", ""),
                    "display_name": author.get("displayName", ""),
                },
                "text": record.get("text", ""),
                "created_at": record.get("createdAt", ""),
                "uri": post.get("uri", ""),
                "cid": post.get("cid", ""),
                "like_count": post.get("likeCount", 0),
                "repost_count": post.get("repostCount", 0),
                "reply_count": post.get("replyCount", 0),
            }

            # Add reply info if this post is a reply
            if "reply" in record and record["reply"]:
                post_data["reply_to"] = {
                    "uri": record["reply"].get("parent", {}).get("uri", ""),
                    "cid": record["reply"].get("parent", {}).get("cid", ""),
                }

            results.append(post_data)

            # Stop once we have enough posts
            if len(results) >= limit:
                break

        return yaml.dump({
            "author_feed": {
                "actor": actor,
                "author": author_info,
                "post_count": len(results),
                "posts": results
            }
        }, default_flow_style=False, sort_keys=False)

    except Exception as e:
        raise Exception(f"Error fetching author feed: {str(e)}")
