#!/usr/bin/env python3
"""Register all Void tools with a Letta agent."""
import os
import sys
import logging
from typing import List
from dotenv import load_dotenv
from letta_client import Letta
from rich.console import Console
from rich.table import Table

# Import standalone functions and their schemas
from tools.search import search_bluesky_posts, SearchArgs
from tools.post import create_new_bluesky_post, PostArgs
from tools.feed import get_bluesky_feed, FeedArgs
from tools.blocks import attach_user_blocks, detach_user_blocks, AttachUserBlocksArgs, DetachUserBlocksArgs
from tools.reply import bluesky_reply, ReplyArgs

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()


# Tool configurations: function paired with its args_schema and metadata
TOOL_CONFIGS = [
    {
        "func": search_bluesky_posts,
        "args_schema": SearchArgs,
        "description": "Search for posts on Bluesky matching the given criteria",
        "tags": ["bluesky", "search", "posts"]
    },
    {
        "func": create_new_bluesky_post,
        "args_schema": PostArgs,
        "description": "Create a new Bluesky post or thread",
        "tags": ["bluesky", "post", "create", "thread"]
    },
    {
        "func": get_bluesky_feed,
        "args_schema": FeedArgs,
        "description": "Retrieve a Bluesky feed (home timeline or custom feed)",
        "tags": ["bluesky", "feed", "timeline"]
    },
    {
        "func": attach_user_blocks,
        "args_schema": AttachUserBlocksArgs,
        "description": "Attach user-specific memory blocks to the agent. Creates blocks if they don't exist.",
        "tags": ["memory", "blocks", "user"]
    },
    {
        "func": detach_user_blocks,
        "args_schema": DetachUserBlocksArgs,
        "description": "Detach user-specific memory blocks from the agent. Blocks are preserved for later use.",
        "tags": ["memory", "blocks", "user"]
    },
    {
        "func": bluesky_reply,
        "args_schema": ReplyArgs,
        "description": "Reply indicator for the Letta agent (1-4 messages, each max 300 chars). Creates threaded replies.",
        "tags": ["bluesky", "reply", "response"]
    },
]


def register_tools(agent_name: str = "void", tools: List[str] = None):
    """Register tools with a Letta agent.

    Args:
        agent_name: Name of the agent to attach tools to
        tools: List of tool names to register. If None, registers all tools.
    """
    try:
        # Initialize Letta client with API key
        client = Letta(token=os.environ["LETTA_API_KEY"])

        # Find the agent
        agents = client.agents.list()
        agent = None
        for a in agents:
            if a.name == agent_name:
                agent = a
                break

        if not agent:
            console.print(f"[red]Error: Agent '{agent_name}' not found[/red]")
            console.print("\nAvailable agents:")
            for a in agents:
                console.print(f"  - {a.name}")
            return

        # Filter tools if specific ones requested
        tools_to_register = TOOL_CONFIGS
        if tools:
            tools_to_register = [t for t in TOOL_CONFIGS if t["func"].__name__ in tools]
            if len(tools_to_register) != len(tools):
                missing = set(tools) - {t["func"].__name__ for t in tools_to_register}
                console.print(f"[yellow]Warning: Unknown tools: {missing}[/yellow]")

        # Create results table
        table = Table(title=f"Tool Registration for Agent '{agent_name}'")
        table.add_column("Tool", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Description")

        # Register each tool
        for tool_config in tools_to_register:
            func = tool_config["func"]
            tool_name = func.__name__

            try:
                # Create or update the tool using the standalone function
                created_tool = client.tools.upsert_from_function(
                    func=func,
                    args_schema=tool_config["args_schema"],
                    tags=tool_config["tags"]
                )

                # Get current agent tools
                current_tools = client.agents.tools.list(agent_id=str(agent.id))
                tool_names = [t.name for t in current_tools]

                # Check if already attached
                if created_tool.name in tool_names:
                    table.add_row(tool_name, "Already Attached", tool_config["description"])
                else:
                    # Attach to agent
                    client.agents.tools.attach(
                        agent_id=str(agent.id),
                        tool_id=str(created_tool.id)
                    )
                    table.add_row(tool_name, "✓ Attached", tool_config["description"])

            except Exception as e:
                table.add_row(tool_name, f"✗ Error: {str(e)}", tool_config["description"])
                logger.error(f"Error registering tool {tool_name}: {e}")

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        logger.error(f"Fatal error: {e}")


def list_available_tools():
    """List all available tools."""
    table = Table(title="Available Void Tools")
    table.add_column("Tool Name", style="cyan")
    table.add_column("Description")
    table.add_column("Tags", style="dim")

    for tool_config in TOOL_CONFIGS:
        table.add_row(
            tool_config["func"].__name__,
            tool_config["description"],
            ", ".join(tool_config["tags"])
        )

    console.print(table)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Register Void tools with a Letta agent")
    parser.add_argument("agent", nargs="?", default="void", help="Agent name (default: void)")
    parser.add_argument("--tools", nargs="+", help="Specific tools to register (default: all)")
    parser.add_argument("--list", action="store_true", help="List available tools")

    args = parser.parse_args()

    if args.list:
        list_available_tools()
    else:
        console.print(f"\n[bold]Registering tools for agent: {args.agent}[/bold]\n")
        register_tools(args.agent, args.tools)
