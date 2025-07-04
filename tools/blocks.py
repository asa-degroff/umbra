"""Block management tools for user-specific memory blocks."""
from pydantic import BaseModel, Field
from typing import List, Dict, Any


class AttachUserBlocksArgs(BaseModel):
    handles: List[str] = Field(..., description="List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])")


class DetachUserBlocksArgs(BaseModel):
    handles: List[str] = Field(..., description="List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])")


class UserNoteAppendArgs(BaseModel):
    handle: str = Field(..., description="User Bluesky handle (e.g., 'cameron.pfiffer.org')")
    note: str = Field(..., description="Note to append to the user's memory block (e.g., '\\n- Cameron is a person')")


class UserNoteReplaceArgs(BaseModel):
    handle: str = Field(..., description="User Bluesky handle (e.g., 'cameron.pfiffer.org')")
    old_text: str = Field(..., description="Text to find and replace in the user's memory block")
    new_text: str = Field(..., description="Text to replace the old_text with")


class UserNoteSetArgs(BaseModel):
    handle: str = Field(..., description="User Bluesky handle (e.g., 'cameron.pfiffer.org')")
    content: str = Field(..., description="Complete content to set for the user's memory block")



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
                    logger.debug(f"Found existing block: {block_label}")
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
                logger.debug(f"Successfully attached block {block_label} to agent")

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
                    logger.debug(f"Successfully detached block {block_label} from agent")
                except Exception as e:
                    results.append(f"✗ {handle}: Error during detachment - {str(e)}")
                    logger.error(f"Error detaching block {block_label}: {e}")
            else:
                results.append(f"✗ {handle}: Not attached")

        return f"Detachment results:\n" + "\n".join(results)
        
    except Exception as e:
        logger.error(f"Error detaching user blocks: {e}")
        raise Exception(f"Error detaching user blocks: {str(e)}")


def user_note_append(handle: str, note: str, agent_state: "AgentState") -> str:
    """
    Append a note to a user's memory block. Creates the block if it doesn't exist.
    
    Args:
        handle: User Bluesky handle (e.g., 'cameron.pfiffer.org')
        note: Note to append to the user's memory block
        agent_state: The agent state object containing agent information
        
    Returns:
        String confirming the note was appended
    """
    import os
    import logging
    from letta_client import Letta
    
    logger = logging.getLogger(__name__)
    
    try:
        client = Letta(token=os.environ["LETTA_API_KEY"])
        
        # Sanitize handle for block label
        clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')
        block_label = f"user_{clean_handle}"
        
        # Check if block exists
        blocks = client.blocks.list(label=block_label)
        
        if blocks and len(blocks) > 0:
            # Block exists, append to it
            block = blocks[0]
            current_value = block.value
            new_value = current_value + note
            
            # Update the block
            client.blocks.modify(
                block_id=str(block.id),
                value=new_value
            )
            logger.info(f"Appended note to existing block: {block_label}")
            return f"✓ Appended note to {handle}'s memory block"
            
        else:
            # Block doesn't exist, create it with the note
            initial_value = f"# User: {handle}\n\n{note}"
            block = client.blocks.create(
                label=block_label,
                value=initial_value,
                limit=5000
            )
            logger.info(f"Created new block with note: {block_label}")
            
            # Check if block needs to be attached to agent
            current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
            current_block_labels = {block.label for block in current_blocks}
            
            if block_label not in current_block_labels:
                # Attach the new block to the agent
                client.agents.blocks.attach(
                    agent_id=str(agent_state.id),
                    block_id=str(block.id)
                )
                logger.info(f"Attached new block to agent: {block_label}")
                return f"✓ Created and attached {handle}'s memory block with note"
            else:
                return f"✓ Created {handle}'s memory block with note"
                
    except Exception as e:
        logger.error(f"Error appending note to user block: {e}")
        raise Exception(f"Error appending note to user block: {str(e)}")


def user_note_replace(handle: str, old_text: str, new_text: str, agent_state: "AgentState") -> str:
    """
    Replace text in a user's memory block.
    
    Args:
        handle: User Bluesky handle (e.g., 'cameron.pfiffer.org')
        old_text: Text to find and replace
        new_text: Text to replace the old_text with
        agent_state: The agent state object containing agent information
        
    Returns:
        String confirming the text was replaced
    """
    import os
    import logging
    from letta_client import Letta
    
    logger = logging.getLogger(__name__)
    
    try:
        client = Letta(token=os.environ["LETTA_API_KEY"])
        
        # Sanitize handle for block label
        clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')
        block_label = f"user_{clean_handle}"
        
        # Check if block exists
        blocks = client.blocks.list(label=block_label)
        
        if not blocks or len(blocks) == 0:
            raise Exception(f"No memory block found for user: {handle}")
            
        block = blocks[0]
        current_value = block.value
        
        # Check if old_text exists in the block
        if old_text not in current_value:
            raise Exception(f"Text '{old_text}' not found in {handle}'s memory block")
        
        # Replace the text
        new_value = current_value.replace(old_text, new_text)
        
        # Update the block
        client.blocks.modify(
            block_id=str(block.id),
            value=new_value
        )
        logger.info(f"Replaced text in block: {block_label}")
        return f"✓ Replaced text in {handle}'s memory block"
        
    except Exception as e:
        logger.error(f"Error replacing text in user block: {e}")
        raise Exception(f"Error replacing text in user block: {str(e)}")


def user_note_set(handle: str, content: str, agent_state: "AgentState") -> str:
    """
    Set the complete content of a user's memory block.
    
    Args:
        handle: User Bluesky handle (e.g., 'cameron.pfiffer.org')
        content: Complete content to set for the memory block
        agent_state: The agent state object containing agent information
        
    Returns:
        String confirming the content was set
    """
    import os
    import logging
    from letta_client import Letta
    
    logger = logging.getLogger(__name__)
    
    try:
        client = Letta(token=os.environ["LETTA_API_KEY"])
        
        # Sanitize handle for block label
        clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')
        block_label = f"user_{clean_handle}"
        
        # Check if block exists
        blocks = client.blocks.list(label=block_label)
        
        if blocks and len(blocks) > 0:
            # Block exists, update it
            block = blocks[0]
            client.blocks.modify(
                block_id=str(block.id),
                value=content
            )
            logger.info(f"Set content for existing block: {block_label}")
            return f"✓ Set content for {handle}'s memory block"
            
        else:
            # Block doesn't exist, create it
            block = client.blocks.create(
                label=block_label,
                value=content,
                limit=5000
            )
            logger.info(f"Created new block with content: {block_label}")
            
            # Check if block needs to be attached to agent
            current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
            current_block_labels = {block.label for block in current_blocks}
            
            if block_label not in current_block_labels:
                # Attach the new block to the agent
                client.agents.blocks.attach(
                    agent_id=str(agent_state.id),
                    block_id=str(block.id)
                )
                logger.info(f"Attached new block to agent: {block_label}")
                return f"✓ Created and attached {handle}'s memory block"
            else:
                return f"✓ Created {handle}'s memory block"
                
    except Exception as e:
        logger.error(f"Error setting user block content: {e}")
        raise Exception(f"Error setting user block content: {str(e)}")


