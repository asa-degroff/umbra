#!/usr/bin/env python3
"""Test script to verify thread retrieval captures all posts in a multi-post thread."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from atproto_client import Client
import bsky_utils
from rich.console import Console
from rich.tree import Tree
from rich.panel import Panel

# Load environment
load_dotenv()

console = Console()

def count_posts_in_thread(thread_data, level=0):
    """Recursively count all posts in a thread structure."""
    count = 0

    if not thread_data:
        return count

    # Count the current post if it exists
    if hasattr(thread_data, 'post') or (isinstance(thread_data, dict) and 'post' in thread_data):
        count += 1

    # Recursively count replies
    replies = None
    if hasattr(thread_data, 'replies'):
        replies = thread_data.replies
    elif isinstance(thread_data, dict) and 'replies' in thread_data:
        replies = thread_data['replies']

    if replies:
        for reply in replies:
            count += count_posts_in_thread(reply, level + 1)

    return count


def build_thread_tree(thread_data, tree=None, level=0):
    """Recursively build a visual tree of the thread structure."""
    if not thread_data:
        return tree

    # Extract post data
    post = None
    if hasattr(thread_data, 'post'):
        post = thread_data.post
    elif isinstance(thread_data, dict) and 'post' in thread_data:
        post = thread_data['post']

    if post:
        # Get post details
        if hasattr(post, 'record'):
            text = post.record.text if hasattr(post.record, 'text') else 'No text'
        elif isinstance(post, dict) and 'record' in post:
            text = post['record'].get('text', 'No text')
        else:
            text = 'No text'

        # Truncate long posts
        display_text = text[:100] + "..." if len(text) > 100 else text

        # Get author
        author = "unknown"
        if hasattr(post, 'author'):
            author = post.author.handle if hasattr(post.author, 'handle') else 'unknown'
        elif isinstance(post, dict) and 'author' in post:
            author = post['author'].get('handle', 'unknown')

        label = f"@{author}: {display_text}"

        if tree is None:
            tree = Tree(f"[bold blue]{label}[/bold blue]")
        else:
            tree = tree.add(f"[cyan]{label}[/cyan]")

    # Add replies
    replies = None
    if hasattr(thread_data, 'replies'):
        replies = thread_data.replies
    elif isinstance(thread_data, dict) and 'replies' in thread_data:
        replies = thread_data['replies']

    if replies:
        for reply in replies:
            build_thread_tree(reply, tree, level + 1)

    return tree


def test_thread_retrieval():
    """Test retrieving a multi-post thread from Bluesky."""

    console.print("\n[bold yellow]Thread Retrieval Test[/bold yellow]\n")

    # Test post metadata
    test_uri = "at://did:plc:rr3zpoloyldj7kupehwfybqr/app.bsky.feed.post/3m5zjzhlj2c2p"
    test_cid = "bafyreidb25r2253qun66c3f3ehp7b4pc6u54s4zol7i7xgrp7h3j25m74y"

    console.print(f"[cyan]Test Post URI:[/cyan] {test_uri}")
    console.print(f"[cyan]Test Post CID:[/cyan] {test_cid}\n")

    # Get credentials
    username = os.getenv('BSKY_USERNAME')
    password = os.getenv('BSKY_PASSWORD')

    if not username or not password:
        console.print("[red]Error: BSKY_USERNAME and BSKY_PASSWORD must be set in .env[/red]")
        sys.exit(1)

    console.print(f"[green]✓[/green] Connecting to Bluesky as {username}...")

    # Create client and login
    client = Client()
    try:
        client.login(username, password)
        console.print("[green]✓[/green] Successfully logged in\n")
    except Exception as e:
        console.print(f"[red]✗ Login failed: {e}[/red]")
        sys.exit(1)

    # Test different depth values
    depths = [10, 100, 1000]

    for depth in depths:
        console.print(f"[bold yellow]Testing with depth={depth}[/bold yellow]")
        console.print("─" * 60)

        try:
            # Fetch thread
            console.print(f"[cyan]Fetching thread with depth={depth}...[/cyan]")
            thread = bsky_utils.get_post_thread(client, test_uri, parent_height=80, depth=depth)

            if not thread:
                console.print("[red]✗ Failed to fetch thread (returned None)[/red]\n")
                continue

            # Count posts
            total_posts = count_posts_in_thread(thread.thread)
            console.print(f"[green]✓[/green] Thread fetched successfully")
            console.print(f"[green]✓[/green] Total posts in thread: [bold]{total_posts}[/bold]\n")

            # Build and display tree
            tree = build_thread_tree(thread.thread)
            if tree:
                console.print(Panel(tree, title="Thread Structure", border_style="green"))

            # Convert to YAML to see what the agent would see
            console.print("\n[cyan]Converting to YAML (as agent sees it)...[/cyan]")
            thread_yaml = bsky_utils.thread_to_yaml_string(thread)
            yaml_lines = thread_yaml.split('\n')
            console.print(f"[green]✓[/green] YAML output: {len(yaml_lines)} lines, {len(thread_yaml)} chars")

            # Show first few lines of YAML
            console.print("\n[dim]First 20 lines of YAML:[/dim]")
            for i, line in enumerate(yaml_lines[:20], 1):
                console.print(f"[dim]{i:3d}[/dim] {line}")
            if len(yaml_lines) > 20:
                console.print(f"[dim]... ({len(yaml_lines) - 20} more lines)[/dim]")

            console.print("\n")

        except Exception as e:
            console.print(f"[red]✗ Error fetching thread: {e}[/red]\n")

    console.print("[bold green]Test completed![/bold green]\n")


if __name__ == "__main__":
    test_thread_retrieval()
