"""Feed tool for retrieving Bluesky feeds."""
from typing import List, Type, Optional
from pydantic import BaseModel, Field
from letta_client.client import BaseTool


class FeedArgs(BaseModel):
    feed_uri: Optional[str] = Field(None, description="Custom feed URI (e.g., 'at://did:plc:abc/app.bsky.feed.generator/feed-name'). If not provided, returns home timeline")
    max_posts: int = Field(default=25, description="Maximum number of posts to retrieve (max 100)")


class GetBlueskyFeedTool(BaseTool):
    name: str = "get_bluesky_feed"
    args_schema: Type[BaseModel] = FeedArgs
    description: str = "Retrieve a Bluesky feed (home timeline or custom feed)"
    tags: List[str] = ["bluesky", "feed", "timeline"]
    
    def run(self, feed_uri: Optional[str] = None, max_posts: int = 25) -> str:
        """Retrieve a Bluesky feed."""
        import os
        import yaml
        import requests
        
        try:
            # Validate inputs
            max_posts = min(max_posts, 100)
            
            # Get credentials from environment
            username = os.getenv("BSKY_USERNAME")
            password = os.getenv("BSKY_PASSWORD")
            pds_host = os.getenv("PDS_URI", "https://bsky.social")
            
            if not username or not password:
                return "Error: BSKY_USERNAME and BSKY_PASSWORD environment variables must be set"
            
            # Create session
            session_url = f"{pds_host}/xrpc/com.atproto.server.createSession"
            session_data = {
                "identifier": username,
                "password": password
            }
            
            try:
                session_response = requests.post(session_url, json=session_data, timeout=10)
                session_response.raise_for_status()
                session = session_response.json()
                access_token = session.get("accessJwt")
                
                if not access_token:
                    return "Error: Failed to get access token from session"
            except Exception as e:
                return f"Error: Authentication failed. ({str(e)})"
            
            # Get feed
            headers = {"Authorization": f"Bearer {access_token}"}
            
            if feed_uri:
                # Custom feed
                feed_url = f"{pds_host}/xrpc/app.bsky.feed.getFeed"
                params = {
                    "feed": feed_uri,
                    "limit": max_posts
                }
                feed_type = "custom"
                feed_name = feed_uri.split('/')[-1] if '/' in feed_uri else feed_uri
            else:
                # Home timeline
                feed_url = f"{pds_host}/xrpc/app.bsky.feed.getTimeline"
                params = {
                    "limit": max_posts
                }
                feed_type = "home"
                feed_name = "timeline"
            
            try:
                response = requests.get(feed_url, headers=headers, params=params, timeout=10)
                response.raise_for_status()
                feed_data = response.json()
            except Exception as e:
                return f"Error: Failed to get feed. ({str(e)})"
            
            # Format posts
            posts = []
            for item in feed_data.get("feed", []):
                post = item.get("post", {})
                author = post.get("author", {})
                record = post.get("record", {})
                
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
                
                # Add repost info if present
                if "reason" in item and item["reason"]:
                    reason = item["reason"]
                    if reason.get("$type") == "app.bsky.feed.defs#reasonRepost":
                        by = reason.get("by", {})
                        post_data["reposted_by"] = {
                            "handle": by.get("handle", ""),
                            "display_name": by.get("displayName", ""),
                        }
                
                # Add reply info if present
                if "reply" in record and record["reply"]:
                    parent = record["reply"].get("parent", {})
                    post_data["reply_to"] = {
                        "uri": parent.get("uri", ""),
                        "cid": parent.get("cid", ""),
                    }
                
                posts.append(post_data)
            
            # Format response
            feed_result = {
                "feed": {
                    "type": feed_type,
                    "name": feed_name,
                    "post_count": len(posts),
                    "posts": posts
                }
            }
            
            if feed_uri:
                feed_result["feed"]["uri"] = feed_uri
            
            return yaml.dump(feed_result, default_flow_style=False, sort_keys=False)
            
        except Exception as e:
            return f"Error retrieving feed: {str(e)}"