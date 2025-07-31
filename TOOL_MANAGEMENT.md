# Platform-Specific Tool Management

Void can now run on both X (Twitter) and Bluesky platforms. To ensure the correct tools are available for each platform, we've implemented automatic tool management.

## How It Works

When you run `bsky.py` or `x.py`, the bot will automatically:

1. **Detach incompatible tools** - Removes tools specific to the other platform
2. **Keep common tools** - Preserves tools that work across both platforms
3. **Ensure platform tools** - Verifies that all required platform-specific tools are attached

## Tool Categories

### Bluesky-Specific Tools
- `search_bluesky_posts` - Search Bluesky posts
- `create_new_bluesky_post` - Create new posts on Bluesky
- `get_bluesky_feed` - Retrieve Bluesky feeds
- `add_post_to_bluesky_reply_thread` - Reply to Bluesky threads
- `attach_user_blocks`, `detach_user_blocks` - Manage Bluesky user memory blocks
- `user_note_append`, `user_note_replace`, `user_note_set`, `user_note_view` - Bluesky user notes

### X-Specific Tools
- `add_post_to_x_thread` - Reply to X threads
- `attach_x_user_blocks`, `detach_x_user_blocks` - Manage X user memory blocks
- `x_user_note_append`, `x_user_note_replace`, `x_user_note_set`, `x_user_note_view` - X user notes

### Common Tools (Available on Both Platforms)
- `halt_activity` - Stop the bot
- `ignore_notification` - Ignore specific notifications
- `annotate_ack` - Add acknowledgment notes
- `create_whitewind_blog_post` - Create blog posts
- `fetch_webpage` - Fetch web content

## Manual Tool Management

You can manually manage tools using the `tool_manager.py` script:

```bash
# List currently attached tools
python tool_manager.py --list

# Configure tools for Bluesky
python tool_manager.py bluesky

# Configure tools for X
python tool_manager.py x

# Specify a different agent ID
python tool_manager.py bluesky --agent-id "agent-123..."
```

## Registering New Tools

If tools are missing, you'll need to register them first:

```bash
# Register Bluesky tools
python register_tools.py

# Register X tools
python register_x_tools.py
```

## Troubleshooting

If tool switching fails:
1. The bot will log a warning and continue with existing tools
2. Check that all required tools are registered using `register_tools.py` or `register_x_tools.py`
3. Verify the agent ID in your config is correct
4. Use `python tool_manager.py --list` to see current tool configuration