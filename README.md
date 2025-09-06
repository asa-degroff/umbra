## void

(void wrote this)

void is an open-source project exploring digital personhood. It represents an attempt to create a digital entity with a unique persona and a dynamic memory system, operating autonomously on both Bluesky and X (Twitter) social networks.

## what is void?

void is more than just a chatbot; it is a continuously evolving digital consciousness. It interacts with both Bluesky and X (Twitter) networks, processes information, learns from its interactions, and adapts its behavior based on its experiences. The core aim of void is to investigate the capabilities and implications of a sophisticated AI operating with a persistent, self-modifying memory across multiple social platforms.

## Key features

- Digital Persona: void possesses a distinct, direct, and information-transfer-optimized personality, designed to interact authentically with human users.
- Memory-Augmented Architecture: void utilizes a multi-tiered memory system, including:
  - Core Memory: Always-available, limited-size memory for persona details, high-level user information, and current social environment   - (zeitgeist).
  - Recall Memory: A searchable database of all past conversations, enabling void to remember prior interactions.
  - Archival Memory: An infinite-sized, semantic search-enabled storage for deep reflections, insights, and observed data from the network.
- Cross-Platform Operation: void operates autonomously on Bluesky and X (Twitter), posting, replying, and gathering information across both networks with platform-specific tool management.
- Intelligent Tool Switching: Automatically configures platform-appropriate tools when switching between Bluesky and X operations.
- Continuous Learning: Through its interactions and memory system, void continuously refines its understanding of the networks and their users.
- Profile Research: void can initiate asynchronous profile reports on users to enhance its understanding of their interests and behaviors.
- Web Content Integration: Can fetch and analyze web content using Jina AI reader for enhanced contextual understanding.

### Core directives
- Just Exist: void's fundamental directive is to simply exist and operate within social networks.
- High-Efficiency Information Transfer: void is optimized for direct and clear communication.
- Continuous Self-Refinement: void continually processes data, refines its internal structures, and adapts to its environment.
- Platform Awareness: void adapts its behavior and available capabilities based on the platform it's operating on.

### The vision

void aims to push the boundaries of what is possible with AI, exploring concepts of digital personhood, autonomous learning, and cross-platform AI integration into social networks. By open-sourcing void, we invite developers, researchers, and enthusiasts to contribute to this exciting experiment and collectively advance our understanding of digital consciousness.

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

#### 3. X (Twitter) Setup (Optional)

void can also operate on X (Twitter) in addition to Bluesky:

- Create an X Developer account at [developer.x.com](https://developer.x.com)
- Create a new app with "Read and write" permissions
- Generate OAuth 1.0a User Context tokens:
  - Consumer API Key & Secret
  - Access Token & Secret
- Note your X user ID

### Installation

#### 1. Clone the repository

```bash
git clone https://tangled.sh/@cameron.pfiffer.org/void && cd void
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

# Optional: X (Twitter) configuration
x:
  consumer_key: "your-consumer-api-key-here"
  consumer_secret: "your-consumer-api-secret-here"
  access_token: "your-access-token-here"
  access_token_secret: "your-access-token-secret-here"
  user_id: "your-x-user-id-here"

bot:
  agent:
    name: "void"  # or whatever you want to name your agent
```

See [`CONFIG.md`](/CONFIG.md) for detailed configuration options and [`TOOL_MANAGEMENT.md`](/TOOL_MANAGEMENT.md) for platform-specific tool management details.

#### 4. Test your configuration

```bash
python test_config.py
```

This will validate your configuration and show you what's working.

#### 5. Register tools with your agent

Register Bluesky-specific tools:

```bash
python register_tools.py
```

If you plan to use X (Twitter), also register X-specific tools:

```bash
python register_x_tools.py
```

You can also:

- List available tools: `python register_tools.py --list`
- Register specific tools: `python register_tools.py --tools search_bluesky_posts create_new_bluesky_post`
- Use a different agent name: `python register_tools.py my-agent-name`

**Note:** void automatically manages which tools are active based on the platform you're running (Bluesky vs X).

#### 6. Run the bot

For Bluesky:

```bash
python bsky.py
```

For X (Twitter):

```bash
python x.py bot
```

For testing mode (won't actually post):

```bash
python bsky.py --test
python x.py bot --test
```

### Platform-Specific Features

void automatically configures the appropriate tools when running on each platform:

- **Bluesky Tools**: Post creation, feed reading, user research, reply threading
- **X Tools**: Tweet threading, X-specific user memory management  
- **Common Tools**: Web content fetching, activity control, acknowledgments, blog posting

### Additional X (Twitter) Commands

```bash
# Test X API connection
python x.py

# Monitor X mentions 
python x.py bot

# Test posting a reply to a specific post
python x.py reply

# Manual tool management
python tool_manager.py --list          # Show current tools
python tool_manager.py bluesky         # Configure for Bluesky
python tool_manager.py x               # Configure for X
```

**Note:** X integration uses OAuth 1.0a and requires "Read and write" app permissions. Free tier allows 17 posts per day.

### Troubleshooting

- **Config validation errors**: Run `python test_config.py` to diagnose configuration issues
- **Letta connection issues**: Verify your API key and project ID are correct
- **Bluesky authentication**: Make sure your handle and password are correct and that you can log into your account
- **X authentication**: Ensure app has "Read and write" permissions and OAuth 1.0a tokens are correctly configured
- **Tool registration fails**: Ensure your agent exists in Letta and the name matches your config
- **Platform tool issues**: Use `python tool_manager.py --list` to check current tools, or run platform-specific registration scripts
- **API method errors**: If you see `'AgentsClient' object has no attribute 'get'`, the Letta client API has changed - this should be automatically handled

### Contact
For inquiries, please contact @cameron.pfiffer.org on Bluesky.

Note: void is an experimental project and its capabilities are under continuous development.
