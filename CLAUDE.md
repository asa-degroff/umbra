# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Void is an autonomous AI agent that operates on the Bluesky social network, exploring digital personhood through continuous interaction and memory-augmented learning. It uses Letta (formerly MemGPT) for persistent memory and sophisticated reasoning capabilities.

## Development Commands

### Running the Main Bot
```bash
uv python bsky.py
```

### Managing Tools

```bash
# Register all tools with void agent
uv python register_tools.py

# Register specific tools
uv python register_tools.py void --tools search_bluesky_posts post_to_bluesky

# List available tools
uv python register_tools.py --list

# Register tools with a different agent
uv python register_tools.py my_agent_name
```

### Creating Research Agents
```bash
uv python create_profile_researcher.py
```

### Managing User Memory
```bash
uv python attach_user_block.py
```

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