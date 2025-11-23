"""Block management tools for user-specific memory blocks."""
from pydantic import BaseModel, Field
from typing import List, Dict, Any

def get_letta_client():
    """Get a Letta client using configuration."""
    try:
        from config_loader import get_letta_config
        from letta_client import Letta
        config = get_letta_config()
        client_params = {
            'token': config['api_key'],
            'timeout': config['timeout']
        }
        if config.get('base_url'):
            client_params['base_url'] = config['base_url']
        return Letta(**client_params)
    except (ImportError, FileNotFoundError, KeyError):
        # Fallback to environment variable
        import os
        from letta_client import Letta
        return Letta(token=os.environ["LETTA_API_KEY"])


def _sanitize_handle_for_label(handle: str) -> str:
    """
    Sanitize a Bluesky handle for use as a block label.

    Args:
        handle: Bluesky handle (e.g., '@user.bsky.social' or 'user.bsky.social')

    Returns:
        Sanitized label (e.g., 'user_bsky_social')
    """
    return handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')


class AttachUserBlocksArgs(BaseModel):
    handles: List[str] = Field(..., description="List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])")


class DetachUserBlocksArgs(BaseModel):
    handles: List[str] = Field(..., description="List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])")


class UserNoteAppendArgs(BaseModel):
    handle: str = Field(..., description="User Bluesky handle (e.g., '3fz.org')")
    note: str = Field(..., description="Note to append to the user's memory block")


class UserNoteReplaceArgs(BaseModel):
    handle: str = Field(..., description="User Bluesky handle (e.g., '3fz.org')")
    old_text: str = Field(..., description="Text to find and replace in the user's memory block")
    new_text: str = Field(..., description="Text to replace the old_text with")


class UserNoteSetArgs(BaseModel):
    handle: str = Field(..., description="User Bluesky handle (e.g., '3fz.org')")
    content: str = Field(..., description="Complete content to set for the user's memory block")


class UserNoteViewArgs(BaseModel):
    handle: str = Field(..., description="User Bluesky handle (e.g., '3fz.org')")



