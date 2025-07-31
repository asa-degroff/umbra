# Tool Changelog - Recent Updates

## Latest Changes (January 2025)

### ✅ NEW: Platform-Specific Tool Management
- **Purpose**: Automatically manage tools based on platform (Bluesky vs X)
- **Implementation**: `tool_manager.py` handles tool switching
- **Behavior**: 
  - Running `bsky.py` activates Bluesky-specific tools
  - Running `x.py` activates X-specific tools
  - Common tools remain available on both platforms
- **Tools Categories**:
  - **Bluesky Tools**: `search_bluesky_posts`, `create_new_bluesky_post`, `get_bluesky_feed`, `add_post_to_bluesky_reply_thread`, user memory tools
  - **X Tools**: `add_post_to_x_thread`, X-specific user memory tools
  - **Common Tools**: `halt_activity`, `ignore_notification`, `annotate_ack`, `create_whitewind_blog_post`, `fetch_webpage`

### ✅ NEW TOOL: `fetch_webpage`
- **Purpose**: Fetch and convert web pages to markdown/text using Jina AI reader
- **Parameters**:
  - `url` (required): The URL to fetch and convert
- **Returns**: Web page content in markdown/text format
- **Usage**: Access and analyze web content for enhanced context

### ✅ ENHANCED: Reply Structure Fix
- **Issue**: Reply threading was broken due to incorrect root post references
- **Fix**: Now properly extracts root URI/CID from notification reply structure
- **Impact**: Bluesky replies now properly maintain thread context

### ✅ ENHANCED: #voidstop Keyword Support
- **Purpose**: Allow users to prevent void from replying to specific posts
- **Usage**: Include `#voidstop` anywhere in a post or thread
- **Behavior**: void will skip processing mentions in posts containing this keyword

### ✅ NEW TOOL: `annotate_ack`
- **Purpose**: Add notes to acknowledgment records for post interactions
- **Parameters**:
  - `note` (required): Note text to attach to acknowledgment
- **Usage**: Track interaction metadata and reasoning

### ✅ NEW TOOL: `create_whitewind_blog_post`
- **Purpose**: Create blog posts on Whitewind platform with markdown support
- **Parameters**:
  - `title` (required): Blog post title
  - `content` (required): Markdown content
  - `visibility` (optional): Public/private visibility
- **Usage**: Create longer-form content beyond social media posts

## Previous Changes

### ✅ ENHANCED: Atomic Reply Threading
- **Tool**: `add_post_to_bluesky_reply_thread`
- **Purpose**: Add single posts to reply threads atomically
- **Benefits**: Better error recovery, flexible threading, clearer intent

### ❌ REMOVED TOOL: `bluesky_reply`
- Replaced by atomic `add_post_to_bluesky_reply_thread` approach
- Migration: Replace single list call with multiple atomic calls

## Migration Notes

### For Platform Switching
- No action required - tools automatically switch based on platform
- Use `python tool_manager.py --list` to check current tool configuration

### For Web Content Integration
- Replace manual web scraping with `fetch_webpage` tool calls
- Automatically handles conversion to markdown for AI processing

### For Enhanced Interaction Control
- Use `#voidstop` in posts to prevent void responses
- Use `annotate_ack` to add metadata to interactions
- Use `ignore_notification` for bot-to-bot interaction control

## Tool Registration

```bash
# Register all Bluesky tools
python register_tools.py

# Register all X tools  
python register_x_tools.py

# Manual tool management
python tool_manager.py bluesky  # Configure for Bluesky
python tool_manager.py x        # Configure for X
```

See [`TOOL_MANAGEMENT.md`](/TOOL_MANAGEMENT.md) for detailed platform-specific tool management information.