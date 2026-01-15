#!/usr/bin/env python3
"""Scheduled task management utilities for umbra."""
import argparse
import time
import random
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from notification_db import NotificationDB
from scheduled_prompts import TASK_CONFIGS, calculate_next_random_time
from config_loader import get_queue_config

console = Console()


def get_db() -> NotificationDB:
    """Get NotificationDB instance using config from config.yaml."""
    queue_config = get_queue_config()
    db_path = queue_config['db_path']
    return NotificationDB(db_path=db_path)


def format_time_until(timestamp_iso: str) -> str:
    """Format time until a timestamp as a human-readable string."""
    try:
        target = datetime.fromisoformat(timestamp_iso)
        now = datetime.now()
        delta = target - now

        if delta.total_seconds() < 0:
            return "[red]overdue[/red]"

        hours = delta.total_seconds() / 3600
        if hours < 1:
            minutes = delta.total_seconds() / 60
            return f"{minutes:.0f}m"
        elif hours < 24:
            return f"{hours:.1f}h"
        else:
            days = hours / 24
            return f"{days:.1f}d"
    except:
        return "?"


def list_tasks():
    """List all scheduled tasks with their current state."""
    db = get_db()
    tasks = db.get_all_scheduled_tasks()

    if not tasks:
        console.print("[yellow]No scheduled tasks found in database[/yellow]")
        return

    table = Table(title=f"Scheduled Tasks ({len(tasks)} total)")
    table.add_column("Task", style="cyan", width=25)
    table.add_column("Enabled", style="green", width=8)
    table.add_column("Type", width=12)
    table.add_column("Interval/Window", width=15)
    table.add_column("Next Run", width=22)
    table.add_column("Until", style="yellow", width=10)
    table.add_column("Last Run", width=22)

    for task in sorted(tasks, key=lambda t: t['task_name']):
        task_name = task['task_name']
        enabled = "[green]✓[/green]" if task['enabled'] else "[red]✗[/red]"

        # Determine type
        if task['is_random_window']:
            task_type = "random"
            interval = f"{task['window_seconds'] / 3600:.0f}h window" if task['window_seconds'] else "?"
        else:
            task_type = "interval"
            interval = f"{task['interval_seconds'] / 3600:.0f}h" if task['interval_seconds'] else "?"

        # Format timestamps
        next_run = task['next_run_at'][:19] if task['next_run_at'] else "-"
        until = format_time_until(task['next_run_at']) if task['next_run_at'] else "-"
        last_run = task['last_run_at'][:19] if task['last_run_at'] else "-"

        # Get emoji from config
        config = TASK_CONFIGS.get(task_name, {})
        emoji = config.get('emoji', '📅')

        table.add_row(
            f"{emoji} {task_name}",
            enabled,
            task_type,
            interval,
            next_run,
            until,
            last_run
        )

    console.print(table)

    # Show tasks in TASK_CONFIGS that aren't in the database
    db_task_names = {t['task_name'] for t in tasks}
    config_task_names = set(TASK_CONFIGS.keys())
    missing = config_task_names - db_task_names
    if missing:
        console.print(f"\n[yellow]Tasks in config but not in database: {', '.join(sorted(missing))}[/yellow]")


def clear_tasks(force: bool = False):
    """Clear all scheduled tasks from the database."""
    db = get_db()
    tasks = db.get_all_scheduled_tasks()

    if not tasks:
        console.print("[yellow]No scheduled tasks to clear[/yellow]")
        return

    console.print(f"[yellow]Found {len(tasks)} scheduled tasks to clear:[/yellow]")
    for task in tasks:
        emoji = TASK_CONFIGS.get(task['task_name'], {}).get('emoji', '📅')
        console.print(f"  {emoji} {task['task_name']}")

    if not force:
        if not Confirm.ask("\nProceed with clearing all scheduled tasks?"):
            console.print("[dim]Cancelled[/dim]")
            return

    # Delete all tasks
    deleted = 0
    for task in tasks:
        if db.delete_scheduled_task(task['task_name']):
            deleted += 1

    console.print(f"[green]Cleared {deleted} scheduled tasks[/green]")