def attach_user_blocks(handles: list, agent_state: "AgentState") -> str:
    """
    Attach user-specific memory blocks to the agent. Creates blocks if they don't exist.
    
    Args:
        handles: List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])
        agent_state: The agent state object containing agent information
        
    Returns:
        String with attachment results for each handle
    """

    handles = list(set(handles))
    
    try:
        # Try to get client the local way first, fall back to inline for cloud execution
        try:
            client = get_letta_client()
        except (ImportError, NameError):
            # Create Letta client inline for cloud execution
            import os
            from letta_client import Letta
            client = Letta(token=os.environ["LETTA_API_KEY"])
        results = []

        # Get current blocks using the API
        current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
        current_block_labels = set()
        current_block_ids = set()
        
        for block in current_blocks:
            current_block_labels.add(block.label)
            current_block_ids.add(str(block.id))

        for handle in handles:
            # Sanitize handle for block label
            clean_handle = _sanitize_handle_for_label(handle)
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
                    
                    # Double-check if this block is already attached by ID
                    if str(block.id) in current_block_ids:
                        results.append(f"✓ {handle}: Already attached (by ID)")
                        continue
                else:
                    block = client.blocks.create(
                        label=block_label,
                        value=f"# User: {handle}\n\nNo information about this user yet.",
                        limit=5000
                    )

                # Attach block atomically
                try:
                    client.agents.blocks.attach(
                        agent_id=str(agent_state.id),
                        block_id=str(block.id)
                    )
                    results.append(f"✓ {handle}: Block attached")
                except Exception as attach_error:
                    # Check if it's a duplicate constraint error
                    error_str = str(attach_error)
                    if "duplicate key value violates unique constraint" in error_str and "unique_label_per_agent" in error_str:
                        # Block is already attached, possibly with this exact label
                        results.append(f"✓ {handle}: Already attached (verified)")
                    else:
                        # Re-raise other errors
                        raise attach_error

            except Exception as e:
                results.append(f"✗ {handle}: Error - {str(e)}")

        return f"Attachment results:\n" + "\n".join(results)
        
    except Exception as e:
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
    
    try:
        # Try to get client the local way first, fall back to inline for cloud execution
        try:
            client = get_letta_client()
        except (ImportError, NameError):
            # Create Letta client inline for cloud execution
            import os
            from letta_client import Letta
            client = Letta(token=os.environ["LETTA_API_KEY"])
        results = []

        # Build mapping of block labels to IDs using the API
        current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
        block_label_to_id = {}

        for block in current_blocks:
            block_label_to_id[block.label] = str(block.id)

        # Process each handle and detach atomically
        for handle in handles:
            # Sanitize handle for block label
            clean_handle = _sanitize_handle_for_label(handle)
            block_label = f"user_{clean_handle}"

            if block_label in block_label_to_id:
                try:
                    # Detach block atomically
                    client.agents.blocks.detach(
                        agent_id=str(agent_state.id),
                        block_id=block_label_to_id[block_label]
                    )
                    results.append(f"✓ {handle}: Detached")
                except Exception as e:
                    results.append(f"✗ {handle}: Error during detachment - {str(e)}")
            else:
                results.append(f"✗ {handle}: Not attached")

        return f"Detachment results:\n" + "\n".join(results)
        
    except Exception as e:
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
    
    try:
        # Try to get X client first, fall back to inline for cloud execution
        try:
            client = get_x_letta_client()
        except (ImportError, NameError):
            # Create Letta client inline for cloud execution
            import os
            from letta_client import Letta
            client = Letta(token=os.environ["LETTA_API_KEY"])
        
        # Sanitize handle for block label
        clean_handle = _sanitize_handle_for_label(handle)
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
            return f"✓ Appended note to {handle}'s memory block"
            
        else:
            # Block doesn't exist, create it with the note
            initial_value = f"# User: {handle}\n\n{note}"
            block = client.blocks.create(
                label=block_label,
                value=initial_value,
                limit=5000
            )
            
            # Check if block needs to be attached to agent
            current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
            current_block_labels = {block.label for block in current_blocks}
            
            if block_label not in current_block_labels:
                # Attach the new block to the agent
                client.agents.blocks.attach(
                    agent_id=str(agent_state.id),
                    block_id=str(block.id)
                )
                return f"✓ Created and attached {handle}'s memory block with note"
            else:
                return f"✓ Created {handle}'s memory block with note"
                
    except Exception as e:
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
    
    try:
        # Try to get X client first, fall back to inline for cloud execution
        try:
            client = get_x_letta_client()
        except (ImportError, NameError):
            # Create Letta client inline for cloud execution
            import os
            from letta_client import Letta
            client = Letta(token=os.environ["LETTA_API_KEY"])
        
        # Sanitize handle for block label
        clean_handle = _sanitize_handle_for_label(handle)
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
        return f"✓ Replaced text in {handle}'s memory block"
        
    except Exception as e:
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
    
    try:
        # Try to get X client first, fall back to inline for cloud execution
        try:
            client = get_x_letta_client()
        except (ImportError, NameError):
            # Create Letta client inline for cloud execution
            import os
            from letta_client import Letta
            client = Letta(token=os.environ["LETTA_API_KEY"])
        
        # Sanitize handle for block label
        clean_handle = _sanitize_handle_for_label(handle)
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
            return f"✓ Set content for {handle}'s memory block"
            
        else:
            # Block doesn't exist, create it
            block = client.blocks.create(
                label=block_label,
                value=content,
                limit=5000
            )
            
            # Check if block needs to be attached to agent
            current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
            current_block_labels = {block.label for block in current_blocks}
            
            if block_label not in current_block_labels:
                # Attach the new block to the agent
                client.agents.blocks.attach(
                    agent_id=str(agent_state.id),
                    block_id=str(block.id)
                )
                return f"✓ Created and attached {handle}'s memory block"
            else:
                return f"✓ Created {handle}'s memory block"
                
    except Exception as e:
        raise Exception(f"Error setting user block content: {str(e)}")


def user_note_view(handle: str, agent_state: "AgentState") -> str:
    """
    View the content of a user's memory block.
    
    Args:
        handle: User Bluesky handle (e.g., 'cameron.pfiffer.org')
        agent_state: The agent state object containing agent information
        
    Returns:
        String containing the user's memory block content
    """
    
    try:
        # Try to get X client first, fall back to inline for cloud execution
        try:
            client = get_x_letta_client()
        except (ImportError, NameError):
            # Create Letta client inline for cloud execution
            import os
            from letta_client import Letta
            client = Letta(token=os.environ["LETTA_API_KEY"])
        
        # Sanitize handle for block label
        clean_handle = _sanitize_handle_for_label(handle)
        block_label = f"user_{clean_handle}"
        
        # Check if block exists
        blocks = client.blocks.list(label=block_label)
        
        if not blocks or len(blocks) == 0:
            return f"No memory block found for user: {handle}"
            
        block = blocks[0]
        
        return f"Memory block for {handle}:\n\n{block.value}"
        
    except Exception as e:
        raise Exception(f"Error viewing user block: {str(e)}")