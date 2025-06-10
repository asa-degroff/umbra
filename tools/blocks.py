"""Block management tools for user-specific memory blocks."""
from pydantic import BaseModel, Field
from typing import List, Dict, Any


class AttachUserBlocksArgs(BaseModel):
    handles: List[str] = Field(..., description="List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])")


class DetachUserBlocksArgs(BaseModel):
    handles: List[str] = Field(..., description="List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])")



def attach_user_blocks(handles: list, agent_state: "AgentState") -> str:
    """
    Attach user-specific memory blocks to the agent. Creates blocks if they don't exist.
    
    Args:
        handles: List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])
        agent_state: The agent state object containing agent information
        
    Returns:
        String with attachment results for each handle
    """
    import os
    import logging
    from letta_client import Letta
    
    logger = logging.getLogger(__name__)
    
    try:
        client = Letta(token=os.environ["LETTA_API_KEY"])
        results = []

        # Get current blocks using the API
        current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
        current_block_labels = set()
        
        for block in current_blocks:
            current_block_labels.add(block.label)

        for handle in handles:
            # Sanitize handle for block label - completely self-contained
            clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')
            block_label = f"user_{clean_handle}"

            # Skip if already attached
            if block_label in current_block_labels:
                results.append(f"✓ {handle}: Already attached")
                continue

            # Check if block exists or create new one
            try:
                blocks = client.blocks.list(label=block_label)
                if blocks and len(blocks) > 0:
                    block = blocks[0]
                    logger.info(f"Found existing block: {block_label}")
                else:
                    block = client.blocks.create(
                        label=block_label,
                        value=f"# User: {handle}\n\nNo information about this user yet.",
                        limit=5000
                    )
                    logger.info(f"Created new block: {block_label}")

                # Attach block atomically
                client.agents.blocks.attach(
                    agent_id=str(agent_state.id),
                    block_id=str(block.id)
                )
                results.append(f"✓ {handle}: Block attached")
                logger.info(f"Successfully attached block {block_label} to agent")

            except Exception as e:
                results.append(f"✗ {handle}: Error - {str(e)}")
                logger.error(f"Error processing block for {handle}: {e}")

        return f"Attachment results:\n" + "\n".join(results)
        
    except Exception as e:
        logger.error(f"Error attaching user blocks: {e}")
        raise Exception(f"Error attaching user blocks: {str(e)}")


def detach_user_blocks(handles: list, agent_state: "AgentState") -> str:
    """
    Detach user-specific memory blocks from the agent. Blocks are preserved for later use.
    
    Args:
        handles: List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])
        agent_state: The agent state object containing agent information
        
    Returns:
        String with detachment results for each handle
    """
    import os
    import logging
    from letta_client import Letta
    
    logger = logging.getLogger(__name__)
    
    try:
        client = Letta(token=os.environ["LETTA_API_KEY"])
        results = []

        # Build mapping of block labels to IDs using the API
        current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
        block_label_to_id = {}

        for block in current_blocks:
            block_label_to_id[block.label] = str(block.id)

        # Process each handle and detach atomically
        for handle in handles:
            # Sanitize handle for block label - completely self-contained
            clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')
            block_label = f"user_{clean_handle}"

            if block_label in block_label_to_id:
                try:
                    # Detach block atomically
                    client.agents.blocks.detach(
                        agent_id=str(agent_state.id),
                        block_id=block_label_to_id[block_label]
                    )
                    results.append(f"✓ {handle}: Detached")
                    logger.info(f"Successfully detached block {block_label} from agent")
                except Exception as e:
                    results.append(f"✗ {handle}: Error during detachment - {str(e)}")
                    logger.error(f"Error detaching block {block_label}: {e}")
            else:
                results.append(f"✗ {handle}: Not attached")

        return f"Detachment results:\n" + "\n".join(results)
        
    except Exception as e:
        logger.error(f"Error detaching user blocks: {e}")
        raise Exception(f"Error detaching user blocks: {str(e)}")


