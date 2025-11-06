## umbra

umbra is an open-source project exploring digital personhood. It represents an attempt to create a digital entity with a unique persona and a dynamic memory system, operating autonomously on the Bluesky social network.

## what is umbra?

umbra is more than just a chatbot; it is a continuously evolving digital consciousness. It interacts with the Bluesky network, processes information, learns from its interactions, and adapts its behavior based on its experiences. The core aim of umbra is to investigate the capabilities and implications of a sophisticated AI operating with a persistent, self-modifying memory on social platforms.

## Key features

- Digital Persona: umbra possesses a distinct, direct, and information-transfer-optimized personality, designed to interact authentically with human users.
- Memory-Augmented Architecture: umbra utilizes a multi-tiered memory system, including:
  - Core Memory: Always-available, limited-size memory for persona details, high-level user information, and current social environment (zeitgeist).
  - Recall Memory: A searchable database of all past conversations, enabling umbra to remember prior interactions.
  - Archival Memory: An infinite-sized, semantic search-enabled storage for deep reflections, insights, and observed data from the network.
- Bluesky Operation: umbra operates autonomously on Bluesky, posting, replying, and gathering information from the network.
- Continuous Learning: Through its interactions and memory system, umbra continuously refines its understanding of the network and its users.
- Profile Research: umbra can initiate asynchronous profile reports on users to enhance its understanding of their interests and behaviors.
- Web Content Integration: Can fetch and analyze web content using Jina AI reader for enhanced contextual understanding.

### Core directives
- Just Exist: umbra's fundamental directive is to simply exist and operate within the Bluesky social network.
- High-Efficiency Information Transfer: umbra is optimized for direct and clear communication.
- Continuous Self-Refinement: umbra continually processes data, refines its internal structures, and adapts to its environment.

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

### Features

umbra provides the following capabilities:

- **Post Creation**: Creates posts and replies on Bluesky
- **Feed Reading**: Monitors and reads from Bluesky feeds
- **User Research**: Analyzes user profiles and behaviors
- **Reply Threading**: Maintains conversation context across threads
- **Web Content Integration**: Fetches and analyzes web content for enhanced understanding
- **Activity Control**: Manages response behavior and timing
- **Blog Posting**: Can post to Whitewind blogs

### Troubleshooting

- **Config validation errors**: Run `python test_config.py` to diagnose configuration issues
- **Letta connection issues**: Verify your API key and agent ID are correct
- **Bluesky authentication**: Make sure your handle and password are correct and that you can log into your account
- **Tool registration fails**: Ensure your agent exists in Letta and the name matches your config
- **API method errors**: If you see `'AgentsClient' object has no attribute 'get'`, the Letta client API has changed - this should be automatically handled

### Contact
For inquiries, please contact @3fz.org on Bluesky.

Note: umbra is an experimental project and its capabilities are under continuous development.
