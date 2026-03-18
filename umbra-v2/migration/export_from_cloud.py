#!/usr/bin/env python3
"""Export umbra agent data from Letta Cloud for migration to self-hosted."""

import json
import sys
import os
from pathlib import Path

# Add parent's parent for config_loader access
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from letta_client import Letta
from config_loader import get_config, get_letta_config
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

console = Console()

EXPORT_DIR = Path(__file__).parent / "export"
ARCHIVAL_FILE = EXPORT_DIR / "archival_export.jsonl"
AGENT_FILE = Path.home() / "umbra" / "agents" / "umbra.af"


def export_archival_memory(client: Letta, agent_id: str):
    """Export all archival memory passages to JSONL."""
    EXPORT_DIR.mkdir(exist_ok=True)

    console.print(f"\n[bold cyan]Exporting archival memory for agent {agent_id}[/bold cyan]")

    passages = []
    cursor = None
    page_size = 1000

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed} passages"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching passages...", total=None)

        while True:
            kwargs = {"agent_id": agent_id, "limit": page_size}
            if cursor:
                kwargs["cursor"] = cursor

            batch = client.agents.passages.list(**kwargs)

            if not batch:
                break

            for passage in batch:
                record = {
                    "text": passage.text,
                    "created_at": passage.created_at.isoformat() if passage.created_at else None,
                    "metadata_": passage.metadata_ if hasattr(passage, 'metadata_') else None,
                }
                passages.append(record)

            progress.update(task, completed=len(passages))

            if len(batch) < page_size:
                break

            cursor = batch[-1].id

    # Write to JSONL
    with open(ARCHIVAL_FILE, "w", encoding="utf-8") as f:
        for record in passages:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    console.print(f"[green]Exported {len(passages)} passages to {ARCHIVAL_FILE}[/green]")
    return len(passages)


def verify_agent_file():
    """Verify the agent .af file exists."""
    if not AGENT_FILE.exists():
        console.print(f"[red]Agent file not found: {AGENT_FILE}[/red]")
        console.print("Export your agent from Letta Cloud first:")
        console.print("  client.agents.export(agent_id=...)")
        return False

    size_mb = AGENT_FILE.stat().st_size / (1024 * 1024)
    console.print(f"[green]Agent file found: {AGENT_FILE} ({size_mb:.1f} MB)[/green]")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export umbra from Letta Cloud")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent.parent.parent / "config.yaml"),
                        help="Path to config.yaml")
    args = parser.parse_args()

    get_config(args.config)
    letta_config = get_letta_config()

    # Connect to Letta Cloud
    client_params = {
        'token': letta_config['api_key'],
        'timeout': letta_config['timeout'],
    }
    if letta_config.get('base_url'):
        client_params['base_url'] = letta_config['base_url']
    client = Letta(**client_params)

    agent_id = letta_config['agent_id']

    # Verify agent exists
    try:
        agent = client.agents.retrieve(agent_id=agent_id)
        console.print(f"[green]Connected to agent: {agent.name} ({agent_id})[/green]")
    except Exception as e:
        console.print(f"[red]Failed to retrieve agent: {e}[/red]")
        sys.exit(1)

    # Verify .af file
    if not verify_agent_file():
        console.print("\n[yellow]Continuing with archival export only...[/yellow]")

    # Export archival memory
    count = export_archival_memory(client, agent_id)

    console.print(f"\n[bold green]Export complete![/bold green]")
    console.print(f"  Agent file: {AGENT_FILE}")
    console.print(f"  Archival passages: {count}")
    console.print(f"  Export directory: {EXPORT_DIR}")


if __name__ == "__main__":
    main()
