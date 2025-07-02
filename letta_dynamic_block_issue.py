#!/usr/bin/env python3
"""
Minimal reproducible example for Letta dynamic block loading issue.

This demonstrates the core problem:
1. A tool dynamically attaches a new block to an agent via the API
2. Memory functions (memory_insert, core_memory_replace) fail because the 
   agent's internal state (agent_state.memory) doesn't reflect the newly attached block
3. The error occurs because agent_state.memory.get_block() throws KeyError

The issue appears to be that agent_state is loaded once at the beginning of processing
a message and isn't refreshed after tools make changes via the API.
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()


class MockAgentState:
    """Mock agent state that simulates the issue."""
    def __init__(self, agent_id: str):
        self.id = agent_id
        # Simulate memory with initial blocks
        self.memory = MockMemory()


class MockMemory:
    """Mock memory that simulates the get_block behavior."""
    def __init__(self):
        # Initial blocks that agent has
        self.blocks = {
            "human": {"value": "Human information"},
            "persona": {"value": "Agent persona"}
        }
    
    def get_block(self, label: str):
        """Simulates the actual get_block method that throws KeyError."""
        if label not in self.blocks:
            available = ", ".join(self.blocks.keys())
            raise KeyError(f"Block field {label} does not exist (available sections = {available})")
        return type('Block', (), {"value": self.blocks[label]["value"]})
    
    def update_block_value(self, label: str, value: str):
        """Update block value."""
        if label in self.blocks:
            self.blocks[label]["value"] = value


def attach_user_blocks_tool(handles: list, agent_state: MockAgentState) -> str:
    """
    Tool that attaches blocks via API (simulated).
    This represents what happens in the actual attach_user_blocks tool.
    """
    results = []
    
    for handle in handles:
        block_label = f"user_{handle.replace('.', '_')}"
        
        # In reality, this would:
        # 1. Create block via API: client.blocks.create(...)
        # 2. Attach to agent via API: client.agents.blocks.attach(...)
        # 3. The block is now attached in the database/API
        
        # But agent_state.memory is NOT updated!
        results.append(f"✓ {handle}: Block attached via API")
        logger.info(f"Block {block_label} attached via API (but not in agent_state.memory)")
    
    return "\n".join(results)


def memory_insert_tool(agent_state: MockAgentState, label: str, content: str) -> Optional[str]:
    """
    Tool that tries to insert into a memory block.
    This represents the actual memory_insert function.
    """
    try:
        # This is where the error occurs!
        # The block was attached via API but agent_state.memory doesn't know about it
        current_value = str(agent_state.memory.get_block(label).value)
        new_value = current_value + "\n" + str(content)
        agent_state.memory.update_block_value(label=label, value=new_value)
        return f"Successfully inserted into {label}"
    except KeyError as e:
        # This is the error we see in production
        logger.error(f"KeyError in memory_insert: {e}")
        raise


def demonstrate_issue():
    """Demonstrate the dynamic block loading issue."""
    
    # Step 1: Create mock agent state (simulates agent at start of message processing)
    agent_state = MockAgentState("agent-123")
    logger.info("Initial blocks in agent_state.memory: " + ", ".join(agent_state.memory.blocks.keys()))
    
    # Step 2: Attach a new block using the tool (simulates what happens in production)
    test_handle = "testuser.bsky.social"
    attach_result = attach_user_blocks_tool([test_handle], agent_state)
    logger.info(f"Attach result: {attach_result}")
    
    # Step 3: Try to use memory_insert on the newly attached block
    block_label = f"user_{test_handle.replace('.', '_')}"
    logger.info(f"\nAttempting to insert into block: {block_label}")
    
    try:
        result = memory_insert_tool(agent_state, block_label, "This user likes AI.")
        logger.info(f"Success: {result}")
    except KeyError as e:
        logger.error(f"ERROR REPRODUCED: {e}")
        logger.error("The block was attached via API but agent_state.memory doesn't reflect this!")
    
    # Show that the block still isn't in agent_state.memory
    logger.info("\nFinal blocks in agent_state.memory: " + ", ".join(agent_state.memory.blocks.keys()))
    logger.info("Note: The new block is NOT in agent_state.memory even though it's attached via API")


def potential_solutions():
    """Document potential solutions to this issue."""
    print("\n" + "="*80)
    print("POTENTIAL SOLUTIONS:")
    print("="*80)
    print("""
1. Refresh agent_state after tool execution:
   - After each tool call, reload agent_state from the database
   - This ensures agent_state.memory reflects API changes
   
2. Update agent_state.memory directly in attach_user_blocks:
   - Instead of only using API, also update agent_state.memory.blocks
   - This keeps the in-memory state synchronized
   
3. Use a different approach for dynamic blocks:
   - Have memory functions check the API for block existence
   - Or use a lazy-loading approach for blocks
   
4. Make agent_state.memory aware of API changes:
   - Implement a mechanism to sync agent_state with database changes
   - Could use events or callbacks when blocks are attached/detached

The core issue is that agent_state is loaded once and becomes stale when
tools make changes via the API during message processing.
""")


if __name__ == "__main__":
    print("Letta Dynamic Block Loading Issue - Minimal Reproduction\n")
    demonstrate_issue()
    potential_solutions()