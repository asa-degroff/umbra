#!/usr/bin/env python3

import json
import os
import shutil
from pathlib import Path
from typing import List, Dict, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

class QueueManager:
    def __init__(self, queue_dir: str = "queue"):
        self.queue_dir = Path(queue_dir)
        self.deleted_dir = self.queue_dir / "deleted"
        self.processed_file = self.queue_dir / "processed_notifications.json"
        self.console = Console()
        
        # Create deleted directory if it doesn't exist
        self.deleted_dir.mkdir(exist_ok=True)
        
        # Load existing processed notifications
        self.processed_notifications = self._load_processed_notifications()
    
    def _load_processed_notifications(self) -> List[str]:
        """Load the list of processed notification URIs."""
        if self.processed_file.exists():
            try:
                with open(self.processed_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
    
    def _save_processed_notifications(self):
        """Save the list of processed notification URIs."""
        with open(self.processed_file, 'w') as f:
            json.dump(self.processed_notifications, f, indent=2)
    
    def _get_queue_files(self) -> List[Path]:
        """Get all JSON files in the queue directory, excluding deleted/."""
        return [f for f in self.queue_dir.glob("*.json") if f.name != "processed_notifications.json"]
    
    def _load_notification(self, file_path: Path) -> Dict[str, Any]:
        """Load a notification from a JSON file."""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            return {"error": f"Failed to load {file_path}: {e}"}
    
    def _format_notification_summary(self, notification: Dict[str, Any], file_path: Path) -> str:
        """Create a short summary of the notification for display."""
        if "error" in notification:
            return f"[red]ERROR: {notification['error']}[/red]"
        
        reason = notification.get("reason", "unknown")
        author = notification.get("author", {})
        handle = author.get("handle", "unknown")
        display_name = author.get("display_name", "")
        record = notification.get("record", {})
        text = record.get("text", "")
        
        # Truncate text if too long
        if len(text) > 100:
            text = text[:97] + "..."
        
        summary = f"[cyan]{reason}[/cyan] from [green]{handle}[/green]"
        if display_name:
            summary += f" ([yellow]{display_name}[/yellow])"
        
        if text:
            summary += f"\n  [dim]{text}[/dim]"
        
        summary += f"\n  [magenta]{file_path.name}[/magenta]"
        
        return summary
    
    def browse_queue(self, page_size: int = 10):
        """Interactive queue browser with paging and deletion."""
        files = self._get_queue_files()
        if not files:
            self.console.print("[yellow]No files in queue.[/yellow]")
            return
        
        # Sort files by modification time (newest first)
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        current_page = 0
        total_pages = (len(files) + page_size - 1) // page_size
        marked_for_deletion = set()
        
        while True:
            # Clear screen
            self.console.clear()
            
            # Calculate current page bounds
            start_idx = current_page * page_size
            end_idx = min(start_idx + page_size, len(files))
            current_files = files[start_idx:end_idx]
            
            # Create table
            table = Table(title=f"Queue Browser - Page {current_page + 1}/{total_pages}")
            table.add_column("Index", justify="center", style="cyan")
            table.add_column("Status", justify="center", style="magenta")
            table.add_column("Notification", style="white")
            
            # Add rows for current page
            for i, file_path in enumerate(current_files):
                global_index = start_idx + i
                notification = self._load_notification(file_path)
                summary = self._format_notification_summary(notification, file_path)
                
                status = "[red]DELETE[/red]" if file_path in marked_for_deletion else "[green]KEEP[/green]"
                
                table.add_row(str(global_index), status, summary)
            
            self.console.print(table)
            
            # Show statistics
            stats_text = f"Total files: {len(files)} | Marked for deletion: {len(marked_for_deletion)}"
            self.console.print(Panel(stats_text, title="Statistics"))
            
            # Show help
            help_text = """
Commands:
  [cyan]n[/cyan] - Next page        [cyan]p[/cyan] - Previous page      [cyan]q[/cyan] - Quit
  [cyan]d <idx>[/cyan] - Toggle delete flag for item at index
  [cyan]v <idx>[/cyan] - View full notification at index
  [cyan]execute[/cyan] - Execute deletions and quit
  [cyan]clear[/cyan] - Clear all delete flags
            """
            self.console.print(Panel(help_text.strip(), title="Help"))
            
            # Get user input
            try:
                command = input("\nEnter command: ").strip().lower()
                
                if command == 'q':
                    break
                elif command == 'n':
                    if current_page < total_pages - 1:
                        current_page += 1
                    else:
                        self.console.print("[yellow]Already on last page.[/yellow]")
                        input("Press Enter to continue...")
                elif command == 'p':
                    if current_page > 0:
                        current_page -= 1
                    else:
                        self.console.print("[yellow]Already on first page.[/yellow]")
                        input("Press Enter to continue...")
                elif command.startswith('d '):
                    try:
                        idx = int(command.split()[1])
                        if 0 <= idx < len(files):
                            file_path = files[idx]
                            if file_path in marked_for_deletion:
                                marked_for_deletion.remove(file_path)
                            else:
                                marked_for_deletion.add(file_path)
                        else:
                            self.console.print(f"[red]Invalid index: {idx}[/red]")
                            input("Press Enter to continue...")
                    except (ValueError, IndexError):
                        self.console.print("[red]Invalid command format. Use: d <index>[/red]")
                        input("Press Enter to continue...")
                elif command.startswith('v '):
                    try:
                        idx = int(command.split()[1])
                        if 0 <= idx < len(files):
                            self._view_notification(files[idx])
                        else:
                            self.console.print(f"[red]Invalid index: {idx}[/red]")
                            input("Press Enter to continue...")
                    except (ValueError, IndexError):
                        self.console.print("[red]Invalid command format. Use: v <index>[/red]")
                        input("Press Enter to continue...")
                elif command == 'execute':
                    if marked_for_deletion:
                        self._execute_deletions(marked_for_deletion)
                    else:
                        self.console.print("[yellow]No files marked for deletion.[/yellow]")
                        input("Press Enter to continue...")
                    break
                elif command == 'clear':
                    marked_for_deletion.clear()
                    self.console.print("[green]All delete flags cleared.[/green]")
                    input("Press Enter to continue...")
                else:
                    self.console.print("[red]Unknown command.[/red]")
                    input("Press Enter to continue...")
                    
            except KeyboardInterrupt:
                break
    
    def _view_notification(self, file_path: Path):
        """Display full notification content."""
        self.console.clear()
        notification = self._load_notification(file_path)
        
        # Display as formatted JSON
        self.console.print(Panel(
            json.dumps(notification, indent=2),
            title=f"Notification: {file_path.name}",
            expand=False
        ))
        
        input("\nPress Enter to continue...")
    
    def _execute_deletions(self, marked_files: set):
        """Move marked files to deleted/ directory and update processed_notifications.json."""
        self.console.print(f"\n[yellow]Moving {len(marked_files)} files to deleted/ directory...[/yellow]")
        
        moved_count = 0
        added_to_processed = []
        
        for file_path in marked_files:
            try:
                # Load notification to get URI
                notification = self._load_notification(file_path)
                if "uri" in notification:
                    uri = notification["uri"]
                    if uri not in self.processed_notifications:
                        self.processed_notifications.append(uri)
                        added_to_processed.append(uri)
                
                # Move file to deleted directory
                deleted_path = self.deleted_dir / file_path.name
                shutil.move(str(file_path), str(deleted_path))
                moved_count += 1
                
                self.console.print(f"[green]✓[/green] Moved {file_path.name}")
                
            except Exception as e:
                self.console.print(f"[red]✗[/red] Failed to move {file_path.name}: {e}")
        
        # Save updated processed notifications
        if added_to_processed:
            self._save_processed_notifications()
            self.console.print(f"\n[green]Added {len(added_to_processed)} URIs to processed_notifications.json[/green]")
        
        self.console.print(f"\n[green]Successfully moved {moved_count} files to deleted/ directory.[/green]")
        input("Press Enter to continue...")


def main():
    """Main entry point for the queue manager."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Interactive queue management tool")
    parser.add_argument("--queue-dir", default="queue", help="Queue directory path")
    parser.add_argument("--page-size", type=int, default=10, help="Number of items per page")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.queue_dir):
        print(f"Error: Queue directory '{args.queue_dir}' does not exist.")
        return 1
    
    manager = QueueManager(args.queue_dir)
    manager.browse_queue(args.page_size)
    
    return 0


if __name__ == "__main__":
    exit(main())