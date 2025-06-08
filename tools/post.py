"""Post tool for creating Bluesky posts."""
from typing import List, Type
from pydantic import BaseModel, Field
from letta_client.client import BaseTool


class PostArgs(BaseModel):
    text: str = Field(..., description="The text content to post (max 300 characters)")


class PostToBlueskyTool(BaseTool):
    name: str = "post_to_bluesky"
    args_schema: Type[BaseModel] = PostArgs
    description: str = "Post a message to Bluesky"
    tags: List[str] = ["bluesky", "post", "create"]
    
    def run(self, text: str) -> str:
        """
        Post a message to Bluesky.
        
        Args:
            text: The text content to post (max 300 characters)
            
        Returns:
            Success message with post URL if successful, error message if failed
        """
        import os
        import re
        import requests
        from datetime import datetime, timezone
        
        try:
            # Validate character limit
            if len(text) > 300:
                return f"Error: Post exceeds 300 character limit (current: {len(text)} characters)"
            
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
                user_did = session.get("did")
                
                if not access_token or not user_did:
                    return "Error: Failed to get access token or DID from session"
            except Exception as e:
                return f"Error: Authentication failed. ({str(e)})"
            
            # Helper function to parse mentions and create facets
            def parse_mentions(text: str):
                facets = []
                # Regex for mentions based on Bluesky handle syntax
                mention_regex = rb"[$|\W](@([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
                text_bytes = text.encode("UTF-8")
                
                for m in re.finditer(mention_regex, text_bytes):
                    handle = m.group(1)[1:].decode("UTF-8")  # Remove @ prefix
                    
                    # Resolve handle to DID
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
                                    "byteStart": m.start(1),
                                    "byteEnd": m.end(1),
                                },
                                "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}],
                            })
                    except:
                        # If handle resolution fails, skip this mention
                        continue
                
                return facets
            
            # Helper function to parse URLs and create facets
            def parse_urls(text: str):
                facets = []
                # URL regex
                url_regex = rb"[$|\W](https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
                text_bytes = text.encode("UTF-8")
                
                for m in re.finditer(url_regex, text_bytes):
                    url = m.group(1).decode("UTF-8")
                    facets.append({
                        "index": {
                            "byteStart": m.start(1),
                            "byteEnd": m.end(1),
                        },
                        "features": [
                            {
                                "$type": "app.bsky.richtext.facet#link",
                                "uri": url,
                            }
                        ],
                    })
                
                return facets
            
            
            # Build the post record
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            
            post_record = {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": now,
            }
            
            # Add facets for mentions and links
            facets = parse_mentions(text) + parse_urls(text)
            if facets:
                post_record["facets"] = facets
            
            # Create the post
            try:
                create_record_url = f"{pds_host}/xrpc/com.atproto.repo.createRecord"
                headers = {"Authorization": f"Bearer {access_token}"}
                
                create_data = {
                    "repo": user_did,
                    "collection": "app.bsky.feed.post",
                    "record": post_record
                }
                
                post_response = requests.post(create_record_url, headers=headers, json=create_data, timeout=10)
                post_response.raise_for_status()
                result = post_response.json()
                
                post_uri = result.get("uri")
                # Extract handle from session if available
                handle = session.get("handle", username)
                rkey = post_uri.split("/")[-1] if post_uri else ""
                post_url = f"https://bsky.app/profile/{handle}/post/{rkey}"
                
                return f"Successfully posted to Bluesky!\nPost URL: {post_url}\nText: {text}"
                    
            except Exception as e:
                return f"Error: Failed to create post. ({str(e)})"
            
        except Exception as e:
            return f"Error posting to Bluesky: {str(e)}"