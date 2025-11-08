#!/usr/bin/env python3
"""
Test script for Claude Code integration.

This script tests:
1. R2 connection and authentication
2. Bucket access and file operations
3. End-to-end request/response flow (if poller is running)

Usage:
    python test_claude_code_tool.py [--config CONFIG_FILE]
"""

import os
import sys
import json
import time
import uuid
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import get_r2_config, get_config
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def test_r2_connection(r2_config):
    """Test R2 connection and credentials."""
    console.print("\n[bold cyan]Test 1: R2 Connection[/bold cyan]")

    try:
        import boto3
        from botocore.exceptions import ClientError

        # Check if credentials are configured
        if not all([
            r2_config['account_id'],
            r2_config['access_key_id'],
            r2_config['secret_access_key']
        ]):
            console.print("[red]✗ R2 credentials not configured[/red]")
            console.print("  Please set R2 credentials in config.yaml or environment variables")
            return False

        # Create S3 client for R2
        r2_endpoint = f"https://{r2_config['account_id']}.r2.cloudflarestorage.com"
        s3_client = boto3.client(
            's3',
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_config['access_key_id'],
            aws_secret_access_key=r2_config['secret_access_key'],
            region_name='auto'
        )

        # Test bucket access
        bucket_name = r2_config['bucket_name']
        console.print(f"  Testing access to bucket: [cyan]{bucket_name}[/cyan]")

        try:
            s3_client.head_bucket(Bucket=bucket_name)
            console.print(f"[green]✓ Successfully connected to R2 bucket: {bucket_name}[/green]")
            return s3_client
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == '404':
                console.print(f"[red]✗ Bucket '{bucket_name}' does not exist[/red]")
                console.print(f"  Please create the bucket in Cloudflare R2 dashboard")
            elif error_code == '403':
                console.print(f"[red]✗ Access denied to bucket '{bucket_name}'[/red]")
                console.print(f"  Please check your R2 API token permissions")
            else:
                console.print(f"[red]✗ Error accessing bucket: {error_code} - {e}[/red]")
            return False

    except ImportError:
        console.print("[red]✗ boto3 library not installed[/red]")
        console.print("  Install with: pip install boto3")
        return False
    except Exception as e:
        console.print(f"[red]✗ Unexpected error: {e}[/red]")
        return False


def test_file_operations(s3_client, bucket_name):
    """Test file upload and download operations."""
    console.print("\n[bold cyan]Test 2: File Operations[/bold cyan]")

    try:
        # Create test file
        test_id = str(uuid.uuid4())[:8]
        test_key = f"claude-code-requests/test_{test_id}.json"
        test_data = {
            "test": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "This is a test file"
        }

        # Upload test file
        console.print(f"  Uploading test file: [cyan]{test_key}[/cyan]")
        s3_client.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=json.dumps(test_data, indent=2),
            ContentType='application/json'
        )
        console.print("[green]✓ Upload successful[/green]")

        # Download test file
        console.print("  Downloading test file...")
        response = s3_client.get_object(Bucket=bucket_name, Key=test_key)
        downloaded_data = json.loads(response['Body'].read())

        if downloaded_data == test_data:
            console.print("[green]✓ Download successful and data matches[/green]")
        else:
            console.print("[red]✗ Downloaded data does not match[/red]")
            return False

        # List files
        console.print("  Listing files in claude-code-requests/...")
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix="claude-code-requests/"
        )
        file_count = len(response.get('Contents', [])) - 1  # Exclude prefix folder itself
        console.print(f"[green]✓ Found {file_count} file(s) in requests folder[/green]")

        # Delete test file
        console.print("  Cleaning up test file...")
        s3_client.delete_object(Bucket=bucket_name, Key=test_key)
        console.print("[green]✓ Test file deleted[/green]")

        return True

    except Exception as e:
        console.print(f"[red]✗ File operation error: {e}[/red]")
        return False


