"""Defensive memory operations that handle missing blocks gracefully."""
import os
from typing import Optional
from letta_client import Letta


def safe_memory_insert(agent_state: "AgentState", label: str, content: str, insert_line: int = -1) -> str:
    """
    Safe version of memory_insert that handles missing blocks by fetching them from API.
    
    This is a stopgap solution for the dynamic block loading issue where agent_state.memory
    doesn't reflect blocks that were attached via API during the same message processing cycle.
    """
    try:
        # Try the normal memory_insert first
        from letta.functions.function_sets.base import memory_insert
        return memory_insert(agent_state, label, content, insert_line)
    
    except KeyError as e:
        if "does not exist" in str(e):
            print(f"[SAFE_MEMORY] Block {label} not found in agent_state.memory, fetching from API...")
            # Try to fetch the block from the API and add it to agent_state.memory
            try:
                client = Letta(token=os.environ["LETTA_API_KEY"])
                
                # Get all blocks attached to this agent
                api_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
                
                # Find the block we're looking for
                target_block = None
                for block in api_blocks:
                    if block.label == label:
                        target_block = block
                        break
                
                if target_block:
                    # Add it to agent_state.memory
                    agent_state.memory.set_block(target_block)
                    print(f"[SAFE_MEMORY] Successfully fetched and added block {label} to agent_state.memory")
                    
                    # Now try the memory_insert again
                    from letta.functions.function_sets.base import memory_insert
                    return memory_insert(agent_state, label, content, insert_line)
                else:
                    # Block truly doesn't exist
                    raise Exception(f"Block {label} not found in API - it may not be attached to this agent")
                    
            except Exception as api_error:
                raise Exception(f"Failed to fetch block {label} from API: {str(api_error)}")
        else:
            raise e  # Re-raise if it's a different KeyError


def safe_core_memory_replace(agent_state: "AgentState", label: str, old_content: str, new_content: str) -> Optional[str]:
    """
    Safe version of core_memory_replace that handles missing blocks.
    """
    try:
        # Try the normal core_memory_replace first
        from letta.functions.function_sets.base import core_memory_replace
        return core_memory_replace(agent_state, label, old_content, new_content)
    
    except KeyError as e:
        if "does not exist" in str(e):
            print(f"[SAFE_MEMORY] Block {label} not found in agent_state.memory, fetching from API...")
            try:
                client = Letta(token=os.environ["LETTA_API_KEY"])
                api_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
                
                target_block = None
                for block in api_blocks:
                    if block.label == label:
                        target_block = block
                        break
                
                if target_block:
                    agent_state.memory.set_block(target_block)
                    print(f"[SAFE_MEMORY] Successfully fetched and added block {label} to agent_state.memory")
                    
                    from letta.functions.function_sets.base import core_memory_replace
                    return core_memory_replace(agent_state, label, old_content, new_content)
                else:
                    raise Exception(f"Block {label} not found in API - it may not be attached to this agent")
                    
            except Exception as api_error:
                raise Exception(f"Failed to fetch block {label} from API: {str(api_error)}")
        else:
            raise e