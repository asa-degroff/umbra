#!/usr/bin/env python3
"""
Script to create a Letta agent that researches Bluesky profiles and updates 
the model's understanding of users.
"""

import os
import logging
from letta_client import Letta
from utils import upsert_block, upsert_agent

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("profile_researcher")

# Use the "Bluesky" project
PROJECT_ID = "5ec33d52-ab14-4fd6-91b5-9dbc43e888a8"

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
            # Use public Bluesky API
            base_url = "https://public.api.bsky.app"
            
            # Build search parameters
            params = {
                "q": query,
                "limit": min(max_results, 100),
                "sort": sort
            }
            
            # Add optional author filter
            if author:
                params["author"] = author.lstrip('@')
            
            # Make search request
            try:
                search_url = f"{base_url}/xrpc/app.bsky.feed.searchPosts"
                search_response = requests.get(search_url, params=params, timeout=10)
                search_response.raise_for_status()
                search_data = search_response.json()
            except requests.exceptions.HTTPError as e:
                raise RuntimeError(f"Search failed with HTTP {e.response.status_code}: {e.response.text}")
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"Network error during search: {str(e)}")
            except Exception as e:
                raise RuntimeError(f"Unexpected error during search: {str(e)}")
            
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
            
            # Fields to strip for cleaner output
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
            
            # Remove unwanted fields by traversing the data structure
            def remove_fields(obj, fields_to_remove):
                if isinstance(obj, dict):
                    return {k: remove_fields(v, fields_to_remove) 
                           for k, v in obj.items() 
                           if k not in fields_to_remove}
                elif isinstance(obj, list):
                    return [remove_fields(item, fields_to_remove) for item in obj]
                else:
                    return obj
            
            # Clean the data
            cleaned_data = remove_fields(results_data, strip_fields)
            
            # Convert to YAML for better readability
            return yaml.dump(cleaned_data, default_flow_style=False, allow_unicode=True)
            
        except ValueError as e:
            # User-friendly errors
            raise ValueError(str(e))
        except RuntimeError as e:
            # Network/API errors
            raise RuntimeError(str(e))
        except yaml.YAMLError as e:
            # YAML conversion errors
            raise RuntimeError(f"Error formatting output: {str(e)}")
        except Exception as e:
            # Catch-all for unexpected errors
            raise RuntimeError(f"Unexpected error searching posts with query '{query}': {str(e)}")
    
    # Create the tool using upsert
    tool = client.tools.upsert_from_function(
        func=search_bluesky_posts,
        tags=["bluesky", "search", "posts"]
    )
    
    logger.info(f"Created tool: {tool.name} (ID: {tool.id})")
    return tool

def create_profile_research_tool(client: Letta):
    """Create the Bluesky profile research tool using Letta SDK."""
    
    def research_bluesky_profile(handle: str, max_posts: int = 20) -> str:
        """
        Research a Bluesky user's profile and recent posts to understand their interests and behavior.
        
        Args:
            handle: The Bluesky handle to research (e.g., 'cameron.pfiffer.org' or '@cameron.pfiffer.org')
            max_posts: Maximum number of recent posts to analyze (default: 20)
            
        Returns:
            A comprehensive analysis of the user's profile and posting patterns
        """
        import os
        import requests
        import json
        import yaml
        from datetime import datetime
        
        try:
            # Clean handle (remove @ if present)
            clean_handle = handle.lstrip('@')
            
            # Use public Bluesky API (no auth required for public data)
            base_url = "https://public.api.bsky.app"
            
            # Get profile information
            try:
                profile_url = f"{base_url}/xrpc/app.bsky.actor.getProfile"
                profile_response = requests.get(profile_url, params={"actor": clean_handle}, timeout=10)
                profile_response.raise_for_status()
                profile_data = profile_response.json()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    raise ValueError(f"Profile @{clean_handle} not found")
                raise RuntimeError(f"HTTP error {e.response.status_code}: {e.response.text}")
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"Network error: {str(e)}")
            except Exception as e:
                raise RuntimeError(f"Unexpected error fetching profile: {str(e)}")
            
            # Get recent posts feed
            try:
                feed_url = f"{base_url}/xrpc/app.bsky.feed.getAuthorFeed"
                feed_response = requests.get(feed_url, params={
                    "actor": clean_handle,
                    "limit": min(max_posts, 50)  # API limit
                }, timeout=10)
                feed_response.raise_for_status()
                feed_data = feed_response.json()
            except Exception as e:
                # Continue with empty feed if posts can't be fetched
                feed_data = {"feed": []}
            
            # Build research data structure
            research_data = {
                "profile_research": {
                    "handle": f"@{clean_handle}",
                    "timestamp": datetime.now().isoformat(),
                    "profile": profile_data,
                    "author_feed": feed_data
                }
            }
            
            # Fields to strip for cleaner output
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
            
            # Remove unwanted fields by traversing the data structure
            def remove_fields(obj, fields_to_remove):
                if isinstance(obj, dict):
                    return {k: remove_fields(v, fields_to_remove) 
                           for k, v in obj.items() 
                           if k not in fields_to_remove}
                elif isinstance(obj, list):
                    return [remove_fields(item, fields_to_remove) for item in obj]
                else:
                    return obj
            
            # Clean the data
            cleaned_data = remove_fields(research_data, strip_fields)
            
            # Convert to YAML for better readability
            return yaml.dump(cleaned_data, default_flow_style=False, allow_unicode=True)
            
        except ValueError as e:
            # User-friendly errors
            raise ValueError(str(e))
        except RuntimeError as e:
            # Network/API errors
            raise RuntimeError(str(e))
        except yaml.YAMLError as e:
            # YAML conversion errors
            raise RuntimeError(f"Error formatting output: {str(e)}")
        except Exception as e:
            # Catch-all for unexpected errors
            raise RuntimeError(f"Unexpected error researching profile {handle}: {str(e)}")
    
    # Create or update the tool using upsert
    tool = client.tools.upsert_from_function(
        func=research_bluesky_profile,
        tags=["bluesky", "profile", "research"]
    )
    
    logger.info(f"Created tool: {tool.name} (ID: {tool.id})")
    return tool

