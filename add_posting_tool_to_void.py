#!/usr/bin/env python3
"""
Add Bluesky posting tool to the main void agent.
"""

import os
import logging
from letta_client import Letta

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("add_posting_tool")

def create_posting_tool(client: Letta):
    """Create the Bluesky posting tool using Letta SDK."""
    
    def post_to_bluesky(text: str) -> str:
        """
        Post a message to Bluesky.
        
        Args:
            text: The text content of the post (required)
            
        Returns:
            Status message with the post URI if successful, error message if failed
        """
        import os
        import requests
        import json
        import re
        from datetime import datetime, timezone
        
        # Check character limit
        if len(text) > 300:
            raise ValueError(f"Post text exceeds 300 character limit ({len(text)} characters)")
        
        try:
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
                return f"✅ Post created successfully! URI: {post_uri}"
                    
            except Exception as e:
                return f"Error: Failed to create post. ({str(e)})"
            
        except Exception as e:
            error_msg = f"Error posting to Bluesky: {str(e)}"
            return error_msg
    
    # Create the tool using upsert
    tool = client.tools.upsert_from_function(
        func=post_to_bluesky,
        tags=["bluesky", "post", "create"]
    )
    
    logger.info(f"Created tool: {tool.name} (ID: {tool.id})")
    return tool

def add_posting_tool_to_void():
    """Add posting tool to the void agent."""
    
    # Create client
    client = Letta(token=os.environ["LETTA_API_KEY"])
    
    logger.info("Adding posting tool to void agent...")
    
    # Create the posting tool
    posting_tool = create_posting_tool(client)
    
    # Find the void agent
    agents = client.agents.list(name="void")
    if not agents:
        print("❌ Void agent not found")
        return
    
    void_agent = agents[0]
    
    # Get current tools
    current_tools = client.agents.tools.list(agent_id=void_agent.id)
    tool_names = [tool.name for tool in current_tools]
    
    # Add posting tool if not already present
    if posting_tool.name not in tool_names:
        client.agents.tools.attach(agent_id=void_agent.id, tool_id=posting_tool.id)
        logger.info(f"Added {posting_tool.name} to void agent")
        print(f"✅ Added post_to_bluesky tool to void agent!")
        print(f"\nVoid agent can now post to Bluesky:")
        print(f"   - Simple post: 'Post \"Hello world!\" to Bluesky'")
        print(f"   - With mentions: 'Post \"Thanks @cameron.pfiffer.org for the help!\"'")
        print(f"   - With links: 'Post \"Check out https://bsky.app\"'")
    else:
        logger.info(f"Tool {posting_tool.name} already attached to void agent")
        print(f"✅ Posting tool already present on void agent")

def main():
    """Main function."""
    try:
        add_posting_tool_to_void()
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()