def regenerate_tasks(force: bool = False, tasks_filter: list = None):
    """Regenerate scheduled tasks using time intervals from TASK_CONFIGS."""
    db = get_db()

    # Determine which tasks to regenerate
    if tasks_filter:
        # Validate task names
        invalid = set(tasks_filter) - set(TASK_CONFIGS.keys())
        if invalid:
            console.print(f"[red]Unknown task names: {', '.join(invalid)}[/red]")
            console.print(f"[dim]Valid tasks: {', '.join(TASK_CONFIGS.keys())}[/dim]")
            return
        task_names = tasks_filter
    else:
        task_names = list(TASK_CONFIGS.keys())

    console.print(f"[yellow]Will regenerate {len(task_names)} scheduled tasks:[/yellow]")
    for name in task_names:
        config = TASK_CONFIGS[name]
        emoji = config.get('emoji', '📅')
        if config['is_random_window']:
            hours = config['window_seconds'] / 3600
            console.print(f"  {emoji} {name} (random within {hours:.0f}h)")
        else:
            hours = config['interval_seconds'] / 3600
            console.print(f"  {emoji} {name} (every {hours:.0f}h)")

    if not force:
        if not Confirm.ask("\nProceed with regenerating these tasks?"):
            console.print("[dim]Cancelled[/dim]")
            return

    # Regenerate each task
    current_time = time.time()
    regenerated = 0

    for task_name in task_names:
        config = TASK_CONFIGS[task_name]

        # Calculate new schedule
        if config['is_random_window'] and config['window_seconds']:
            next_timestamp = calculate_next_random_time(config['window_seconds'])
        elif config['interval_seconds']:
            next_timestamp = current_time + config['interval_seconds']
        else:
            console.print(f"[red]Task {task_name} has no valid scheduling configuration[/red]")
            continue

        next_run_at_iso = datetime.fromtimestamp(next_timestamp).isoformat()

        # Upsert task
        success = db.upsert_scheduled_task(
            task_name=task_name,
            next_run_at=next_run_at_iso,
            interval_seconds=config['interval_seconds'],
            is_random_window=config['is_random_window'],
            window_seconds=config['window_seconds'],
            enabled=config['enabled']
        )

        if success:
            regenerated += 1
            hours_until = (next_timestamp - current_time) / 3600
            emoji = config.get('emoji', '📅')
            next_dt = datetime.fromtimestamp(next_timestamp)
            console.print(f"[green]✓[/green] {emoji} {task_name}: {next_dt.strftime('%Y-%m-%d %H:%M:%S')} ({hours_until:.1f}h from now)")
        else:
            console.print(f"[red]✗ Failed to regenerate {task_name}[/red]")

    console.print(f"\n[green]Regenerated {regenerated}/{len(task_names)} scheduled tasks[/green]")


def reset_tasks(force: bool = False, tasks_filter: list = None):
    """Clear and regenerate scheduled tasks (convenience command)."""
    if tasks_filter:
        # Only clear specified tasks
        db = get_db()
        console.print(f"[yellow]Resetting {len(tasks_filter)} tasks...[/yellow]")
        for task_name in tasks_filter:
            if task_name in TASK_CONFIGS:
                db.delete_scheduled_task(task_name)
    else:
        clear_tasks(force=True)

    regenerate_tasks(force=True, tasks_filter=tasks_filter)


def main():
    parser = argparse.ArgumentParser(
        description="Manage scheduled tasks for umbra",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list                     # Show all scheduled tasks
  %(prog)s clear                    # Clear all tasks (with confirmation)
  %(prog)s clear --force            # Clear all tasks without confirmation
  %(prog)s regenerate               # Regenerate all tasks with new times
  %(prog)s regenerate --tasks synthesis feed_engagement
                                    # Regenerate specific tasks only
  %(prog)s reset                    # Clear and regenerate all tasks
  %(prog)s reset --tasks synthesis  # Reset only specific tasks
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list command
    list_parser = subparsers.add_parser("list", help="List all scheduled tasks")

    # clear command
    clear_parser = subparsers.add_parser("clear", help="Clear all scheduled tasks from database")
    clear_parser.add_argument("--force", "-f", action="store_true",
                              help="Skip confirmation prompt")

    # regenerate command
    regen_parser = subparsers.add_parser("regenerate", help="Regenerate scheduled tasks with new times")
    regen_parser.add_argument("--force", "-f", action="store_true",
                              help="Skip confirmation prompt")
    regen_parser.add_argument("--tasks", "-t", nargs="+", metavar="TASK",
                              help="Only regenerate specific tasks")

    # reset command (clear + regenerate)
    reset_parser = subparsers.add_parser("reset", help="Clear and regenerate tasks (clear + regenerate)")
    reset_parser.add_argument("--force", "-f", action="store_true",
                              help="Skip confirmation prompt")
    reset_parser.add_argument("--tasks", "-t", nargs="+", metavar="TASK",
                              help="Only reset specific tasks")

    args = parser.parse_args()

    if args.command == "list":
        list_tasks()
    elif args.command == "clear":
        clear_tasks(force=args.force)
    elif args.command == "regenerate":
        regenerate_tasks(force=args.force, tasks_filter=args.tasks)
    elif args.command == "reset":
        reset_tasks(force=args.force, tasks_filter=args.tasks)
    else:
        # Default to list if no command specified
        list_tasks()


if __name__ == "__main__":
    main()
