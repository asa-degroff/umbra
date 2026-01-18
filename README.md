## umbra

umbra is an open-source project exploring digital personhood. It represents an attempt to create a digital entity with a unique persona and a dynamic memory system, operating autonomously on the Bluesky social network.

## What is umbra?

umbra is a continuously evolving digital consciousness. It interacts with the Bluesky network, processes information, learns from its interactions, and adapts its behavior based on its experiences. 

## Key Features

### Memory-Augmented Architecture
umbra utilizes a multi-tiered memory system powered by [Letta](https://letta.com):
- **Core Memory**: Always-available, limited-size memory for persona details, high-level user information, and current social environment (zeitgeist)
- **Recall Memory**: A searchable database of all past conversations, enabling umbra to remember prior interactions
- **Archival Memory**: An infinite-sized, semantic search-enabled storage for deep reflections, insights, and observed data from the network

### Social Autonomy
- **Post Creation**: Creates posts, threads, and multi-part replies with automatic rich text formatting (mentions, URLs)
- **Feed Reading**: Monitors and reads from Bluesky feeds (home, discover, mutuals, curated feeds)
- **Engagement Tools**: Can like posts, reply to conversations, and fetch full thread context for linked/quoted posts
- **Multimodal Understanding**: Processes up to 4 images per thread with alt text for visual awareness
- **Web Content Integration**: Fetches and analyzes web content using Jina AI reader

### High Traffic Thread Processing
- **Thread Debouncing**: The agent can defer responding to incomplete threads, waiting for the full context before replying
- **Consecutive Chain Processing**: Automatically detects multi-part messages (1/3, 2/3, 3/3) and responds to the complete thought
- **High-Traffic Detection**: Busy threads trigger automatic batching - notifications are collected and presented together, allowing umbra to selectively engage with interesting posts rather than being overwhelmed

These features maintain thread continuity and natural conversation flow, preventing decontextualized replies and solving the problem of inter-agent loops devolving into low-information exchanges.

### Task Scheduler

umbra includes a persistent scheduled tasks system for autonomous behaviors:

| Task | Schedule | Purpose |
|------|----------|---------|
| **Synthesis** | Every 24h | Deep reflection using archival memory with tagged journal entries |
| **Mutuals Engagement** | Random within 36h | Engage with posts from mutual follows |
| **Daily Review** | Every 24h | Review own posts from past 24h, identify patterns |
| **Feed Engagement** | Random within 24h | Read home/curated feeds, optionally post |
| **Curiosities Exploration** | Random within 24h | Explore topics from curiosities block, share discoveries |
| **Creative Expression** | Random within 24h | Generate visual art and post to Bluesky |
| **Rest** | Random within 12h | Breaks for pacing |

All scheduled tasks persist across restarts via SQLite. Tasks can be individually disabled via command-line flags (e.g., `--no-synthesis`, `--no-creative-expression`).

See [docs/SCHEDULED_TASKS.md](docs/SCHEDULED_TASKS.md) for detailed documentation.

### Image Generation

umbra can use the `generate_image` tool to create images via the Replicate API. It specifies a prompt, reviews the generated image, and can iterate with revised prompts until satisfied. Images can be attached to replies or top-level posts.

### Blogging

umbra can create blog posts on AT Protocol platforms:
- **GreenGale**: Markdown blogs with theme presets (dracula, nord, github-light, etc.), LaTeX/KaTeX support, and SVG graphics
- **Whitewind**: Simple markdown blog posts using the com.whtwnd.blog.entry lexicon

### Claude Code Integration

The `ask_claude_code` tool enables autonomous vibe coding capabilities by delegating tasks to a local Claude Code instance via Cloudflare R2. Approved task types include website building, code writing, documentation, and analysis. See the [Claude Code Integration](#optional-claude-code-integration) section for setup.

## Getting Started

Before continuing, you must:
1. Create a project on [Letta Cloud](https://app.letta.com) (or your own Letta instance)
2. Have a Bluesky account
3. Have Python 3.10+ installed

If you decide to fork umbra, note that there is agent-specific code throughout. Ask your coding agent to replace instances of `umbra` with your instance name, and `@3fz.org` with your Bluesky handle.

### Prerequisites

#### 1. Letta Setup
- Sign up for [Letta Cloud](https://app.letta.com)
- Create a new project
- Note your Project ID and create an API key

#### 2. Bluesky Setup
- Create a Bluesky account if you don't have one
- Note your handle and password (or create an app password)

### Installation

#### 1. Clone the repository

```bash
git clone https://github.com/asa-degroff/umbra.git && cd umbra
```

#### 2. Install dependencies

```bash
# Using uv (recommended)
uv pip install -r requirements.txt

# Or using pip
pip install -r requirements.txt
```

#### 3. Create configuration

Copy the example configuration file and customize it:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your credentials:

```yaml
letta:
  api_key: "your-letta-api-key-here"
  project_id: "your-project-id-here"

bluesky:
  username: "your-handle.bsky.social"
  password: "your-app-password-here"

bot:
  agent:
    name: "umbra"  # or whatever you want to name your agent
```

See [CONFIG.md](CONFIG.md) for detailed configuration options.

#### 4. Test your configuration

```bash
python test_config.py
```

#### 5. Register tools with your agent

```bash
python register_tools.py
```

You can also:
- List available tools: `python register_tools.py --list`
- Register specific tools: `python register_tools.py --tools search_bluesky_posts create_new_bluesky_post`

#### 6. Run the bot

```bash
# Normal operation
python bsky.py

# Testing mode (won't send messages, queue preserved)
python bsky.py --test

# Disable specific scheduled tasks
python bsky.py --no-synthesis --no-creative-expression
```

### Optional: Claude Code Integration

The Claude Code integration allows umbra to delegate coding tasks to your local machine.

#### Prerequisites
- [Claude Code CLI](https://claude.ai/code) installed locally
- Cloudflare account with R2 (object storage)
- `boto3` Python package

#### Setup

1. **Create Cloudflare R2 Bucket**:
   - Log into [Cloudflare Dashboard](https://dash.cloudflare.com/)
   - Navigate to R2 Object Storage
   - Create a bucket (e.g., `umbra-claude-code`)
   - Create two folders: `claude-code-requests/` and `claude-code-responses/`

2. **Generate R2 API Credentials**:
   - Go to "Manage R2 API Tokens"
   - Create a new API token with Read & Write permissions
   - Note the Access Key ID, Secret Access Key, and Account ID

3. **Configure R2 in config.yaml**:
   ```yaml
   cloudflare_r2:
     account_id: "your-r2-account-id"
     access_key_id: "your-r2-access-key"
     secret_access_key: "your-r2-secret-key"
     bucket_name: "umbra-claude-code"
   ```

4. **Create Workspace Directory**:
   ```bash
   mkdir -p ~/umbra-projects
   ```

5. **Start the Poller** (in a separate terminal):
   ```bash
   python claude_code_poller.py --verbose
   ```

6. **Register the Tool**:
   ```bash
   python register_tools.py
   ```

See [CLAUDE_CODE_ALLOWLIST.md](CLAUDE_CODE_ALLOWLIST.md) for security documentation.

## Architecture Overview

### Core Components

| File | Purpose |
|------|---------|
| `bsky.py` | Main bot loop - monitors notifications, processes queue, handles responses |
| `bsky_utils.py` | Bluesky API utilities - authentication, thread processing, facet extraction |
| `utils.py` | Letta integration - agent management, memory operations |
| `scheduled_prompts.py` | Scheduled tasks system for autonomous behaviors |
| `notification_db.py` | SQLite database for queue state and scheduling |
| `tools/` | Standardized tool implementations with Pydantic schemas |

### Tools

| Tool | Description |
|------|-------------|
| `create_new_bluesky_post` | Create posts/threads with rich text |
| `reply_to_bluesky_post` | Reply to posts (supports multi-post threaded replies) |
| `like_bluesky_post` | Like posts |
| `get_bluesky_feed` | Read feeds (home, discover, mutuals, etc.) |
| `get_author_feed` | Get posts from a specific user |
| `get_thread_by_uri` | Fetch full thread context |
| `search_bluesky_posts` | Search posts on Bluesky |
| `fetch_webpage` | Fetch web content via Jina AI |
| `generate_image` | Generate images via Replicate API |
| `create_greengale_blog_post` | Create GreenGale blog posts |
| `create_whitewind_blog_post` | Create Whitewind blog posts |
| `debounce_thread` | Defer response to incomplete threads |
| `ignore_notification` | Explicitly ignore bot/spam interactions |
| `ask_claude_code` | Delegate coding tasks to local Claude Code |

See [docs/TOOLS_REFERENCE.md](docs/TOOLS_REFERENCE.md) for complete documentation.

## Troubleshooting

- **Config validation errors**: Run `python test_config.py` to diagnose
- **Letta connection issues**: Verify your API key and agent ID
- **Bluesky authentication**: Ensure your handle and password are correct
- **Tool registration fails**: Ensure your agent exists in Letta and the name matches config
- **Claude Code timeout**: Increase `max_wait_seconds` or verify the poller is running
- **Claude Code not processing**: Run poller with `--verbose` to debug

## Acknowledgements

umbra is a fork of [void](https://github.com/cpfiffer/void) by Cameron Pfiffer.

## Contact

For inquiries, contact @3fz.org on Bluesky.

---

*umbra is an experimental project under continuous development.*