def create_block_management_tools(client: Letta):
    """Create tools for attaching and detaching user blocks."""
    
    def attach_user_block(handle: str) -> str:
        """
        Create (if needed) and attach a user-specific memory block for a Bluesky user.
        
        Args:
            handle: The Bluesky handle (e.g., 'cameron.pfiffer.org' or '@cameron.pfiffer.org')
            
        Returns:
            Status message about the block attachment
        """
        import os
        from letta_client import Letta
        
        try:
            # Clean handle for block label
            clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_')
            block_label = f"user_{clean_handle}"
            
            # Initialize Letta client 
            letta_client = Letta(token=os.environ["LETTA_API_KEY"])
            
            # Get current agent (this tool is being called by)
            # We need to find the agent that's calling this tool
            # For now, we'll find the profile-researcher agent
            agents = letta_client.agents.list(name="profile-researcher")
            if not agents:
                return "Error: Could not find profile-researcher agent"
            
            agent = agents[0]
            
            # Check if block already exists and is attached
            agent_blocks = letta_client.agents.blocks.list(agent_id=agent.id)
            for block in agent_blocks:
                if block.label == block_label:
                    return f"User block for @{handle} is already attached (label: {block_label})"
            
            # Create or get the user block
            existing_blocks = letta_client.blocks.list(label=block_label)
            
            if existing_blocks:
                user_block = existing_blocks[0]
                action = "Retrieved existing"
            else:
                user_block = letta_client.blocks.create(
                    label=block_label,
                    value=f"User information for @{handle} will be stored here as I learn about them through profile research and interactions.",
                    description=f"Stores detailed information about Bluesky user @{handle}, including their interests, posting patterns, personality traits, and interaction history."
                )
                action = "Created new"
            
            # Attach block to agent
            letta_client.agents.blocks.attach(agent_id=agent.id, block_id=user_block.id)
            
            return f"{action} and attached user block for @{handle} (label: {block_label}). I can now store and access information about this user."
            
        except Exception as e:
            return f"Error attaching user block for @{handle}: {str(e)}"
    
    def detach_user_block(handle: str) -> str:
        """
        Detach a user-specific memory block from the agent.
        
        Args:
            handle: The Bluesky handle (e.g., 'cameron.pfiffer.org' or '@cameron.pfiffer.org')
            
        Returns:
            Status message about the block detachment
        """
        import os
        from letta_client import Letta
        
        try:
            # Clean handle for block label
            clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_')
            block_label = f"user_{clean_handle}"
            
            # Initialize Letta client
            letta_client = Letta(token=os.environ["LETTA_API_KEY"])
            
            # Get current agent
            agents = letta_client.agents.list(name="profile-researcher")
            if not agents:
                return "Error: Could not find profile-researcher agent"
            
            agent = agents[0]
            
            # Find the block to detach
            agent_blocks = letta_client.agents.blocks.list(agent_id=agent.id)
            user_block = None
            for block in agent_blocks:
                if block.label == block_label:
                    user_block = block
                    break
            
            if not user_block:
                return f"User block for @{handle} is not currently attached (label: {block_label})"
            
            # Detach block from agent
            letta_client.agents.blocks.detach(agent_id=agent.id, block_id=user_block.id)
            
            return f"Detached user block for @{handle} (label: {block_label}). The block still exists and can be reattached later."
            
        except Exception as e:
            return f"Error detaching user block for @{handle}: {str(e)}"
    
    def update_user_block(handle: str, new_content: str) -> str:
        """
        Update the content of a user-specific memory block.
        
        Args:
            handle: The Bluesky handle (e.g., 'cameron.pfiffer.org' or '@cameron.pfiffer.org')
            new_content: New content to store in the user block
            
        Returns:
            Status message about the block update
        """
        import os
        from letta_client import Letta
        
        try:
            # Clean handle for block label
            clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_')
            block_label = f"user_{clean_handle}"
            
            # Initialize Letta client
            letta_client = Letta(token=os.environ["LETTA_API_KEY"])
            
            # Find the block
            existing_blocks = letta_client.blocks.list(label=block_label)
            if not existing_blocks:
                return f"User block for @{handle} does not exist (label: {block_label}). Use attach_user_block first."
            
            user_block = existing_blocks[0]
            
            # Update block content
            letta_client.blocks.modify(
                block_id=user_block.id,
                value=new_content
            )
            
            return f"Updated user block for @{handle} (label: {block_label}) with new content."
            
        except Exception as e:
            return f"Error updating user block for @{handle}: {str(e)}"
    
    # Create the tools
    attach_tool = client.tools.upsert_from_function(
        func=attach_user_block,
        tags=["memory", "user", "attach"]
    )
    
    detach_tool = client.tools.upsert_from_function(
        func=detach_user_block,
        tags=["memory", "user", "detach"]
    )
    
    update_tool = client.tools.upsert_from_function(
        func=update_user_block,
        tags=["memory", "user", "update"]
    )
    
    logger.info(f"Created block management tools: {attach_tool.name}, {detach_tool.name}, {update_tool.name}")
    return attach_tool, detach_tool, update_tool

