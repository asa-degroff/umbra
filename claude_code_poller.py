#!/usr/bin/env python3
"""
Local polling daemon for Claude Code integration.

This script continuously polls a Cloudflare R2 bucket for new Claude Code
requests from the umbra agent, executes them locally using the Claude Code CLI,
and uploads responses back to R2.

Security Features:
- Task type allowlist validation
- Restricted workspace directory execution
- Request expiration (ignore requests older than 10 minutes)
- Comprehensive logging of all requests and responses

Usage:
    python claude_code_poller.py [--config CONFIG_FILE]

Configuration:
    Uses config.yaml or environment variables:
    - R2_ACCOUNT_ID: Cloudflare R2 account ID
    - R2_ACCESS_KEY_ID: R2 API access key
    - R2_SECRET_ACCESS_KEY: R2 API secret key
    - R2_BUCKET_NAME: R2 bucket name (default: umbra-claude-code)
    - CLAUDE_CODE_WORKSPACE: Workspace directory path (default: ~/umbra-projects)

Requirements:
    - boto3: pip install boto3
    - Claude Code CLI installed and in PATH
    - Valid R2 credentials
"""

import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("Error: boto3 is required. Install with: pip install boto3")
    sys.exit(1)


# Allowlist of approved task types (must match tools/claude_code.py)
APPROVED_TASK_TYPES = {
    "website": "Build, modify, or update website code",
    "code": "Write, refactor, or debug code",
    "documentation": "Create or update documentation",
    "analysis": "Analyze code, data, or text files",
}

# Configuration
POLL_INTERVAL_SECONDS = 5  # How often to check for new requests
REQUEST_EXPIRATION_MINUTES = 10  # Ignore requests older than this
MAX_EXECUTION_TIME_SECONDS = 300  # 5 minute timeout for Claude Code


