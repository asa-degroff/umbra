#!/usr/bin/env python3
"""
Add Bluesky search tool to the main void agent.
"""

import os
import logging
from letta_client import Letta

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("add_search_tool")

def create_search_posts_tool(client: Letta):
    """Create the Bluesky search posts tool using Letta SDK."""
    
    def search_bluesky_posts(query: str, max_results: int = 25, author: str = None, sort: str = "latest") -> str:
        """
        Search for posts on Bluesky matching the given criteria.
        
        Args:
            query: Search query string (required)
            max_results: Maximum number of results to return (default: 25, max: 100)
            author: Filter to posts by a specific author handle (optional)
            sort: Sort order - "latest" or "top" (default: "latest")
            
        Returns:
            YAML-formatted search results with posts and metadata
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
            
            # Build search parameters
            params = {
                "q": query,
                "limit": min(max_results, 100),
                "sort": sort
            }
            
            # Add optional author filter
            if author:
                params["author"] = author.lstrip('@')
            
            # Make authenticated search request
            try:
                search_url = f"{pds_host}/xrpc/app.bsky.feed.searchPosts"
                headers = {"Authorization": f"Bearer {access_token}"}
                search_response = requests.get(search_url, params=params, headers=headers, timeout=10)
                search_response.raise_for_status()
                search_data = search_response.json()
            except Exception as e:
                return f"Error: Search failed for query '{query}'. ({str(e)})"
            
            # Build search results structure
            results_data = {
                "search_results": {
                    "query": query,
                    "timestamp": datetime.now().isoformat(),
                    "parameters": {
                        "sort": sort,
                        "max_results": max_results,
                        "author_filter": author if author else "none"
                    },
                    "results": search_data
                }
            }
            
            # Fields to strip (same as profile research)
            strip_fields = [
                "cid", "rev", "did", "uri", "langs", "threadgate", "py_type",
                "labels", "facets", "avatar", "viewer", "indexed_at", "indexedAt", 
                "tags", "associated", "thread_context", "image", "aspect_ratio",
                "alt", "thumb", "fullsize", "root", "parent", "created_at", 
                "createdAt", "verification", "embedding_disabled", "thread_muted",
                "reply_disabled", "pinned", "like", "repost", "blocked_by",
                "blocking", "blocking_by_list", "followed_by", "following",
                "known_followers", "muted", "muted_by_list", "root_author_like",
                "embed", "entities", "reason", "feedContext"
            ]
            
            # Convert to YAML directly without field stripping complications
            # The field stripping with regex is causing JSON parsing errors
            # So let's just pass the raw data through yaml.dump which handles it gracefully
            return yaml.dump(results_data, default_flow_style=False, allow_unicode=True)
            
        except Exception as e:
            error_msg = f"Error searching posts: {str(e)}"
            return error_msg
    
    # Create the tool using upsert
    tool = client.tools.upsert_from_function(
        func=search_bluesky_posts,
        tags=["bluesky", "search", "posts"]
    )
    
    logger.info(f"Created tool: {tool.name} (ID: {tool.id})")
    return tool

def add_search_tool_to_void():
    """Add search tool to the void agent."""
    
    # Create client
    client = Letta(token=os.environ["LETTA_API_KEY"])
    
    logger.info("Adding search tool to void agent...")
    
    # Create the search tool
    search_tool = create_search_posts_tool(client)
    
    # Find the void agent
    agents = client.agents.list(name="void")
    if not agents:
        print("❌ Void agent not found")
        return
    
    void_agent = agents[0]
    
    # Get current tools
    current_tools = client.agents.tools.list(agent_id=void_agent.id)
    tool_names = [tool.name for tool in current_tools]
    
    # Add search tool if not already present
    if search_tool.name not in tool_names:
        client.agents.tools.attach(agent_id=void_agent.id, tool_id=search_tool.id)
        logger.info(f"Added {search_tool.name} to void agent")
        print(f"✅ Added search_bluesky_posts tool to void agent!")
        print(f"\nVoid agent can now search Bluesky posts:")
        print(f"   - Basic search: 'Search for posts about AI safety'")
        print(f"   - Author filter: 'Search posts by @cameron.pfiffer.org about letta'")
        print(f"   - Top posts: 'Search top posts about ATProto'")
    else:
        logger.info(f"Tool {search_tool.name} already attached to void agent")
        print(f"✅ Search tool already present on void agent")

def main():
    """Main function."""
    try:
        add_search_tool_to_void()
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()