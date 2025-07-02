#!/usr/bin/env python3
"""
Simplified minimal reproducible example for Letta dynamic block loading issue.

This demonstrates the core issue:
1. A tool attaches a new block to an agent
2. Memory functions fail because agent_state doesn't reflect the new block
"""

import os
import logging
from dotenv import load_dotenv
from letta_client import Letta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()


def main():
    """Demonstrate the dynamic block loading issue."""
    client = Letta(token=os.environ["LETTA_API_KEY"])
    
    # Use an existing agent or create one using the utils
    agent_name = "test_block_issue"
    
    # First, let's see if we can create an agent using the API directly
    logger.info("Looking for or creating test agent...")
    
    agents = client.agents.list()
    agent = None
    for a in agents:
        if a.name == agent_name:
            agent = a
            logger.info(f"Found existing agent: {agent.name}")
            break
    
    if not agent:
        # Create using simple params that work
        agent = client.agents.create(
            name=agent_name
        )
        logger.info(f"Created agent: {agent.name} (ID: {agent.id})")
    
    try:
        # Get initial blocks
        initial_blocks = client.agents.blocks.list(agent_id=str(agent.id))
        initial_labels = {block.label for block in initial_blocks}
        logger.info(f"Initial blocks: {initial_labels}")
        
        # Step 1: Create and attach a new block
        test_handle = "testuser.bsky.social"
        block_label = f"user_{test_handle.replace('.', '_')}"
        
        # Check if block already attached
        if block_label in initial_labels:
            logger.info(f"Block {block_label} already attached, skipping creation")
        else:
            logger.info(f"Creating block: {block_label}")
            
            # Check if block exists
            existing_blocks = client.blocks.list(label=block_label)
            if existing_blocks:
                new_block = existing_blocks[0]
                logger.info(f"Using existing block with ID: {new_block.id}")
            else:
                # Create the block
                new_block = client.blocks.create(
                    label=block_label,
                    value=f"# User: {test_handle}\n\nInitial content.",
                    limit=5000
                )
                logger.info(f"Created block with ID: {new_block.id}")
            
            # Attach to agent
            logger.info("Attaching block to agent...")
            client.agents.blocks.attach(
                agent_id=str(agent.id),
                block_id=str(new_block.id)
            )
        
        # Verify attachment via API
        blocks_after = client.agents.blocks.list(agent_id=str(agent.id))
        labels_after = {block.label for block in blocks_after}
        logger.info(f"Blocks after attachment: {labels_after}")
        
        if block_label in labels_after:
            logger.info("✓ Block successfully attached via API")
        else:
            logger.error("✗ Block NOT found via API after attachment")
        
        # Step 2: Send a message asking the agent to use memory_insert on the new block
        logger.info(f"\nAsking agent to update the newly attached block...")
        
        from letta_client import MessageCreate
        
        response = client.agents.messages.create(
            agent_id=str(agent.id),
            messages=[MessageCreate(role="user", content=f"Use memory_insert to add this text to the '{block_label}' memory block: 'This user likes AI and technology.'")]
        )
        
        # Check for errors in the response
        error_found = False
        for message in response.messages:
            if hasattr(message, 'text') and message.text:
                logger.info(f"Agent: {message.text}")
            
            # Look for tool returns with errors
            if hasattr(message, 'type') and message.type == 'tool_return':
                if hasattr(message, 'status') and message.status == 'error':
                    error_found = True
                    logger.error("ERROR REPRODUCED!")
                    if hasattr(message, 'tool_return'):
                        logger.error(f"Tool error: {message.tool_return}")
                    if hasattr(message, 'stderr') and message.stderr:
                        for err in message.stderr:
                            logger.error(f"Stderr: {err}")
        
        if not error_found:
            logger.info("No error found - checking if operation succeeded...")
            
            # Get the block content to see if it was updated
            updated_blocks = client.blocks.list(label=block_label)
            if updated_blocks:
                logger.info(f"Block content:\n{updated_blocks[0].value}")
        
    finally:
        # Cleanup - always delete test agent
        if agent and agent.name == agent_name:
            logger.info(f"\nDeleting test agent {agent.name}")
            client.agents.delete(agent_id=str(agent.id))


if __name__ == "__main__":
    main()