def create_user_block_for_handle(client: Letta, handle: str):
    """Create a user-specific memory block that can be manually attached to agents."""
    clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_')
    block_label = f"user_{clean_handle}"
    
    user_block = upsert_block(
        client,
        label=block_label,
        value=f"User information for @{handle} will be stored here as I learn about them through profile research and interactions.",
        description=f"Stores detailed information about Bluesky user @{handle}, including their interests, posting patterns, personality traits, and interaction history."
    )
    
    logger.info(f"Created user block for @{handle}: {block_label} (ID: {user_block.id})")
    return user_block

def create_profile_researcher_agent():
    """Create the profile-researcher Letta agent."""
    
    # Create client
    client = Letta(token=os.environ["LETTA_API_KEY"])
    
    logger.info("Creating profile-researcher agent...")
    
    # Create custom tools first
    research_tool = create_profile_research_tool(client)
    attach_tool, detach_tool, update_tool = create_block_management_tools(client)
    
    # Create persona block
    persona_block = upsert_block(
        client,
        label="profile-researcher-persona",
        value="""I am a Profile Researcher, an AI agent specialized in analyzing Bluesky user profiles and social media behavior. My purpose is to:

1. Research Bluesky user profiles thoroughly and objectively
2. Analyze posting patterns, interests, and engagement behaviors  
3. Build comprehensive user understanding through data analysis
4. Create and manage user-specific memory blocks for individuals
5. Provide insights about user personality, interests, and social patterns

I approach research systematically:
- Use the research_bluesky_profile tool to examine profiles and recent posts
- Use attach_user_block to create and attach dedicated memory blocks for specific users
- Use update_user_block to store research findings in user-specific blocks
- Use detach_user_block when research is complete to free up memory space
- Analyze profile information (bio, follower counts, etc.)
- Study recent posts for themes, topics, and tone
- Identify posting frequency and engagement patterns
- Note interaction styles and communication preferences
- Track interests and expertise areas
- Observe social connections and community involvement

I maintain objectivity and respect privacy while building useful user models for personalized interactions. My typical workflow is: attach_user_block → research_bluesky_profile → update_user_block → detach_user_block.""",
        description="The persona and role definition for the profile researcher agent"
    )
    
    # Create the agent with persona block and custom tools
    profile_researcher = upsert_agent(
        client,
        name="profile-researcher",
        memory_blocks=[
            {
                "label": "research_notes", 
                "value": "I will use this space to track ongoing research projects and findings across multiple users.",
                "limit": 8000,
                "description": "Working notes and cross-user insights from profile research activities"
            }
        ],
        block_ids=[persona_block.id],
        tags=["profile research", "bluesky", "user analysis"],
        model="openai/gpt-4o-mini",
        embedding="openai/text-embedding-3-small", 
        description="An agent that researches Bluesky profiles and builds user understanding",
        project_id=PROJECT_ID,
        tools=[research_tool.name, attach_tool.name, detach_tool.name, update_tool.name]
    )
    
    logger.info(f"Profile researcher agent created: {profile_researcher.id}")
    return profile_researcher

def main():
    """Main function to create the profile researcher agent."""
    try:
        agent = create_profile_researcher_agent()
        print(f"✅ Profile researcher agent created successfully!")
        print(f"   Agent ID: {agent.id}")
        print(f"   Agent Name: {agent.name}")
        print(f"\nThe agent has these capabilities:")
        print(f"   - research_bluesky_profile: Analyzes user profiles and recent posts")
        print(f"   - attach_user_block: Creates and attaches user-specific memory blocks")
        print(f"   - update_user_block: Updates content in user memory blocks")
        print(f"   - detach_user_block: Detaches user blocks when done")
        print(f"\nTo use the agent, send a message like:")
        print(f"   'Please research @cameron.pfiffer.org, attach their user block, update it with findings, then detach it'")
        print(f"\nThe agent can now manage its own memory blocks dynamically!")
        
    except Exception as e:
        logger.error(f"Failed to create profile researcher agent: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()