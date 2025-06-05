#!/usr/bin/env python3
"""
Helper script to create and attach user-specific memory blocks to the profile researcher agent.
Usage: python attach_user_block.py @cameron.pfiffer.org
"""

import sys
import os
import logging
from letta_client import Letta
from create_profile_researcher import create_user_block_for_handle

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("attach_user_block")

def attach_user_block_to_agent(agent_name: str, handle: str):
    """Create and attach a user block to an agent."""
    
    # Create client
    client = Letta(token=os.environ["LETTA_API_KEY"])
    
    # Find the agent
    agents = client.agents.list(name=agent_name)
    if not agents:
        print(f"❌ Agent '{agent_name}' not found")
        return False
    
    agent = agents[0]
    print(f"📝 Found agent: {agent.name} (ID: {agent.id})")
    
    # Create the user block
    print(f"🔍 Creating user block for {handle}...")
    user_block = create_user_block_for_handle(client, handle)
    
    # Check if already attached
    agent_blocks = client.agents.blocks.list(agent_id=agent.id)
    for block in agent_blocks:
        if block.id == user_block.id:
            print(f"✅ User block for {handle} is already attached to {agent.name}")
            return True
    
    # Attach the block to the agent
    print(f"🔗 Attaching user block to agent...")
    client.agents.blocks.attach(agent_id=agent.id, block_id=user_block.id)
    
    print(f"✅ Successfully attached user block for {handle} to {agent.name}")
    print(f"   Block ID: {user_block.id}")
    print(f"   Block Label: {user_block.label}")
    return True

def main():
    """Main function."""
    if len(sys.argv) != 2:
        print("Usage: python attach_user_block.py <handle>")
        print("Example: python attach_user_block.py @cameron.pfiffer.org")
        sys.exit(1)
    
    handle = sys.argv[1]
    agent_name = "profile-researcher"
    
    try:
        success = attach_user_block_to_agent(agent_name, handle)
        if not success:
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()