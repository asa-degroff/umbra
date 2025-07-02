# Letta Dynamic Block Loading Issue

## Problem Summary

Void agent experiences persistent failures when attempting to use memory functions (like `memory_insert` or `core_memory_replace`) on dynamically attached blocks. The error manifests as:

```
KeyError: 'Block field user_nonbinary_computer does not exist (available sections = long_term_objectives, system_information, user_dulanyw_bsky_social, posting_ideas, conversation_summary, user_example_com, user_elouan_xyz, user_barrycarlyon_co_uk, user_unxpctd_xyz, user_vasthypno_bsky_social, scratchpad, void-persona, zeitgeist, communication_guidelines, tool_use_guide, user_tachikoma_elsewhereunbound_com, tool_usage_rules)'
```

## Root Cause Analysis

The issue occurs due to a **state synchronization problem** between the Letta API and the agent's internal memory state:

1. **Block Attachment via API**: The `attach_user_blocks` tool successfully creates and attaches blocks using the Letta client API (`client.agents.blocks.attach`)

2. **Stale Agent State**: However, the agent's internal `agent_state.memory` object is loaded once at the beginning of message processing and is NOT refreshed after API changes

3. **Memory Function Failure**: When memory functions like `memory_insert` try to access the newly attached block via `agent_state.memory.get_block(label)`, it fails because the block only exists in the database/API layer, not in the agent's loaded memory state

## Technical Details

### The Problematic Flow

```python
# 1. Agent receives message and agent_state is loaded with initial blocks
agent_state.memory.blocks = ["human", "persona", "zeitgeist", ...] 

# 2. Agent calls attach_user_blocks tool
def attach_user_blocks(handles, agent_state):
    client = Letta(token=os.environ["LETTA_API_KEY"])
    # This succeeds - block is created and attached via API
    client.agents.blocks.attach(agent_id=agent_state.id, block_id=block.id)
    # BUT: agent_state.memory is NOT updated!

# 3. Agent tries to use memory_insert on the new block
def memory_insert(agent_state, label, content):
    # This fails because agent_state.memory doesn't have the new block
    current_value = agent_state.memory.get_block(label).value  # KeyError!
```

### Evidence from Codebase

From `letta/letta/schemas/memory.py:129`:
```python
def get_block(self, label: str) -> Block:
    """Correct way to index into the memory.memory field, returns a Block"""
    keys = []
    for block in self.blocks:
        if block.label == label:
            return block
        keys.append(block.label)
    raise KeyError(f"Block field {label} does not exist (available sections = {', '.join(keys)})")
```

The error message in the exception matches exactly what we see in production.

## Reproduction

The `letta_dynamic_block_issue.py` script demonstrates this issue with a mock setup that reproduces the exact error condition.

## Impact

This affects Void's ability to:
- Dynamically create user-specific memory blocks during conversations
- Update those blocks with new information about users
- Maintain personalized context for individual users

The issue is intermittent because it depends on timing and whether blocks are attached/accessed within the same message processing cycle.

## Potential Solutions

### 1. Refresh Agent State After Tool Execution
Reload `agent_state` from the database after each tool call that modifies blocks:
```python
# After tool execution in Letta's tool executor
agent_state = agent_manager.get_agent_by_id(agent_id, include_blocks=True)
```

### 2. Synchronize agent_state.memory in attach_user_blocks
Update both the API and the in-memory state:
```python
def attach_user_blocks(handles, agent_state):
    # Attach via API
    client.agents.blocks.attach(agent_id=agent_state.id, block_id=block.id)
    
    # Also update agent_state.memory directly
    agent_state.memory.set_block(block)
```

### 3. Lazy Loading in Memory Functions
Make memory functions check the API if a block isn't found locally:
```python
def get_block(self, label: str) -> Block:
    # Try local first
    for block in self.blocks:
        if block.label == label:
            return block
    
    # If not found, check API
    api_blocks = client.agents.blocks.list(agent_id=self.agent_id)
    for block in api_blocks:
        if block.label == label:
            self.blocks.append(block)  # Cache it
            return block
    
    # Finally raise error
    raise KeyError(...)
```

### 4. Event-Driven State Synchronization
Implement a callback/event system where API changes automatically update `agent_state.memory`.

## Recommended Fix

**Solution #1 (Refresh Agent State)** is likely the most robust as it ensures consistency without requiring changes to existing tools. The refresh should happen in Letta's tool execution pipeline after any tool that can modify agent state.

## Files Provided

- `letta_dynamic_block_issue.py` - Minimal reproduction script
- `minimal_block_issue_simple.py` - API-based reproduction attempt
- This documentation file

## Related Code Locations

- `void/tools/blocks.py` - Contains the attach_user_blocks tool
- `letta/letta/schemas/memory.py:129` - Where the KeyError is thrown
- `letta/letta/functions/function_sets/base.py` - Memory functions (memory_insert, core_memory_replace)