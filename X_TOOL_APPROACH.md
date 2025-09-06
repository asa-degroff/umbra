# X Tool Approach

This document explains how X tools work differently from Bluesky tools, following the "keep it simple, stupid" principle.

## Core Philosophy

X tools follow the same pattern as Bluesky tools in `bsky.py`:

1. **Tools are signals, not actions** - They don't perform network operations
2. **Handler processes tool calls** - The main bot loop (like `bsky.py`) processes tool results
3. **Atomic operations** - Each tool call represents one discrete action
4. **Thread construction** - Multiple tool calls are aggregated into threads by the handler

## X Tool Set

The X tool set is intentionally minimal:

### Core Tools (Kept from Bluesky)
- `halt_activity` - Signal to terminate the bot
- `ignore_notification` - Explicitly ignore a notification without replying  
- `annotate_ack` - Add notes to acknowledgment records
- `create_whitewind_blog_post` - Create blog posts (platform-agnostic)
- `fetch_webpage` - Fetch and process web content (platform-agnostic)

### X-Specific User Block Tools
- `attach_x_user_blocks` - Attach X user memory blocks (format: `x_user_<user_id>`)
- `detach_x_user_blocks` - Detach X user memory blocks
- `x_user_note_append` - Append to X user memory blocks
- `x_user_note_replace` - Replace text in X user memory blocks  
- `x_user_note_set` - Set complete content of X user memory blocks
- `x_user_note_view` - View X user memory block content

### X Thread Tool
- `add_post_to_x_thread` - Signal to add a post to the reply thread (max 280 chars)

## Implementation Pattern

### Tool Implementation (`tools/x_thread.py`)
```python
def add_post_to_x_thread(text: str) -> str:
    # Validate input
    if len(text) > 280:
        raise Exception(f"Text exceeds 280 character limit...")
    
    # Return confirmation - actual posting handled by x_bot.py
    return f"X post queued for reply thread: {text[:50]}..."
```

### Handler Implementation (Future `x_bot.py`)
```python
# Extract successful tool calls from agent response
reply_candidates = []
for message in message_response.messages:
    if message.tool_call.name == 'add_post_to_x_thread':
        if tool_status == 'success':
            reply_candidates.append(text)

# Aggregate into thread and post to X
if reply_candidates:
    # Build thread structure
    # Post to X using x.py client
    # Handle threading/replies properly
```

## Key Differences from Bluesky

1. **Character Limit**: X uses 280 characters vs Bluesky's 300
2. **User Identification**: X uses numeric user IDs vs Bluesky handles
3. **Block Format**: `x_user_<user_id>` vs `user_<handle>` 
4. **No Language Parameter**: X doesn't use language codes like Bluesky

## Thread Context Integration

X threads include user IDs for block management:

```yaml
conversation:
  - text: "hey @void_comind"
    author:
      username: "cameron_pfiffer" 
      name: "Cameron Pfiffer"
    author_id: "1232326955652931584"  # Used for x_user_1232326955652931584 block
```

The `ensure_x_user_blocks_attached()` function in `x.py` automatically creates and attaches user blocks based on thread participants.

## Registration

Use `register_x_tools.py` to register X-specific tools:

```bash
# Register all X tools
python register_x_tools.py

# Register specific tools
python register_x_tools.py --tools add_post_to_x_thread x_user_note_append

# List available tools  
python register_x_tools.py --list
```

## Future Implementation

When creating the X bot handler (similar to `bsky.py`):

1. Parse X mentions/replies
2. Get thread context using `x.py` 
3. Attach user blocks with `ensure_x_user_blocks_attached()`
4. Send to Letta agent with X tools
5. Process `add_post_to_x_thread` tool calls
6. Post replies to X using `x.py` client
7. Handle threading and reply context properly