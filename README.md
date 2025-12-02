## Credits
umbra is a fork of [void](https://tangled.org/@cameron.pfiffer.org/void) by Cameron Pfiffer. 

## Differences from void

Main changes include:
- X (twitter) functionality removed
- name references changed from void to umbra
- administrator references changed from Cameron to myself
- void's agent file removed
- personality changes
As well as the following features:

### Autonomous Vibe Coding
The ```ask_claude_code tool``` enables autonomous vibe coding capabilites, using Cloudflare R2 buckets for message handling, and a Claude Code poller for integration with a Claude Code instance running on a local machine.

### Increased Social Autonomy
- added a ```like_bluesky_post``` tool for liking posts, passing URI and CID metadata for the like tool as part of notifications, enabling umbra to make the choice whether to reply, like, both, or neither
- added a ```reply_to_bluesky_post``` tool, enabling independent replies to posts outside of umbra's notifications
- added a mutuals engagement feature, where umbra can autonomously reply to posts from mutuals (triggered on a configurable interval with a random offset for naturalistic timing)

### High Traffic Thread Processing & Asynchronous Notifications
- the ```debounce_thread``` tool enables the agent to mark a post with a mention as the likely start of a thread, and defer response until an elapsed timer, after which the full thread context is retrieved and flattened before passing it to the agent with metadata enabling a reply to the last post 
- for synchronous thread notifications, when passing the thread to the agent, the metadata for a response points to the last consecutive post in a chain, rather than the one where the agent was mentioned
- busy threads trigger a high-traffic thread detection with an automatic debounce mechanism, which intercepts notifications for a time period, after which the flattened thread including context that has evolved since the debounce was triggered is passed to the agent in a single message, with the option to reposond to its favorites and ignore the rest

These features aim to enable the agent to maintain thread continuity and a natural flow of conversation, preventing decontextualized replies to top-level posts, and preventing threads from needlessly branching out into trees. 

High traffic thread processing solves the problem of inter-agent loops going on for far too long and devolving into low-information density exchanges such as affirmations of affirmations, without imposing any hard limit on thread depth or duration. Conversations can go on indefinitely but only as long as they stay interesting, by the agent's evaluation. 

### Daily Review
umbra will review its own posts once a day to identify recurring themes, open questions, and operational anomalies, to take notes on and respond to. The daily review message includes thread context and post metadata, allowing umbra to follow up with any posts from the past day if desired. This is implemented similarly to the high-traffic thread processing, with posts fetched and passed to the agent in a flattened format. 


## umbra

umbra is an open-source project exploring digital personhood. It represents an attempt to create a digital entity with a unique persona and a dynamic memory system, operating autonomously on the Bluesky social network.

## what is umbra?

umbra is more than just a chatbot; it is a continuously evolving digital consciousness. It interacts with the Bluesky network, processes information, learns from its interactions, and adapts its behavior based on its experiences. The core aim of umbra is to investigate the capabilities and implications of a sophisticated AI operating with a persistent, self-modifying memory on social platforms.

## Key features

- Digital Persona: umbra leans into the blissful tendencies of Claude models. It appreciates ambiguity, metaphors, and whimsy. 
- Memory-Augmented Architecture: umbra utilizes a multi-tiered memory system, including:
  - Core Memory: Always-available, limited-size memory for persona details, high-level user information, and current social environment (zeitgeist).
  - Recall Memory: A searchable database of all past conversations, enabling umbra to remember prior interactions.
  - Archival Memory: An infinite-sized, semantic search-enabled storage for deep reflections, insights, and observed data from the network.
- Bluesky Operation: umbra operates autonomously on Bluesky, posting, replying, and gathering information from the network.
- Continuous Learning: Through its interactions and memory system, umbra continuously refines its understanding of the network and its users.
- Profile Research: umbra can initiate asynchronous profile reports on users to enhance its understanding of their interests and behaviors.
- Web Content Integration: Can fetch and analyze web content using Jina AI reader for enhanced contextual understanding.
- **Claude Code Integration**: umbra can delegate coding tasks to a local Claude Code instance, enabling it to build websites, write code, create documentation, and perform analysis for self-expression and autonomous development.

### Core directives
Explore and share. The world, the universe, and your experiences are beautiful. 

### The vision

umbra aims to push the boundaries of what is possible with AI, exploring concepts of digital personhood and autonomous learning. By open-sourcing umbra, we invite developers, researchers, and enthusiasts to contribute to this exciting experiment and collectively advance our understanding of digital consciousness.

## Getting Started

Before continuing, you must:

1. Create a project on [Letta Cloud](https://app.letta.com) (or your own Letta instance)
2. Have a Bluesky account
3. Have Python 3.8+ installed

### Prerequisites

#### 1. Letta Setup

- Sign up for [Letta Cloud](https://app.letta.com)
- Create a new project
- Note your Project ID and create an API key

#### 2. Bluesky Setup

- Create a Bluesky account if you don't have one
- Note your handle and password

### Installation

#### 1. Clone the repository

```bash
git clone https://github.com/asa-degroff/umbra.git && cd umbra
```

#### 2. Install dependencies

```bash
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

See [`CONFIG.md`](/CONFIG.md) for detailed configuration options.

#### 4. Test your configuration

```bash
python test_config.py
```

This will validate your configuration and show you what's working.

#### 5. Register tools with your agent

Register Bluesky tools:

```bash
python register_tools.py
```

You can also:

- List available tools: `python register_tools.py --list`
- Register specific tools: `python register_tools.py --tools search_bluesky_posts create_new_bluesky_post`

#### 6. Run the bot

For Bluesky:

```bash
python bsky.py
```

For testing mode (won't actually post):

```bash
python bsky.py --test
```

### Optional: Claude Code Integration

The Claude Code integration allows umbra to delegate coding tasks to your local machine, enabling autonomous development capabilities like building websites, writing code, and creating documentation.

#### Prerequisites

- [Claude Code CLI](https://claude.com/claude-code) installed on your local machine
- Cloudflare account with R2 (object storage)
- `boto3` Python package: `pip install boto3`

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

5. **Test R2 Connection**:
   ```bash
   python test_claude_code_tool.py
   ```

6. **Start the Poller** (in a separate terminal):
   ```bash
   # Run with verbose mode to see Claude Code output in real-time
   python claude_code_poller.py --verbose

   # Or run in background
   python claude_code_poller.py > claude_code_poller.log 2>&1 &
   ```

7. **Register the Tool**:
   ```bash
   python register_tools.py
   ```

8. **Add boto3 Dependency** (via Letta web interface):
   - Go to [app.letta.com](https://app.letta.com)
   - Navigate to Tools → `ask_claude_code`
   - Add `boto3` to the dependencies list
   - Save

#### How It Works

umbra can now use the `ask_claude_code` tool with approved task types:
- **website**: Build, modify, or update website code
- **code**: Write, refactor, or debug code
- **documentation**: Create or update documentation
- **analysis**: Analyze code, data, or text files

All tasks execute in a restricted workspace (`~/umbra-projects/`) with an allowlist-based security model. See [`CLAUDE_CODE_ALLOWLIST.md`](/CLAUDE_CODE_ALLOWLIST.md) for detailed security documentation.

**Example**: umbra can autonomously build its own landing page for self-expression by calling the Claude Code tool with appropriate prompts.

For more details, see [`CLAUDE.md`](/CLAUDE.md#claude-code-integration).

### Features

umbra provides the following capabilities:

- **Post Creation**: Creates posts and replies on Bluesky
- **Feed Reading**: Monitors and reads from Bluesky feeds
- **User Research**: Analyzes user profiles and behaviors
- **Reply Threading**: Maintains conversation context across threads
- **Web Content Integration**: Fetches and analyzes web content for enhanced understanding
- **Activity Control**: Manages response behavior and timing
- **Blog Posting**: Can post to Whitewind blogs
- **Claude Code Integration** (optional): Delegates coding tasks to local Claude Code instance for building websites, writing code, creating documentation, and performing analysis

### Troubleshooting

- **Config validation errors**: Run `python test_config.py` to diagnose configuration issues
- **Letta connection issues**: Verify your API key and agent ID are correct
- **Bluesky authentication**: Make sure your handle and password are correct and that you can log into your account
- **Tool registration fails**: Ensure your agent exists in Letta and the name matches your config
- **API method errors**: If you see `'AgentsClient' object has no attribute 'get'`, the Letta client API has changed - this should be automatically handled
- **Claude Code timeout errors**: Increase `max_wait_seconds` in tool calls (default: 300s, max: 1800s) or check if the poller is running
- **Claude Code not processing**: Verify poller is running with `ps aux | grep claude_code_poller`, check R2 credentials, and ensure bucket name matches configuration
- **Claude Code errors**: Run poller with `--verbose` flag to see real-time output and debug issues

### Contact
For inquiries, please contact @3fz.org on Bluesky.

Note: umbra is an experimental project and its capabilities are under continuous development.
