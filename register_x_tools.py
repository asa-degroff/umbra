#!/usr/bin/env python3
"""Register X-specific tools with a Letta agent."""
import logging
from typing import List
from letta_client import Letta
from rich.console import Console
from rich.table import Table
from x import get_x_letta_config

# Import standalone functions and their schemas
from tools.blocks import (
    attach_x_user_blocks, detach_x_user_blocks,
    AttachXUserBlocksArgs, DetachXUserBlocksArgs
)
from tools.halt import halt_activity, HaltArgs
from tools.ignore import ignore_notification, IgnoreNotificationArgs
from tools.whitewind import create_whitewind_blog_post, WhitewindPostArgs
from tools.ack import annotate_ack, AnnotateAckArgs
from tools.webpage import fetch_webpage, WebpageArgs

# Import X thread tool
from tools.x_thread import add_post_to_x_thread, XThreadPostArgs

# Import X post tool
from tools.x_post import post_to_x, PostToXArgs

# Import X search tool
from tools.search_x import search_x_posts, SearchXArgs

letta_config = get_x_letta_config()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()

# X-specific tool configurations
X_TOOL_CONFIGS = [
    # Keep these core tools
    {
        "func": halt_activity,
        "args_schema": HaltArgs,
        "description": "Signal to halt all bot activity and terminate X bot",
        "tags": ["control", "halt", "terminate"]
    },
    {
        "func": ignore_notification,
        "args_schema": IgnoreNotificationArgs,
        "description": "Explicitly ignore an X notification without replying",
        "tags": ["notification", "ignore", "control", "bot"]
    },
    {
        "func": annotate_ack,
        "args_schema": AnnotateAckArgs,
        "description": "Add a note to the acknowledgment record for the current X interaction",
        "tags": ["acknowledgment", "note", "annotation", "metadata"]
    },
    {
        "func": create_whitewind_blog_post,
        "args_schema": WhitewindPostArgs,
        "description": "Create a blog post on Whitewind with markdown support",
        "tags": ["whitewind", "blog", "post", "markdown"]
    },
    {
        "func": fetch_webpage,
        "args_schema": WebpageArgs,
        "description": "Fetch a webpage and convert it to markdown/text format using Jina AI reader",
        "tags": ["web", "fetch", "webpage", "markdown", "jina"]
    },
    
    # X user block management tools
    {
        "func": attach_x_user_blocks,
        "args_schema": AttachXUserBlocksArgs,
        "description": "Attach X user-specific memory blocks to the agent. Creates blocks if they don't exist.",
        "tags": ["memory", "blocks", "user", "x", "twitter"]
    },
    {
        "func": detach_x_user_blocks,
        "args_schema": DetachXUserBlocksArgs,
        "description": "Detach X user-specific memory blocks from the agent. Blocks are preserved for later use.",
        "tags": ["memory", "blocks", "user", "x", "twitter"]
    },
    
    # X thread tool
    {
        "func": add_post_to_x_thread,
        "args_schema": XThreadPostArgs,
        "description": "Add a single post to the current X reply thread atomically",
        "tags": ["x", "twitter", "reply", "thread", "atomic"]
    },
    
    # X post tool
    {
        "func": post_to_x,
        "args_schema": PostToXArgs,
        "description": "Create a new standalone post on X (Twitter)",
        "tags": ["x", "twitter", "post", "create", "standalone"]
    },
    
    # X search tool
    {
        "func": search_x_posts,
        "args_schema": SearchXArgs,
        "description": "Get recent posts from a specific X (Twitter) user",
        "tags": ["x", "twitter", "search", "posts", "user"]
    }
]

def register_x_tools(agent_id: str = None, tools: List[str] = None):
    """Register X-specific tools with a Letta agent.

    Args:
        agent_id: ID of the agent to attach tools to. If None, uses config default.
        tools: List of tool names to register. If None, registers all tools.
    """
    # Use agent ID from config if not provided
    if agent_id is None:
        agent_id = letta_config['agent_id']
    
    try:
        # Initialize Letta client with API key and base_url from config
        client_params = {
            'token': letta_config['api_key'],
            'timeout': letta_config['timeout']
        }
        if letta_config.get('base_url'):
            client_params['base_url'] = letta_config['base_url']
        client = Letta(**client_params)

        # Get the agent by ID
        try:
            agent = client.agents.retrieve(agent_id=agent_id)
        except Exception as e:
            console.print(f"[red]Error: Agent '{agent_id}' not found[/red]")
            console.print(f"Error details: {e}")
            return

        # Filter tools if specific ones requested
        tools_to_register = X_TOOL_CONFIGS
        if tools:
            tools_to_register = [t for t in X_TOOL_CONFIGS if t["func"] and t["func"].__name__ in tools]
            if len(tools_to_register) != len(tools):
                registered_names = {t["func"].__name__ for t in tools_to_register if t["func"]}
                missing = set(tools) - registered_names
                console.print(f"[yellow]Warning: Unknown tools: {missing}[/yellow]")

        # Create results table
        table = Table(title=f"X Tool Registration for Agent '{agent.name}' ({agent_id})")
        table.add_column("Tool", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Description")

        # Register each tool
        for tool_config in tools_to_register:
            func = tool_config["func"]
            if not func:
                continue
                
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


def list_available_x_tools():
    """List all available X tools."""
    table = Table(title="Available X Tools")
    table.add_column("Tool Name", style="cyan")
    table.add_column("Description")
    table.add_column("Tags", style="dim")

    for tool_config in X_TOOL_CONFIGS:
        if tool_config["func"]:
            table.add_row(
                tool_config["func"].__name__,
                tool_config["description"],
                ", ".join(tool_config["tags"])
            )

    console.print(table)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Register X tools with a Letta agent")
    parser.add_argument("--agent-id", help=f"Agent ID (default: from config)")
    parser.add_argument("--tools", nargs="+", help="Specific tools to register (default: all)")
    parser.add_argument("--list", action="store_true", help="List available tools")

    args = parser.parse_args()

    if args.list:
        list_available_x_tools()
    else:
        # Use config default if no agent specified
        agent_id = args.agent_id if args.agent_id else letta_config['agent_id']
        console.print(f"\n[bold]Registering X tools for agent: {agent_id}[/bold]\n")
        register_x_tools(agent_id, args.tools)