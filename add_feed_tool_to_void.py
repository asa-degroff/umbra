#!/usr/bin/env python3
"""
Add Bluesky feed retrieval tool to the main void agent.
"""

import os
import logging
from letta_client import Letta

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("add_feed_tool")

def create_feed_tool(client: Letta):
    """Create the Bluesky feed retrieval tool using Letta SDK."""
    
    def get_bluesky_feed(feed_uri: str = None, max_posts: int = 25) -> str:
        """
        Retrieve a Bluesky feed. If no feed_uri provided, gets the authenticated user's home timeline.
        
        Args:
            feed_uri: The AT-URI of the feed to retrieve (optional - defaults to home timeline)
            max_posts: Maximum number of posts to return (default: 25, max: 100)
            
        Returns:
            YAML-formatted feed data with posts and metadata
        """
        import os
        import requests
        import json
        import yaml
        from datetime import datetime
        
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
                
                if not access_token:
                    return "Error: Failed to get access token from session"
            except Exception as e:
                return f"Error: Authentication failed. ({str(e)})"
            
            # Build feed parameters
            params = {
                "limit": min(max_posts, 100)
            }
            
            # Determine which endpoint to use
            if feed_uri:
                # Use getFeed for custom feeds
                feed_url = f"{pds_host}/xrpc/app.bsky.feed.getFeed"
                params["feed"] = feed_uri
                feed_type = "custom_feed"
            else:
                # Use getTimeline for home feed
                feed_url = f"{pds_host}/xrpc/app.bsky.feed.getTimeline"
                feed_type = "home_timeline"
            
            # Make authenticated feed request
            try:
                headers = {"Authorization": f"Bearer {access_token}"}
                feed_response = requests.get(feed_url, params=params, headers=headers, timeout=10)
                feed_response.raise_for_status()
                feed_data = feed_response.json()
            except Exception as e:
                feed_identifier = feed_uri if feed_uri else "home timeline"
                return f"Error: Failed to retrieve feed '{feed_identifier}'. ({str(e)})"
            
            # Build feed results structure
            results_data = {
                "feed_data": {
                    "feed_type": feed_type,
                    "feed_uri": feed_uri if feed_uri else "home_timeline",
                    "timestamp": datetime.now().isoformat(),
                    "parameters": {
                        "max_posts": max_posts,
                        "user": username
                    },
                    "results": feed_data
                }
            }
            
            # Convert to YAML directly without field stripping complications
            # This avoids the JSON parsing errors we had before
            return yaml.dump(results_data, default_flow_style=False, allow_unicode=True)
            
        except Exception as e:
            error_msg = f"Error retrieving feed: {str(e)}"
            return error_msg
    
    # Create the tool using upsert
    tool = client.tools.upsert_from_function(
        func=get_bluesky_feed,
        tags=["bluesky", "feed", "timeline"]
    )
    
    logger.info(f"Created tool: {tool.name} (ID: {tool.id})")
    return tool

def add_feed_tool_to_void():
    """Add feed tool to the void agent."""
    
    # Create client
    client = Letta(token=os.environ["LETTA_API_KEY"])
    
    logger.info("Adding feed tool to void agent...")
    
    # Create the feed tool
    feed_tool = create_feed_tool(client)
    
    # Find the void agent
    agents = client.agents.list(name="void")
    if not agents:
        print("❌ Void agent not found")
        return
    
    void_agent = agents[0]
    
    # Get current tools
    current_tools = client.agents.tools.list(agent_id=void_agent.id)
    tool_names = [tool.name for tool in current_tools]
    
    # Add feed tool if not already present
    if feed_tool.name not in tool_names:
        client.agents.tools.attach(agent_id=void_agent.id, tool_id=feed_tool.id)
        logger.info(f"Added {feed_tool.name} to void agent")
        print(f"✅ Added get_bluesky_feed tool to void agent!")
        print(f"\nVoid agent can now retrieve Bluesky feeds:")
        print(f"   - Home timeline: 'Show me my home feed'")
        print(f"   - Custom feed: 'Get posts from at://did:plc:xxx/app.bsky.feed.generator/xxx'")
        print(f"   - Limited posts: 'Show me the latest 10 posts from my timeline'")
    else:
        logger.info(f"Tool {feed_tool.name} already attached to void agent")
        print(f"✅ Feed tool already present on void agent")

def main():
    """Main function."""
    try:
        add_feed_tool_to_void()
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()