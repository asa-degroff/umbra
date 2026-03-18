#!/usr/bin/env python3
"""Import umbra agent data into self-hosted Letta server."""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from letta_client import Letta
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn

console = Console()

EXPORT_DIR = Path(__file__).parent / "export"
ARCHIVAL_FILE = EXPORT_DIR / "archival_export.jsonl"
AGENT_FILE = Path.home() / "umbra" / "agents" / "umbra.af"
CHECKPOINT_FILE = EXPORT_DIR / "import_checkpoint.json"
RESULT_FILE = EXPORT_DIR / "import_result.json"

# Self-hosted Letta config
LETTA_BASE_URL = "http://localhost:8283"
CLAUDE_PROXY_URL = "http://localhost:3456/v1"


def load_checkpoint() -> int:
    """Load the last successfully imported passage index."""
    if CHECKPOINT_FILE.exists():
        data = json.loads(CHECKPOINT_FILE.read_text())
        return data.get("last_imported_index", 0)
    return 0


def save_checkpoint(index: int):
    """Save checkpoint for resume-on-failure."""
    CHECKPOINT_FILE.write_text(json.dumps({"last_imported_index": index}))


def import_agent(client: Letta) -> str:
    """Import the agent .af file and return the new agent ID."""
    if not AGENT_FILE.exists():
        console.print(f"[red]Agent file not found: {AGENT_FILE}[/red]")
        sys.exit(1)

    console.print(f"\n[bold cyan]Importing agent from {AGENT_FILE}...[/bold cyan]")

    with open(AGENT_FILE, "rb") as f:
        agent = client.agents.import_agent_file(file=f)

    console.print(f"[green]Agent imported: {agent.name} (ID: {agent.id})[/green]")
    return agent.id


def import_archival_passages(client: Letta, agent_id: str):
    """Import archival passages with progress bar and checkpoint support."""
    if not ARCHIVAL_FILE.exists():
        console.print("[yellow]No archival export file found, skipping.[/yellow]")
        return 0

    # Count total passages
    with open(ARCHIVAL_FILE, "r", encoding="utf-8") as f:
        total = sum(1 for _ in f)

    start_index = load_checkpoint()
    if start_index > 0:
        console.print(f"[yellow]Resuming from passage {start_index}/{total}[/yellow]")

    console.print(f"\n[bold cyan]Importing {total - start_index} archival passages...[/bold cyan]")

    imported = 0
    errors = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Importing passages", total=total, completed=start_index)

        with open(ARCHIVAL_FILE, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < start_index:
                    continue

                record = json.loads(line)
                try:
                    client.agents.passages.create(
                        agent_id=agent_id,
                        text=record["text"],
                    )
                    imported += 1
                except Exception as e:
                    errors += 1
                    if errors <= 5:
                        console.print(f"[yellow]Warning at passage {i}: {e}[/yellow]")
                    elif errors == 6:
                        console.print("[yellow]Suppressing further warnings...[/yellow]")

                # Checkpoint every 50 passages
                if (i + 1) % 50 == 0:
                    save_checkpoint(i + 1)

                progress.update(task, completed=i + 1)

    save_checkpoint(total)
    console.print(f"[green]Imported {imported} passages ({errors} errors)[/green]")
    return imported


def configure_agent(client: Letta, agent_id: str):
    """Configure agent LLM and embedding settings for self-hosted."""
    console.print(f"\n[bold cyan]Configuring agent for self-hosted...[/bold cyan]")

    try:
        from letta_client import LlmConfig, EmbeddingConfig

        client.agents.modify(
            agent_id=agent_id,
            llm_config=LlmConfig(
                model="openai/claude-opus-4",
                model_endpoint_type="openai",
                model_endpoint=CLAUDE_PROXY_URL,
                context_window=200000,
            ),
            embedding_config=EmbeddingConfig(
                embedding_model="ollama/qwen3-embedding:0.6b",
                embedding_endpoint_type="ollama",
                embedding_endpoint="http://localhost:11434",
                embedding_dim=1024,
            ),
        )
        console.print("[green]LLM and embedding config updated[/green]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not set LLM/embedding config: {e}[/yellow]")
        console.print("[yellow]You may need to configure this manually in Letta.[/yellow]")


def set_tool_env_vars(client: Letta, agent_id: str):
    """Set environment variables on the agent for tool execution."""
    console.print(f"\n[bold cyan]Setting tool environment variables...[/bold cyan]")

    # Read from parent config.yaml
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from config_loader import get_config, get_bluesky_config, get_r2_config, get_image_generation_config
    get_config(str(Path(__file__).resolve().parent.parent.parent / "config.yaml"))

    bsky_config = get_bluesky_config()
    r2_config = get_r2_config()
    image_config = get_image_generation_config()

    env_vars = {
        'BSKY_USERNAME': bsky_config['username'],
        'BSKY_PASSWORD': bsky_config['password'],
        'PDS_URI': bsky_config['pds_uri'],
    }

    if r2_config.get('account_id') and r2_config.get('access_key_id'):
        env_vars.update({
            'R2_ACCOUNT_ID': r2_config['account_id'],
            'R2_ACCESS_KEY_ID': r2_config['access_key_id'],
            'R2_SECRET_ACCESS_KEY': r2_config['secret_access_key'],
            'R2_BUCKET_NAME': r2_config['bucket_name'],
        })

    if image_config.get('replicate_api_token'):
        env_vars['REPLICATE_API_TOKEN'] = image_config['replicate_api_token']

    try:
        client.agents.modify(
            agent_id=agent_id,
            tool_exec_environment_variables=env_vars,
        )
        console.print(f"[green]Set {len(env_vars)} environment variables[/green]")
    except Exception as e:
        console.print(f"[yellow]Warning: Failed to set env vars: {e}[/yellow]")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Import umbra into self-hosted Letta")
    parser.add_argument("--base-url", default=LETTA_BASE_URL, help="Letta server URL")
    parser.add_argument("--skip-archival", action="store_true", help="Skip archival import")
    parser.add_argument("--agent-id", help="Use existing agent instead of importing")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent.parent.parent / "config.yaml"),
                        help="Path to V1 config.yaml for reading credentials")
    args = parser.parse_args()

    # Connect to self-hosted Letta
    client = Letta(base_url=args.base_url, timeout=600)
    console.print(f"[green]Connected to Letta at {args.base_url}[/green]")

    # Import or use existing agent
    if args.agent_id:
        agent_id = args.agent_id
        console.print(f"[cyan]Using existing agent: {agent_id}[/cyan]")
    else:
        agent_id = import_agent(client)

    # Import archival memory
    if not args.skip_archival:
        import_archival_passages(client, agent_id)

    # Configure for self-hosted
    configure_agent(client, agent_id)

    # Set tool env vars
    set_tool_env_vars(client, agent_id)

    # Save result
    result = {"agent_id": agent_id, "base_url": args.base_url}
    RESULT_FILE.write_text(json.dumps(result, indent=2))

    console.print(f"\n[bold green]Import complete![/bold green]")
    console.print(f"  New agent ID: {agent_id}")
    console.print(f"  Update your config.yaml with:")
    console.print(f"    letta:")
    console.print(f"      base_url: \"{args.base_url}\"")
    console.print(f"      agent_id: \"{agent_id}\"")


if __name__ == "__main__":
    main()
