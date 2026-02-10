#!/usr/bin/env python3
"""
Local polling daemon for Umbriel integration.

Polls Cloudflare R2 for Umbriel requests from Umbra, sends them to Umbriel
via OpenClaw CLI, and uploads responses back to R2.

Usage:
    python umbriel_poller.py [--config CONFIG_FILE] [--verbose]

Environment variables:
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("Error: boto3 is required. Install with: pip install boto3")
    sys.exit(1)


POLL_INTERVAL_SECONDS = 5
REQUEST_EXPIRATION_MINUTES = 15
MAX_EXECUTION_TIME_SECONDS = 300


class UmbrielPoller:
    """Poll R2 for Umbriel requests and execute them via OpenClaw CLI."""

    def __init__(self, config_file: Optional[str] = None, verbose: bool = False):
        self.config_file = config_file
        self.verbose = verbose
        self.load_config()
        self.setup_s3_client()
        self.log(f"Umbriel Poller initialized")
        self.log(f"Bucket: {self.bucket_name}")
        self.log(f"Poll interval: {POLL_INTERVAL_SECONDS}s")

    def load_config(self):
        if self.config_file and os.path.exists(self.config_file):
            try:
                import yaml
                with open(self.config_file, 'r') as f:
                    config = yaml.safe_load(f) or {}
                r2_config = config.get('cloudflare_r2', {})
                self.account_id = r2_config.get('account_id') or os.getenv('R2_ACCOUNT_ID')
                self.access_key_id = r2_config.get('access_key_id') or os.getenv('R2_ACCESS_KEY_ID')
                self.secret_access_key = r2_config.get('secret_access_key') or os.getenv('R2_SECRET_ACCESS_KEY')
                self.bucket_name = r2_config.get('bucket_name') or os.getenv('R2_BUCKET_NAME', 'umbra-claude-code')
            except Exception as e:
                self.log(f"Warning: Could not load config file: {e}")
                self.load_from_env()
        else:
            self.load_from_env()

        if not all([self.account_id, self.access_key_id, self.secret_access_key]):
            print("Error: R2 credentials not configured!")
            print("Required: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY")
            sys.exit(1)

    def load_from_env(self):
        self.account_id = os.getenv('R2_ACCOUNT_ID')
        self.access_key_id = os.getenv('R2_ACCESS_KEY_ID')
        self.secret_access_key = os.getenv('R2_SECRET_ACCESS_KEY')
        self.bucket_name = os.getenv('R2_BUCKET_NAME', 'umbra-claude-code')

    def setup_s3_client(self):
        r2_endpoint = f"https://{self.account_id}.r2.cloudflarestorage.com"
        self.s3_client = boto3.client(
            's3',
            endpoint_url=r2_endpoint,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name='auto'
        )

    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def is_request_expired(self, request_data: Dict) -> bool:
        try:
            timestamp_str = request_data.get('timestamp')
            if not timestamp_str:
                return True
            request_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            age = datetime.now(timezone.utc) - request_time
            return age > timedelta(minutes=REQUEST_EXPIRATION_MINUTES)
        except Exception:
            return True

    def execute_umbriel_request(self, request_data: Dict) -> Dict:
        """Send message to Umbriel via OpenClaw CLI and return response."""
        request_id = request_data['request_id']
        message = request_data.get('message', request_data.get('question', ''))
        priority = request_data.get('priority', 'normal')

        self.log(f"🌙 Executing request {request_id} (priority: {priority})")
        if self.verbose:
            self.log(f"   Message: {message[:200]}{'...' if len(message) > 200 else ''}")

        # Daily reviews are large — give them more time
        is_daily_review = request_data.get('submitted_by') == 'umbra-daily-review'
        if is_daily_review:
            timeout = 300
        elif priority == 'high':
            timeout = 240
        else:
            timeout = 120

        try:
            start_time = time.time()

            # Ensure openclaw is in PATH
            env = os.environ.copy()
            npm_bin = os.path.expanduser("~/.npm-global/bin")
            if npm_bin not in env.get("PATH", ""):
                env["PATH"] = f"{npm_bin}:{env.get('PATH', '')}"

            cmd = [
                "openclaw", "agent",
                "-m", message,
                "--channel", "telegram",
                "--to", "telegram:8223522714",
                "--timeout", str(timeout)
            ]

            if self.verbose:
                self.log(f"   Running: openclaw agent -m '...' --timeout {timeout}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 30,  # buffer for subprocess overhead
                env=env
            )

            execution_time = time.time() - start_time

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else f"Process exited with code {result.returncode}"
                self.log(f"   Request {request_id} failed: {error_msg}", level="ERROR")
                return {
                    "request_id": request_id,
                    "error": error_msg,
                    "response": None,
                    "execution_time_seconds": round(execution_time, 2)
                }

            response_text = result.stdout.strip()
            if not response_text:
                response_text = "[Empty response from Umbriel]"

            # Try to parse JSON and extract content
            try:
                data = json.loads(response_text)
                if isinstance(data, dict):
                    for key in ('reply', 'response', 'message', 'text', 'content', 'output'):
                        if key in data and data[key]:
                            response_text = str(data[key])
                            break
            except json.JSONDecodeError:
                pass  # Use raw text

            # Append reply instructions so Umbra knows how to continue the conversation
            response_text += "\n\n[To reply to Umbriel, use the ask_umbriel tool.]"

            self.log(f"   Request {request_id} completed in {execution_time:.2f}s")

            return {
                "request_id": request_id,
                "response": response_text,
                "error": None,
                "execution_time_seconds": round(execution_time, 2),
                "priority": priority,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }

        except subprocess.TimeoutExpired:
            self.log(f"   Request {request_id} timed out after {timeout}s", level="ERROR")
            return {
                "request_id": request_id,
                "error": f"Timed out after {timeout}s",
                "response": None,
                "execution_time_seconds": timeout
            }
        except FileNotFoundError:
            self.log("   Error: 'openclaw' command not found in PATH", level="ERROR")
            return {
                "request_id": request_id,
                "error": "openclaw CLI not found",
                "response": None,
                "execution_time_seconds": 0
            }
        except Exception as e:
            self.log(f"   Request {request_id} error: {str(e)}", level="ERROR")
            return {
                "request_id": request_id,
                "error": str(e),
                "response": None,
                "execution_time_seconds": 0
            }

    def process_request(self, request_key: str):
        """Download, validate, execute, and respond to a request."""
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=request_key
            )
            request_data = json.loads(response['Body'].read())
            request_id = request_data.get('request_id', 'unknown')

            if self.is_request_expired(request_data):
                self.log(f"Request {request_id} is expired, skipping", level="WARNING")
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=request_key)
                return

            # Execute via OpenClaw
            response_data = self.execute_umbriel_request(request_data)

            # Upload response
            response_key = f"umbriel-responses/{request_id}.json"
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
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix="umbriel-requests/"
            )

            if 'Contents' not in response:
                return

            for obj in response['Contents']:
                key = obj['Key']
                if not key.endswith('.json'):
                    continue
                if key == "umbriel-requests/":
                    continue

                self.log(f"Found new request: {key}")
                self.process_request(key)

        except ClientError as e:
            self.log(f"Error polling R2: {str(e)}", level="ERROR")
        except Exception as e:
            self.log(f"Unexpected error in poll loop: {str(e)}", level="ERROR")

    def run(self):
        """Run the polling loop continuously."""
        self.log("Starting Umbriel polling loop...")
        self.log("Press Ctrl+C to stop")

        try:
            while True:
                self.poll_once()
                time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            self.log("Shutting down...")
            sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="Poll Cloudflare R2 for Umbriel requests from Umbra"
    )
    parser.add_argument('--config', help='Path to config.yaml file', default='config.yaml')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    poller = UmbrielPoller(config_file=args.config, verbose=args.verbose)
    poller.run()


if __name__ == "__main__":
    main()
