#!/usr/bin/env python3
"""Verify migration from Letta Cloud to self-hosted."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from letta_client import Letta
from rich.console import Console
from rich.table import Table

console = Console()

EXPORT_DIR = Path(__file__).parent / "export"
ARCHIVAL_FILE = EXPORT_DIR / "archival_export.jsonl"
RESULT_FILE = EXPORT_DIR / "import_result.json"

EXPECTED_BLOCKS = ["zeitgeist", "umbra-persona", "umbra-humans"]


def check(name: str, passed: bool, detail: str = ""):
    icon = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
    msg = f"  {icon} {name}"
    if detail:
        msg += f" — {detail}"
    console.print(msg)
    return passed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Verify umbra migration")
    parser.add_argument("--base-url", default="http://localhost:8283", help="Letta server URL")
    parser.add_argument("--agent-id", help="Agent ID to verify (reads from import_result.json if not given)")
    args = parser.parse_args()

    # Get agent ID
    if args.agent_id:
        agent_id = args.agent_id
    elif RESULT_FILE.exists():
        result = json.loads(RESULT_FILE.read_text())
        agent_id = result["agent_id"]
        args.base_url = result.get("base_url", args.base_url)
    else:
        console.print("[red]No agent ID provided and no import_result.json found.[/red]")
        sys.exit(1)

    client = Letta(base_url=args.base_url, timeout=120)
    console.print(f"[bold cyan]Verifying migration: {agent_id} @ {args.base_url}[/bold cyan]\n")

    all_passed = True

    # 1. Agent retrievable
    try:
        agent = client.agents.retrieve(agent_id=agent_id)
        all_passed &= check("Agent retrievable", True, f"name={agent.name}")
    except Exception as e:
        all_passed &= check("Agent retrievable", False, str(e))
        console.print("[red]Cannot continue without agent.[/red]")
        sys.exit(1)

    # 2. Core memory blocks
    try:
        blocks = client.agents.blocks.list(agent_id=agent_id)
        block_labels = [b.label for b in blocks]
        for label in EXPECTED_BLOCKS:
            present = label in block_labels
            if present:
                block = next(b for b in blocks if b.label == label)
                non_empty = bool(block.value and block.value.strip())
                all_passed &= check(f"Block '{label}'", non_empty,
                                    f"{len(block.value)} chars" if non_empty else "EMPTY")
            else:
                all_passed &= check(f"Block '{label}'", False, "missing")
    except Exception as e:
        all_passed &= check("Core memory blocks", False, str(e))

    # 3. Archival passage count
    try:
        # Count passages on server
        server_passages = []
        cursor = None
        while True:
            kwargs = {"agent_id": agent_id, "limit": 1000}
            if cursor:
                kwargs["cursor"] = cursor
            batch = client.agents.passages.list(**kwargs)
            if not batch:
                break
            server_passages.extend(batch)
            if len(batch) < 1000:
                break
            cursor = batch[-1].id

        server_count = len(server_passages)

        # Count exported passages
        if ARCHIVAL_FILE.exists():
            with open(ARCHIVAL_FILE) as f:
                export_count = sum(1 for _ in f)
            match = server_count >= export_count
            all_passed &= check("Archival passages", match,
                                f"server={server_count}, export={export_count}")
        else:
            check("Archival passages", True, f"server={server_count} (no export to compare)")
    except Exception as e:
        all_passed &= check("Archival passages", False, str(e))

    # 4. Tools attached
    try:
        tools = client.agents.tools.list(agent_id=agent_id)
        tool_names = [t.name for t in tools]
        has_tools = len(tools) > 0
        all_passed &= check("Tools attached", has_tools,
                            f"{len(tools)} tools: {', '.join(tool_names[:5])}{'...' if len(tools) > 5 else ''}")
    except Exception as e:
        all_passed &= check("Tools attached", False, str(e))

    # 5. Test message
    try:
        console.print("\n  [dim]Sending test message...[/dim]")
        response = client.agents.messages.create(
            agent_id=agent_id,
            messages=[{
                "role": "user",
                "content": "[SYSTEM] Migration verification test. Respond with a single short sentence confirming you're operational."
            }],
        )
        # Check we got an assistant response
        got_response = any(
            hasattr(msg, 'content') and msg.content
            for msg in response.messages
            if hasattr(msg, 'role') and msg.role == 'assistant'
        )
        if not got_response:
            # Try checking for assistant_message type
            got_response = any(
                hasattr(msg, 'assistant_message') or msg.__class__.__name__ == 'AssistantMessage'
                for msg in response.messages
            )
        all_passed &= check("Test message", got_response, "agent responded")
    except Exception as e:
        all_passed &= check("Test message", False, str(e))

    # Summary
    console.print()
    if all_passed:
        console.print("[bold green]All checks passed! Migration verified.[/bold green]")
    else:
        console.print("[bold red]Some checks failed. Review above.[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
