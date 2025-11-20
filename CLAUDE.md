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

# Enable daily mutuals engagement (prompts umbra to read and reply to mutuals feed once per day at random time)
ac && python bsky.py --mutuals-engagement

# Run with both synthesis and mutuals engagement enabled
ac && python bsky.py --synthesis-interval 3600 --mutuals-engagement
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

### Thread Debouncing

Thread debouncing allows umbra to defer responding to posts that appear to be the first part of an incomplete multi-post thread. This enables umbra to see the complete thread before responding, rather than replying to just the first post without full context.

#### How It Works

1. When umbra receives a notification, if the post appears to be the start of an incomplete thread (contains thread indicators like 🧵, "thread incoming", numbered posts like "1/5", etc.), the agent can call the `debounce_thread` tool
2. The notification is marked for later processing (default: 10 minutes)
3. After the debounce period expires, umbra fetches the complete current state of the thread
4. Umbra then responds with full context of all posts in the thread

#### Configuration

Enable thread debouncing in `config.yaml`:

```yaml
threading:
  debounce_enabled: true   # Set to true to enable (default: false)
  debounce_seconds: 600    # Wait time in seconds (default: 10 minutes)
  max_debounce_seconds: 1200  # Maximum wait time (default: 20 minutes)
```

#### Agent Behavior

When `debounce_enabled` is true:
- The agent receives an additional prompt section explaining the debounce capability
- The agent is informed about thread indicators to look for
- The agent decides whether to debounce based on the post content
- If debounced, the notification is skipped during normal processing
- After the debounce period expires, the agent receives the complete thread

#### Database Migration

If upgrading from a version without thread debouncing, run the migration:

```bash
ac && python migrate_debounce_schema.py
```

This adds the required database columns (`debounce_until`, `debounce_reason`, `thread_chain_id`) to track debounced notifications.

#### Tool: debounce_thread

The agent has access to the `debounce_thread` tool when debouncing is enabled:

**Parameters:**
- `notification_uri`: URI of the notification to debounce
- `debounce_seconds`: How long to wait (optional, defaults to config value)
- `reason`: Reason for debouncing (optional, defaults to "incomplete_thread")

**Example agent call:**
```python
debounce_thread(
    notification_uri="at://did:plc:abc123/app.bsky.feed.post/xyz789",
    debounce_seconds=600
)
```

#### Monitoring Debounced Notifications

Debounced notifications remain in the queue but are skipped during processing. Check logs for:
- `⏸️ Skipping debounced notification` - Still waiting for debounce period to expire
- `⏰ Found N expired debounced notifications` - Processing debounced threads
- `⏰ Processing debounced thread from @handle` - Currently processing a debounced thread

### Claude Code Integration

The Claude Code tool allows umbra to delegate coding tasks to a local Claude Code instance running on the administrator's machine. This enables umbra to build websites, write code, create documentation, and perform analysis.

#### Setup

1. **Configure Cloudflare R2** (see CONFIG.md for detailed setup):
   - Create an R2 bucket (e.g., `umbra-claude-code`)
   - Create two folders: `claude-code-requests/` and `claude-code-responses/`
   - Generate R2 API credentials
   - Add credentials to `config.yaml`

2. **Create Workspace Directory**:
   ```bash
   mkdir -p ~/umbra-projects
   ```

3. **Test R2 Connection**:
   ```bash
   ac && python test_claude_code_tool.py
   ```

4. **Start the Poller** (in a separate terminal or as a background service):
   ```bash
   # Run in foreground (see Claude Code output in real-time)
   ac && python claude_code_poller.py --verbose

   # Or run without verbose mode (quieter)
   ac && python claude_code_poller.py

   # Or run in background with logging
   ac && python claude_code_poller.py > claude_code_poller.log 2>&1 &

   # Or run in background with verbose logging
   ac && python claude_code_poller.py --verbose > claude_code_poller.log 2>&1 &

   # Or use systemd/supervisor for production
   ```

5. **Register the Tool**:
   ```bash
   ac && python register_tools.py
   # This will automatically set R2 environment variables on the agent
   ```

#### Usage

Once configured, umbra can use the `ask_claude_code` tool with these approved task types:

- **website**: Build, modify, or update website code
- **code**: Write, refactor, or debug code
- **documentation**: Create or update documentation
- **analysis**: Analyze code, data, or text files

Example prompts umbra might use:
```
ask_claude_code(
    prompt="Create a dark-themed landing page for umbra with an About section",
    task_type="website",
    max_wait_seconds=180
)
```

#### Security

The integration uses an allowlist-based security model:
- Only approved task types are executed
- All executions run in a restricted workspace directory (`~/umbra-projects/`)
- Requests expire after 10 minutes
- All activity is logged
- See `CLAUDE_CODE_ALLOWLIST.md` for detailed security documentation

#### Monitoring

Check poller logs to monitor Claude Code execution:
```bash
# View live logs if running in background
tail -f claude_code_poller.log

# View R2 bucket contents
# Use Cloudflare dashboard or AWS CLI with R2 endpoint
```

#### Troubleshooting

**Poller not processing requests:**
- Ensure poller is running: `ps aux | grep claude_code_poller`
- Check R2 credentials in config.yaml
- Verify bucket name matches configuration
- Check poller logs for errors

**Tool returning timeout errors:**
- Increase `max_wait_seconds` in tool call
- Check if poller is running
- Verify Claude Code CLI is installed: `which claude`
- Check network connectivity to R2

**Invalid task type errors:**
- Ensure task_type is one of: website, code, documentation, analysis
- Task types are case-sensitive (use lowercase)
- See `CLAUDE_CODE_ALLOWLIST.md` for approved types

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
   - **like.py**: LikeBlueskyTool for liking posts
   - **reply.py**: ReplyToBlueskyPostTool for replying to any post (works with feeds, search results, etc.)
   - **blocks.py**: User block management tools (attach, detach, update)
   - **claude_code.py**: Claude Code integration for delegating coding tasks to local instance

5. **claude_code_poller.py**: Local daemon that polls R2 for coding requests from umbra and executes them via Claude Code CLI

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