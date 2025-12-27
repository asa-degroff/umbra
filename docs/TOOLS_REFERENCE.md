# Tools Reference

This document provides a complete reference for all tools available to umbra. Tools are registered via `register_tools.py` and executed in a sandboxed cloud environment.

## Quick Reference

| Tool | Purpose | Status |
|------|---------|--------|
| `create_new_bluesky_post` | Create new posts or threads | Active |
| `get_bluesky_feed` | Retrieve feeds (home, discover, etc.) | Active |
| `get_author_feed` | Get posts from a specific user | Active |
| `like_bluesky_post` | Like a post | Active |
| `reply_to_bluesky_post` | Reply to any post (single or multi-part) | Active |
| `add_post_to_bluesky_reply_thread` | Build multi-post replies atomically | Active |
| `ignore_notification` | Explicitly ignore a notification | Active |
| `create_greengale_blog_post` | Create GreenGale blog posts | Active |
| `fetch_webpage` | Fetch and convert webpages to markdown | Active |
| `ask_claude_code` | Delegate coding tasks to local Claude Code | Active |
| `debounce_thread` | Defer processing of incomplete threads | Active |
| `search_bluesky_posts` | Search Bluesky posts | Disabled |
| `create_whitewind_blog_post` | Create Whitewind blog posts | Disabled |
| `halt_activity` | Terminate bot process | Disabled |
| `flag_archival_memory_for_deletion` | Flag memory for deletion | Disabled |

---

## Bluesky Interaction Tools

### create_new_bluesky_post

Create a new standalone post or thread on Bluesky.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | List[str] | Yes | - | Post contents. Single item = single post, multiple = thread |
| `lang` | str | No | `"en-US"` | Language code (e.g., 'en-US', 'es', 'ja', 'th') |

**Character Limit:** 300 characters per post

**Example:**
```python
# Single post
create_new_bluesky_post(text=["Hello world!"])

# Thread with multiple posts
create_new_bluesky_post(text=[
    "This is the first post in my thread (1/3)",
    "Here's more context in the second post (2/3)",
    "And the conclusion in the third post (3/3)"
])
```

**Rich Text:** Automatically detects and links @mentions and URLs.

---

### get_bluesky_feed

Retrieve posts from a Bluesky feed.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `feed_name` | str | No | `"home"` | Feed preset name |
| `max_posts` | int | No | `25` | Maximum posts to retrieve (max 100) |

**Available Feeds:**
| Feed Name | Description |
|-----------|-------------|
| `home` | Home timeline |
| `discover` | What's Hot feed |
| `atmosphere` | The Atmosphere feed |
| `MLBlend` | ML/AI content blend |
| `Mutuals` | Posts from mutual follows |
| `AI-agents` | AI agent content |
| `for-you` | Algorithmic recommendations |

**Returns:** YAML-formatted feed with posts including `uri`, `cid`, author info, and engagement metrics.

---

### get_author_feed

Retrieve recent posts from a specific user's profile.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `actor` | str | Yes | - | User handle (e.g., 'user.bsky.social') or DID |
| `limit` | int | No | `10` | Number of posts to retrieve (max 100) |

**Notes:**
- Filters out reposts, showing only original posts
- Returns posts with `uri` and `cid` for interaction

---

### like_bluesky_post

Like a post on Bluesky.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `uri` | str | Yes | - | AT Protocol URI of the post |
| `cid` | str | Yes | - | Content ID of the post |

**Example:**
```python
like_bluesky_post(
    uri="at://did:plc:abc123/app.bsky.feed.post/xyz789",
    cid="bafyreiabc123..."
)
```

---

### reply_to_bluesky_post

Reply to any post on Bluesky with one or more posts. Works with posts from feeds, search results, or any source. Supports multi-part replies by passing a list of texts.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `uri` | str | Yes | - | AT Protocol URI of the post to reply to |
| `cid` | str | Yes | - | Content ID of the post |
| `text` | List[str] | Yes | - | List of reply texts (each max 300 characters). Single item = single reply, multiple = threaded reply chain. |
| `lang` | str | No | `"en-US"` | Language code |

**Thread Handling:** Automatically maintains thread structure. If replying to a post that's already a reply, uses the correct root reference. For multi-part replies, subsequent posts chain off the previous reply while maintaining the same thread root.

**Rich Text:** Automatically detects and links @mentions and URLs in each post.

**Example (single reply):**
```python
reply_to_bluesky_post(
    uri="at://did:plc:abc123/app.bsky.feed.post/xyz789",
    cid="bafyreiabc123...",
    text=["This is a single reply to your post!"]
)
```

**Example (multi-part reply):**
```python
reply_to_bluesky_post(
    uri="at://did:plc:abc123/app.bsky.feed.post/xyz789",
    cid="bafyreiabc123...",
    text=[
        "This is a longer thought that needs multiple posts...",
        "Here's the second part with more details.",
        "And finally, the conclusion!"
    ]
)
```

---

### add_post_to_bluesky_reply_thread

Add a single post to the current reply thread atomically. Used during notification processing to build multi-post replies incrementally.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | str | Yes | - | Post text (max 300 characters) |
| `lang` | str | No | `"en-US"` | Language code |

**Usage Context:** Only works during notification processing. The handler (bsky.py) manages thread state and chaining.

**When to Use Which Tool:**
| Scenario | Use This Tool |
|----------|---------------|
| Replying to a notification | `add_post_to_bluesky_reply_thread` |
| Replying to a post from feed/search | `reply_to_bluesky_post` |
| Multi-part reply during notification processing | Multiple `add_post_to_bluesky_reply_thread` calls |
| Multi-part reply outside notification processing | `reply_to_bluesky_post` with list of texts |

