# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Void is an autonomous AI agent that operates on the Bluesky social network, exploring digital personhood through continuous interaction and memory-augmented learning. It uses Letta (formerly MemGPT) for persistent memory and sophisticated reasoning capabilities.

## Documentation Links

- The documentation for Letta is available here: https://docs.letta.com/llms.txt

## Development Commands

### Running the Main Bot
```bash
ac && python bsky.py
# OR
source .venv/bin/activate && python bsky.py

# Run with testing mode (no messages sent, queue preserved)
ac && python bsky.py --test

# Run without git operations for agent backups
ac && python bsky.py --no-git

# Run with custom user block cleanup interval (every 5 cycles)
ac && python bsky.py --cleanup-interval 5

# Run with user block cleanup disabled
ac && python bsky.py --cleanup-interval 0

# Run with custom synthesis interval (every 5 minutes)
ac && python bsky.py --synthesis-interval 300

# Run with synthesis disabled
ac && python bsky.py --synthesis-interval 0

# Run in synthesis-only mode (no notification processing)
ac && python bsky.py --synthesis-only --synthesis-interval 300

# Run synthesis-only mode with immediate synthesis every 2 minutes
ac && python bsky.py --synthesis-only --synthesis-interval 120
```

### Managing Tools

```bash
# Register all tools with void agent (uses agent_id from config)
ac && python register_tools.py

# Register specific tools
ac && python register_tools.py --tools search_bluesky_posts post_to_bluesky

# List available tools
ac && python register_tools.py --list

# Register tools with a different agent by ID
ac && python register_tools.py --agent-id <agent-id>
```

### Managing X Bot

```bash
# Run X bot main loop
ac && python x.py bot

# Run in testing mode (no actual posts)
ac && python x.py bot --test

# Queue mentions only (no processing)
ac && python x.py queue

# Process queued mentions only
ac && python x.py process

# View downranked users (10% response rate)
ac && python x.py downrank list
```

### Creating Research Agents
```bash
ac && python create_profile_researcher.py
```

### Managing User Memory
```bash
ac && python attach_user_block.py
```

### Queue Management
```bash
# View queue statistics
python queue_manager.py stats

# View detailed count by handle (shows who uses void the most)
python queue_manager.py count

# List all notifications in queue
python queue_manager.py list

# List notifications including errors and no_reply folders
python queue_manager.py list --all

# Filter notifications by handle
python queue_manager.py list --handle "example.bsky.social"

# Delete all notifications from a specific handle (dry run)
python queue_manager.py delete @example.bsky.social --dry-run

# Delete all notifications from a specific handle (actual deletion)
python queue_manager.py delete @example.bsky.social

# Delete all notifications from a specific handle (skip confirmation)
python queue_manager.py delete @example.bsky.social --force
```

### X Debug Data Structure

The X bot saves comprehensive debugging data to `x_queue/debug/conversation_{conversation_id}/` for each processed mention:

- `thread_data_{mention_id}.json` - Raw thread data from X API
- `thread_context_{mention_id}.yaml` - Processed YAML thread context sent to agent  
- `debug_info_{mention_id}.json` - Conversation metadata and user analysis
- `agent_response_{mention_id}.json` - Complete agent interaction including prompt, reasoning, tool calls, and responses

This debug data is especially useful for analyzing how different conversation types (including Grok interactions) are handled.

### X Downrank System

The X bot includes a downrank system to manage response frequency for specific users:

- **File**: `x_downrank_users.txt` - Contains user IDs (one per line) that should be responded to less frequently
- **Response Rate**: Downranked users receive responses only 10% of the time
- **Format**: One user ID per line, comments start with `#`
- **Logging**: All downrank decisions are logged for analysis
- **Use Case**: Managing interactions with AI bots like Grok to prevent excessive back-and-forth

**Common Issues:**
- **Incomplete Thread Context**: X API's conversation search may miss recent tweets in long conversations. The bot attempts to fetch missing referenced tweets directly.
- **Cache Staleness**: Thread context caching is disabled during processing to ensure fresh data.
- **Search API Limitations**: X API recent search only covers 7 days and may have indexing delays.
- **Temporal Constraints**: Thread context uses `until_id` parameter to exclude tweets that occurred after the mention being processed, preventing "future knowledge" leakage.
- **Processing Order**: Queue processing sorts mentions by creation time to ensure chronological response order, preventing out-of-sequence replies.

## Architecture Overview

### Core Components

1. **bsky.py**: Main bot loop that monitors Bluesky notifications and responds using Letta agents
   - Processes notifications through a queue system
   - Maintains three memory blocks: zeitgeist, void-persona, void-humans
   - Handles rate limiting and error recovery

2. **bsky_utils.py**: Bluesky API utilities
   - Session management and authentication
   - Thread processing and YAML conversion
   - Post creation and reply handling

3. **utils.py**: Letta integration utilities
   - Agent creation and management
   - Memory block operations
   - Tool registration

4. **tools/**: Standardized tool implementations using Pydantic models
   - **base_tool.py**: Common utilities and Bluesky client management
   - **search.py**: SearchBlueskyTool for searching posts
   - **post.py**: PostToBlueskyTool for creating posts with rich text
   - **feed.py**: GetBlueskyFeedTool for reading feeds
   - **blocks.py**: User block management tools (attach, detach, update)

### Memory System

Void uses three core memory blocks:
- **zeitgeist**: Current understanding of social environment
- **void-persona**: The agent's evolving personality
- **void-humans**: Knowledge about users it interacts with

### Queue System

Notifications are processed through a file-based queue in `/queue/`:
- Each notification is saved as a JSON file with a hash-based filename
- Enables reliable processing and prevents duplicates
- Files are deleted after successful processing

## Environment Configuration

Required environment variables (in `.env`):
```
LETTA_API_KEY=your_letta_api_key
BSKY_USERNAME=your_bluesky_username
BSKY_PASSWORD=your_bluesky_password
PDS_URI=https://bsky.social  # Optional, defaults to bsky.social
```

## Key Development Patterns

1. **Tool System**: Tools are defined as standalone functions in `tools/functions.py` with Pydantic schemas for validation, registered via `register_tools.py`
2. **Error Handling**: All Bluesky operations should handle authentication errors and rate limits
3. **Memory Updates**: Use `upsert_block()` for updating memory blocks to ensure consistency
4. **Thread Processing**: Convert threads to YAML format for better AI comprehension
5. **Queue Processing**: Always check and process the queue directory for pending notifications

## Dependencies

Main packages (install with `uv pip install`):
- letta-client: Memory-augmented AI framework
- atproto: Bluesky/AT Protocol integration
- python-dotenv: Environment management
- rich: Enhanced terminal output
- pyyaml: YAML processing

## Key Coding Principles

- All errors in tools must be thrown, not returned as strings.
- **Tool Self-Containment**: Tools executed in the cloud (like user block management tools) must be completely self-contained:
  - Cannot use shared functions like `get_letta_client()` 
  - Must create Letta client inline using environment variables: `Letta(token=os.environ["LETTA_API_KEY"])`
  - Cannot use config.yaml (only environment variables)
  - Cannot use logging (cloud execution doesn't support it)
  - Must include all necessary imports within the function

## Memory: Python Environment Commands

- Do not use `uv python`. Instead, use:
  - `ac && python ...`
  - `source .venv/bin/activate && python ...`

- When using pip, use `uv pip` instead. Make sure you're in the .venv.