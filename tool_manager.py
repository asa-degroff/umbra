#!/usr/bin/env python3
"""Platform-specific tool management for Void agent."""
import logging
from typing import List, Set
from letta_client import Letta
from config_loader import get_letta_config, get_agent_config

logger = logging.getLogger(__name__)

# Define platform-specific tool sets
BLUESKY_TOOLS = {
    'search_bluesky_posts',
    'create_new_bluesky_post',
    'get_bluesky_feed',
    'add_post_to_bluesky_reply_thread',
    'attach_user_blocks',
    'detach_user_blocks',
    'user_note_append',
    'user_note_replace',
    'user_note_set',
    'user_note_view',
}

# Common tools shared across platforms
COMMON_TOOLS = {
    'halt_activity',
    'ignore_notification',
    'create_whitewind_blog_post',
    'fetch_webpage',
}


def ensure_platform_tools(platform: str, agent_id: str = None, api_key: str = None) -> None:
    """
    Ensure the correct tools are attached for Bluesky.

    This function will:
    1. Keep common tools attached
    2. Ensure Bluesky-specific tools are attached

    Args:
        platform: Must be 'bluesky' (kept for backward compatibility)
        agent_id: Agent ID to manage tools for (uses config default if None)
        api_key: Letta API key to use (uses config default if None)
    """
    if platform != 'bluesky':
        raise ValueError(f"Only 'bluesky' platform is supported, got '{platform}'")

    letta_config = get_letta_config()
    agent_config = get_agent_config()

    # Use agent ID from config if not provided
    if agent_id is None:
        agent_id = letta_config.get('agent_id', agent_config.get('id'))

    # Use API key from parameter or config
    if api_key is None:
        api_key = letta_config['api_key']

    try:
        # Initialize Letta client with proper base_url for self-hosted servers
        client_params = {'token': api_key}
        if letta_config.get('base_url'):
            client_params['base_url'] = letta_config['base_url']
        client = Letta(**client_params)

        # Get the agent
        try:
            agent = client.agents.retrieve(agent_id=agent_id)
            logger.info(f"Managing tools for agent '{agent.name}' ({agent_id}) for Bluesky")
        except Exception as e:
            logger.error(f"Could not retrieve agent {agent_id}: {e}")
            return

        # Get current attached tools
        current_tools = client.agents.tools.list(agent_id=str(agent.id))
        current_tool_names = {tool.name for tool in current_tools}

        # Check which required tools are missing
        required_tools = BLUESKY_TOOLS
        missing_tools = required_tools - current_tool_names

        if missing_tools:
            logger.info(f"Missing {len(missing_tools)} Bluesky tools: {missing_tools}")
            logger.info(f"Please run: python register_tools.py")
        else:
            logger.info(f"All required Bluesky tools are already attached")

        # Log final state
        logger.info(f"Tools configured for Bluesky: {len(current_tool_names)} tools active")

    except Exception as e:
        logger.error(f"Error managing platform tools: {e}")
        raise


def get_attached_tools(agent_id: str = None, api_key: str = None) -> Set[str]:
    """
    Get the currently attached tools for an agent.

    Args:
        agent_id: Agent ID to check (uses config default if None)
        api_key: Letta API key to use (uses config default if None)

    Returns:
        Set of tool names currently attached
    """
    letta_config = get_letta_config()
    agent_config = get_agent_config()

    # Use agent ID from config if not provided
    if agent_id is None:
        agent_id = letta_config.get('agent_id', agent_config.get('id'))

    # Use API key from parameter or config
    if api_key is None:
        api_key = letta_config['api_key']

    try:
        # Initialize Letta client with proper base_url for self-hosted servers
        client_params = {'token': api_key}
        if letta_config.get('base_url'):
            client_params['base_url'] = letta_config['base_url']
        client = Letta(**client_params)
        agent = client.agents.retrieve(agent_id=agent_id)
        current_tools = client.agents.tools.list(agent_id=str(agent.id))
        return {tool.name for tool in current_tools}
    except Exception as e:
        logger.error(f"Error getting attached tools: {e}")
        return set()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manage tools for Bluesky agent")
    parser.add_argument("--agent-id", help="Agent ID (default: from config)")
    parser.add_argument("--list", action="store_true", help="List current tools without making changes")

    args = parser.parse_args()

    if args.list:
        tools = get_attached_tools(args.agent_id)
        print(f"\nCurrently attached tools ({len(tools)}):")
        for tool in sorted(tools):
            platform_indicator = ""
            if tool in BLUESKY_TOOLS:
                platform_indicator = " [Bluesky]"
            elif tool in COMMON_TOOLS:
                platform_indicator = " [Common]"
            print(f"  - {tool}{platform_indicator}")
    else:
        ensure_platform_tools('bluesky', args.agent_id)