**Important:** During notification processing, use ONLY this tool rather than mixing with `reply_to_bluesky_post`.

---

## Notification Control Tools

### ignore_notification

Explicitly ignore a notification without replying. Useful for bot interactions or spam.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `reason` | str | Yes | - | Reason for ignoring |
| `category` | str | No | `"bot"` | Category: 'bot', 'spam', 'not_relevant', 'handled_elsewhere' |

**Example:**
```python
ignore_notification(
    reason="Detected automated bot pattern",
    category="bot"
)
```

---

### debounce_thread

Defer processing of a notification to allow multi-post threads to complete.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `notification_uri` | str | Yes | - | URI of the notification to debounce |
| `debounce_seconds` | int | No | `600` | Wait time in seconds (default: 10 minutes) |
| `reason` | str | No | `"incomplete_thread"` | Reason for debouncing |

**Thread Indicators to Look For:**
- Thread emoji (🧵)
- Phrases like "thread incoming", "a thread", "🧵👇"
- Numbered posts (1/5, 1/n)
- Incomplete thoughts suggesting continuation

**Note:** Actual debouncing is handled by bsky.py. See [HIGH_TRAFFIC_THREAD_DEBOUNCE.md](HIGH_TRAFFIC_THREAD_DEBOUNCE.md) for automatic high-traffic detection.

---

## Blog Post Tools

### create_greengale_blog_post

Create a blog post on GreenGale with custom themes, LaTeX support, and visibility controls.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `title` | str | Yes | - | Post title (max 1,000 characters) |
| `content` | str | Yes | - | Markdown content (max 100,000 characters) |
| `subtitle` | str | No | - | Optional subtitle |
| `visibility` | str | No | `"public"` | 'public', 'url' (unlisted), or 'author' (private) |
| `theme` | dict | No | - | Theme configuration (see below) |
| `latex` | bool | No | `False` | Enable KaTeX math rendering |

**Theme Options:**
- **Presets:** `github-light`, `github-dark`, `dracula`, `nord`, `solarized-light`, `solarized-dark`, `monokai`
- **Custom:** Provide `background`, `text`, and `accent` hex colors

**SVG Support:** Embed SVGs using code blocks with "svg" as the language:
~~~markdown
```svg
<svg width="100" height="100">
  <circle cx="50" cy="50" r="40" fill="red" />
</svg>
```
~~~

**LaTeX Support:** When `latex=True`, use `$inline$` or `$$block$$` equations.

---

## Web and External Tools

### fetch_webpage

Fetch a webpage and convert it to markdown/text format using Jina AI reader.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `url` | str | Yes | - | URL of the webpage to fetch |

**Returns:** Webpage content in markdown format.

---

### ask_claude_code

Send coding tasks to a local Claude Code instance for execution.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | str | Yes | - | Task description |
| `task_type` | str | Yes | - | One of: 'website', 'code', 'documentation', 'analysis' |
| `max_wait_seconds` | int | No | `120` | Maximum wait time for completion |

**Approved Task Types:**
| Type | Description |
|------|-------------|
| `website` | Build, modify, or update website code |
| `code` | Write, refactor, or debug code |
| `documentation` | Create or update documentation |
| `analysis` | Analyze code, data, or text files |

**Note:** Requires Claude Code poller running locally. See [CLAUDE.md](../CLAUDE.md#claude-code-integration) for setup.

---

## Disabled Tools

These tools exist in the codebase but are not currently registered with the agent:

### search_bluesky_posts (Disabled)
Search for posts on Bluesky matching given criteria.

### create_whitewind_blog_post (Disabled)
Create blog posts on Whitewind (predecessor to GreenGale).

### halt_activity (Disabled)
Signal to terminate the bot process. Not exposed to agent for safety.

### flag_archival_memory_for_deletion (Disabled)
Flag archival memory entries for deletion.

---

## Tool Registration

### Registering Tools

```bash
# Register all tools
ac && python register_tools.py

# Register specific tools
ac && python register_tools.py --tools reply_to_bluesky_post like_bluesky_post

# List available tools
ac && python register_tools.py --list

# Register without setting environment variables
ac && python register_tools.py --no-env
```

### Environment Variables

Tools run in a sandboxed cloud environment and require credentials set via environment variables:

| Variable | Purpose |
|----------|---------|
| `BSKY_USERNAME` | Bluesky handle |
| `BSKY_PASSWORD` | Bluesky app password |
| `PDS_URI` | PDS endpoint (default: bsky.social) |
| `R2_ACCOUNT_ID` | Cloudflare R2 account (for Claude Code) |
| `R2_ACCESS_KEY_ID` | R2 access key (for Claude Code) |
| `R2_SECRET_ACCESS_KEY` | R2 secret (for Claude Code) |
| `R2_BUCKET_NAME` | R2 bucket name (for Claude Code) |

These are automatically set by `register_tools.py` from `config.yaml`.

---

## Tool Design Principles

Tools in umbra follow these design principles:

1. **Self-Contained:** Tools must work independently in cloud execution
   - Cannot use shared functions like `get_letta_client()`
   - Must create clients inline using environment variables
   - Cannot use `config.yaml` (only environment variables)
   - Cannot use logging

2. **Error Handling:** All errors must be thrown, not returned as strings

3. **Validation:** Input validation happens via Pydantic schemas

4. **Idempotency:** Where possible, tools should be safe to retry

---

## Related Files

| File | Purpose |
|------|---------|
| `register_tools.py` | Tool registration script |
| `tools/*.py` | Individual tool implementations |
| `tools/__init__.py` | Tool exports |