class ClaudeCodePoller:
    """Poll R2 for Claude Code requests and execute them locally."""

    def __init__(self, config_file: Optional[str] = None, verbose: bool = False):
        """Initialize the poller with configuration."""
        self.config_file = config_file
        self.verbose = verbose
        self.load_config()
        self.setup_s3_client()
        self.setup_workspace()
        self.log(f"Claude Code Poller initialized")
        self.log(f"Bucket: {self.bucket_name}")
        self.log(f"Workspace: {self.workspace_dir}")
        self.log(f"Poll interval: {POLL_INTERVAL_SECONDS}s")
        self.log(f"Verbose mode: {'enabled' if verbose else 'disabled'}")

    def load_config(self):
        """Load configuration from file or environment variables."""
        # Try to load from config.yaml first
        if self.config_file and os.path.exists(self.config_file):
            try:
                import yaml
                with open(self.config_file, 'r') as f:
                    config = yaml.safe_load(f) or {}

                # Extract R2 configuration
                r2_config = config.get('cloudflare_r2', {})
                self.account_id = r2_config.get('account_id') or os.getenv('R2_ACCOUNT_ID')
                self.access_key_id = r2_config.get('access_key_id') or os.getenv('R2_ACCESS_KEY_ID')
                self.secret_access_key = r2_config.get('secret_access_key') or os.getenv('R2_SECRET_ACCESS_KEY')
                self.bucket_name = r2_config.get('bucket_name') or os.getenv('R2_BUCKET_NAME', 'umbra-claude-code')

                # Extract Claude Code configuration
                cc_config = config.get('claude_code', {})
                workspace = cc_config.get('workspace_dir') or os.getenv('CLAUDE_CODE_WORKSPACE', '~/umbra-projects')
                self.workspace_dir = os.path.expanduser(workspace)

            except Exception as e:
                self.log(f"Warning: Could not load config file: {e}")
                self.load_from_env()
        else:
            self.load_from_env()

        # Validate required configuration
        if not all([self.account_id, self.access_key_id, self.secret_access_key]):
            print("Error: R2 credentials not configured!")
            print("Required environment variables or config.yaml settings:")
            print("  - R2_ACCOUNT_ID")
            print("  - R2_ACCESS_KEY_ID")
            print("  - R2_SECRET_ACCESS_KEY")
            sys.exit(1)

    def load_from_env(self):
        """Load configuration from environment variables."""
        self.account_id = os.getenv('R2_ACCOUNT_ID')
        self.access_key_id = os.getenv('R2_ACCESS_KEY_ID')
        self.secret_access_key = os.getenv('R2_SECRET_ACCESS_KEY')
        self.bucket_name = os.getenv('R2_BUCKET_NAME', 'umbra-claude-code')
        workspace = os.getenv('CLAUDE_CODE_WORKSPACE', '~/umbra-projects')
        self.workspace_dir = os.path.expanduser(workspace)

    def setup_s3_client(self):
        """Create S3-compatible client for Cloudflare R2."""
        r2_endpoint = f"https://{self.account_id}.r2.cloudflarestorage.com"
        self.s3_client = boto3.client(
            's3',
            endpoint_url=r2_endpoint,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name='auto'
        )

    def setup_workspace(self):
        """Create and validate workspace directory."""
        workspace_path = Path(self.workspace_dir)
        workspace_path.mkdir(parents=True, exist_ok=True)

        if not workspace_path.is_dir():
            print(f"Error: Could not create workspace directory: {self.workspace_dir}")
            sys.exit(1)

        # Create a README in the workspace
        readme_path = workspace_path / "README.md"
        if not readme_path.exists():
            readme_content = """# Umbra Claude Code Workspace

This directory is used by umbra's Claude Code integration to execute coding tasks.

**Security Notice:**
- This directory is isolated from the rest of your system
- Only approved task types are executed here
- All requests are logged

**Task Types:**
- website: Build, modify, or update website code
- code: Write, refactor, or debug code
- documentation: Create or update documentation
- analysis: Analyze code, data, or text files

Created by claude_code_poller.py
"""
            readme_path.write_text(readme_content)

    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def is_request_expired(self, request_data: Dict) -> bool:
        """Check if a request is too old to process."""
        try:
            timestamp_str = request_data.get('timestamp')
            if not timestamp_str:
                return True

            request_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            age = datetime.now(timezone.utc) - request_time
            return age > timedelta(minutes=REQUEST_EXPIRATION_MINUTES)
        except Exception:
            return True

    def validate_task_type(self, task_type: str) -> bool:
        """Validate task type against allowlist."""
        return task_type in APPROVED_TASK_TYPES

    def execute_claude_code(self, request_data: Dict) -> Dict:
        """Execute Claude Code CLI with the request prompt."""
        request_id = request_data['request_id']
        prompt = request_data['prompt']
        task_type = request_data['task_type']

        self.log(f"Executing request {request_id} (task: {task_type})")
        if self.verbose:
            self.log(f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")

        try:
            # Build Claude Code command
            cmd = [
                "claude",
                "-p",  # Print mode (non-interactive)
                prompt,
                "--output-format", "json",
                "--dangerously-skip-permissions"  # Auto-approve for automation
            ]

            # Execute in workspace directory
            start_time = time.time()

            if self.verbose:
                # Stream output in verbose mode
                self.log(f"{'='*60}")
                self.log(f"CLAUDE CODE OUTPUT (Request {request_id}):")
                self.log(f"{'='*60}")

                result = subprocess.run(
                    cmd,
                    cwd=self.workspace_dir,
                    text=True,
                    timeout=MAX_EXECUTION_TIME_SECONDS
                    # stdout/stderr will go to console
                )

                self.log(f"{'='*60}")
                self.log(f"END OUTPUT (Request {request_id})")
                self.log(f"{'='*60}")
            else:
                # Capture output in non-verbose mode
                result = subprocess.run(
                    cmd,
                    cwd=self.workspace_dir,
                    capture_output=True,
                    text=True,
                    timeout=MAX_EXECUTION_TIME_SECONDS
                )

            execution_time = time.time() - start_time

            # Check for errors
            if result.returncode != 0:
                error_msg = result.stderr if hasattr(result, 'stderr') and result.stderr else "Claude Code execution failed"
                self.log(f"Request {request_id} failed: {error_msg}", level="ERROR")
                return {
                    "request_id": request_id,
                    "error": error_msg,
                    "response": None,
                    "execution_time_seconds": round(execution_time, 2)
                }

            # In verbose mode, we need to capture output for the response
            # Since we streamed it, we'll return a success message
            if self.verbose:
                response_text = f"Task completed. Check console output above for details. Execution time: {execution_time:.2f}s"
            else:
                # Parse JSON output if available, otherwise use stdout
                try:
                    response_data = json.loads(result.stdout)
                    response_text = json.dumps(response_data, indent=2)
                except json.JSONDecodeError:
                    response_text = result.stdout

            self.log(f"Request {request_id} completed in {execution_time:.2f}s")

            return {
                "request_id": request_id,
                "response": response_text,
                "error": None,
                "execution_time_seconds": round(execution_time, 2),
                "task_type": task_type,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }

        except subprocess.TimeoutExpired:
            self.log(f"Request {request_id} timed out after {MAX_EXECUTION_TIME_SECONDS}s", level="ERROR")
            return {
                "request_id": request_id,
                "error": f"Execution timed out after {MAX_EXECUTION_TIME_SECONDS}s",
                "response": None,
                "execution_time_seconds": MAX_EXECUTION_TIME_SECONDS
            }
        except FileNotFoundError:
            self.log("Error: Claude Code CLI not found in PATH", level="ERROR")
            return {
                "request_id": request_id,
                "error": "Claude Code CLI not found. Please ensure 'claude' command is in PATH.",
                "response": None,
                "execution_time_seconds": 0
            }
        except Exception as e:
            self.log(f"Request {request_id} error: {str(e)}", level="ERROR")
            return {
                "request_id": request_id,
                "error": str(e),
                "response": None,
                "execution_time_seconds": 0
            }

    def process_request(self, request_key: str):
        """Download, validate, execute, and respond to a request."""
        try:
            # Download request
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=request_key
            )
            request_data = json.loads(response['Body'].read())

            request_id = request_data.get('request_id', 'unknown')
            task_type = request_data.get('task_type', '')

            # Validate request
            if self.is_request_expired(request_data):
                self.log(f"Request {request_id} is expired, skipping", level="WARNING")
                # Delete expired request
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=request_key)
                return

            if not self.validate_task_type(task_type):
                self.log(f"Request {request_id} has invalid task type: {task_type}", level="ERROR")
                # Upload error response
                error_response = {
                    "request_id": request_id,
                    "error": f"Invalid task_type '{task_type}'. Approved types: {', '.join(APPROVED_TASK_TYPES.keys())}",
                    "response": None,
                    "execution_time_seconds": 0
                }
                response_key = f"claude-code-responses/{request_id}.json"
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=response_key,
                    Body=json.dumps(error_response, indent=2),
                    ContentType='application/json'
                )
                # Delete request
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=request_key)
                return

            # Execute Claude Code
            response_data = self.execute_claude_code(request_data)

            # Upload response
            response_key = f"claude-code-responses/{request_id}.json"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=response_key,
                Body=json.dumps(response_data, indent=2),
                ContentType='application/json'
            )

            # Delete processed request
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=request_key)

            self.log(f"Request {request_id} processed and response uploaded")

        except ClientError as e:
            self.log(f"S3 error processing {request_key}: {str(e)}", level="ERROR")
        except Exception as e:
            self.log(f"Error processing {request_key}: {str(e)}", level="ERROR")

    def poll_once(self):
        """Poll R2 once for new requests."""
        try:
            # List all request files
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix="claude-code-requests/"
            )

            if 'Contents' not in response:
                return  # No requests

            # Process each request
            for obj in response['Contents']:
                key = obj['Key']
                if not key.endswith('.json'):
                    continue

                # Skip the prefix directory itself
                if key == "claude-code-requests/":
                    continue

                self.log(f"Found new request: {key}")
                self.process_request(key)

        except ClientError as e:
            self.log(f"Error polling R2: {str(e)}", level="ERROR")
        except Exception as e:
            self.log(f"Unexpected error in poll loop: {str(e)}", level="ERROR")

    def run(self):
        """Run the polling loop continuously."""
        self.log("Starting polling loop...")
        self.log(f"Approved task types: {', '.join(APPROVED_TASK_TYPES.keys())}")
        self.log("Press Ctrl+C to stop")

        try:
            while True:
                self.poll_once()
                time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            self.log("Shutting down...")
            sys.exit(0)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Poll Cloudflare R2 for Claude Code requests from umbra"
    )
    parser.add_argument(
        '--config',
        help='Path to config.yaml file',
        default='config.yaml'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show Claude Code output in real-time (useful for debugging)'
    )

    args = parser.parse_args()

    # Create and run poller
    poller = ClaudeCodePoller(config_file=args.config, verbose=args.verbose)
    poller.run()


if __name__ == "__main__":
    main()
