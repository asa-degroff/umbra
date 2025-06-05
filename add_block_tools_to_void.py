#!/usr/bin/env python3
"""
Add block management tools to the main void agent so it can also manage user blocks.
"""

import os
import logging
from letta_client import Letta
from create_profile_researcher import create_block_management_tools

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("add_block_tools")

def add_block_tools_to_void():
    """Add block management tools to the void agent."""
    
    # Create client
    client = Letta(token=os.environ["LETTA_API_KEY"])
    
    logger.info("Adding block management tools to void agent...")
    
    # Create the block management tools
    attach_tool, detach_tool, update_tool = create_block_management_tools(client)
    
    # Find the void agent
    agents = client.agents.list(name="void")
    if not agents:
        print("❌ Void agent not found")
        return
    
    void_agent = agents[0]
    
    # Get current tools
    current_tools = client.agents.tools.list(agent_id=void_agent.id)
    tool_names = [tool.name for tool in current_tools]
    
    # Add new tools if not already present
    new_tools = []
    for tool, name in [(attach_tool, "attach_user_block"), (detach_tool, "detach_user_block"), (update_tool, "update_user_block")]:
        if name not in tool_names:
            client.agents.tools.attach(agent_id=void_agent.id, tool_id=tool.id)
            new_tools.append(name)
            logger.info(f"Added tool {name} to void agent")
        else:
            logger.info(f"Tool {name} already attached to void agent")
    
    if new_tools:
        print(f"✅ Added {len(new_tools)} block management tools to void agent:")
        for tool_name in new_tools:
            print(f"   - {tool_name}")
    else:
        print("✅ All block management tools already present on void agent")
    
    print(f"\nVoid agent can now:")
    print(f"   - attach_user_block: Create and attach user memory blocks")
    print(f"   - update_user_block: Update user memory with new information")
    print(f"   - detach_user_block: Clean up memory when done with user")

def main():
    """Main function."""
    try:
        add_block_tools_to_void()
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()