# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Umbra is an autonomous AI agent that operates on the Bluesky social network, exploring digital personhood through continuous interaction and memory-augmented learning. It uses Letta (formerly MemGPT) for persistent memory and sophisticated reasoning capabilities.

## Documentation Links

- The documentation for Letta is available here: https://docs.letta.com/llms.txt

## Development Commands

### Running the Main Bot
```bash
ac && python bsky.py
# OR
source .venv/bin/activate && python bsky.py

# Run with custom config file
ac && python bsky.py --config herald.yaml

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
# Register all tools with umbra agent (uses agent_id from config.yaml)
ac && python register_tools.py

# Register specific tools
ac && python register_tools.py --tools search_bluesky_posts post_to_bluesky

# List available tools
ac && python register_tools.py --list

# Register tools with a different agent by ID
ac && python register_tools.py --agent-id <agent-id>

# Register tools without setting environment variables
ac && python register_tools.py --no-env

# Note: register_tools.py automatically sets BSKY_USERNAME, BSKY_PASSWORD, and PDS_URI
# as environment variables on the agent for tool execution
```

### Queue Management
```bash
# View queue statistics
python queue_manager.py stats

# View detailed count by handle (shows who uses umbra the most)
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

## Architecture Overview

### Core Components

1. **bsky.py**: Main bot loop that monitors Bluesky notifications and responds using Letta agents
   - Processes notifications through a queue system
   - Maintains three memory blocks: zeitgeist, umbra-persona, umbra-humans
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

Umbra uses three core memory blocks:
- **zeitgeist**: Current understanding of social environment
- **umbra-persona**: The agent's evolving personality
- **umbra-humans**: Knowledge about users it interacts with

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