def test_end_to_end(s3_client, bucket_name):
    """Test end-to-end request/response flow."""
    console.print("\n[bold cyan]Test 3: End-to-End Request/Response Flow[/bold cyan]")
    console.print("  [dim]This test requires the poller (claude_code_poller.py) to be running[/dim]")

    # Ask user if they want to proceed
    response = console.input("\n  Run end-to-end test? [y/N]: ")
    if response.lower() != 'y':
        console.print("  [yellow]Skipped[/yellow]")
        return True

    try:
        # Create request
        request_id = str(uuid.uuid4())
        request_data = {
            "request_id": request_id,
            "prompt": "What is 2+2? Just respond with the number.",
            "task_type": "analysis",
            "task_description": "Analyze code, data, or text files",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "max_wait_seconds": 60,
            "submitted_by": "test_script"
        }

        # Upload request
        request_key = f"claude-code-requests/{request_id}.json"
        console.print(f"\n  Uploading request: [cyan]{request_id}[/cyan]")
        s3_client.put_object(
            Bucket=bucket_name,
            Key=request_key,
            Body=json.dumps(request_data, indent=2),
            ContentType='application/json'
        )
        console.print("[green]✓ Request uploaded[/green]")

        # Wait for response with progress indicator
        response_key = f"claude-code-responses/{request_id}.json"
        max_wait = 60
        start_time = time.time()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("  Waiting for response from poller...", total=None)

            while time.time() - start_time < max_wait:
                try:
                    response_obj = s3_client.get_object(Bucket=bucket_name, Key=response_key)
                    response_data = json.loads(response_obj['Body'].read())

                    # Clean up files
                    s3_client.delete_object(Bucket=bucket_name, Key=request_key)
                    s3_client.delete_object(Bucket=bucket_name, Key=response_key)

                    # Check result
                    if response_data.get("error"):
                        console.print(f"[red]✗ Response contained error: {response_data['error']}[/red]")
                        return False
                    else:
                        console.print("\n[green]✓ Received response from poller![/green]")
                        console.print(f"  Execution time: {response_data.get('execution_time_seconds', 'unknown')}s")
                        console.print(f"  Response preview: {response_data.get('response', '')[:100]}...")
                        return True

                except Exception:
                    # Response not ready yet
                    time.sleep(2)
                    continue

        # Timeout
        console.print(f"\n[yellow]⚠ Timeout after {max_wait}s - poller may not be running[/yellow]")
        console.print("  To test end-to-end flow:")
        console.print("  1. Start the poller: python claude_code_poller.py")
        console.print("  2. Run this test again")

        # Clean up request file
        try:
            s3_client.delete_object(Bucket=bucket_name, Key=request_key)
        except:
            pass

        return False

    except Exception as e:
        console.print(f"[red]✗ End-to-end test error: {e}[/red]")
        return False


def main():
    """Run all tests."""
    parser = argparse.ArgumentParser(
        description="Test Claude Code integration with Cloudflare R2"
    )
    parser.add_argument(
        '--config',
        help='Path to config.yaml file',
        default='config.yaml'
    )

    args = parser.parse_args()

    # Load configuration
    get_config(args.config)
    r2_config = get_r2_config()

    # Print header
    console.print(Panel.fit(
        "[bold cyan]Claude Code Integration Test Suite[/bold cyan]\n"
        f"Bucket: {r2_config['bucket_name']}\n"
        f"Account: {r2_config['account_id']}",
        title="Test Configuration"
    ))

    # Run tests
    results = {}

    # Test 1: R2 Connection
    s3_client = test_r2_connection(r2_config)
    results['connection'] = bool(s3_client)

    if s3_client:
        # Test 2: File Operations
        results['file_ops'] = test_file_operations(s3_client, r2_config['bucket_name'])

        # Test 3: End-to-end
        results['end_to_end'] = test_end_to_end(s3_client, r2_config['bucket_name'])

    # Print summary
    console.print("\n" + "=" * 60)
    console.print("[bold]Test Summary:[/bold]")
    console.print("=" * 60)

    for test_name, passed in results.items():
        status = "[green]✓ PASS[/green]" if passed else "[red]✗ FAIL[/red]"
        console.print(f"  {test_name.replace('_', ' ').title()}: {status}")

    all_passed = all(results.values())
    console.print("=" * 60)

    if all_passed:
        console.print("[bold green]All tests passed! ✓[/bold green]")
        console.print("\nNext steps:")
        console.print("1. Ensure poller is running: python claude_code_poller.py")
        console.print("2. Register tool with agent: python register_tools.py")
        console.print("3. Test with umbra via send_to_umbra.py")
    else:
        console.print("[bold red]Some tests failed ✗[/bold red]")
        console.print("\nPlease fix the issues above before proceeding.")

    console.print()

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
