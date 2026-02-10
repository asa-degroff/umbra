#!/usr/bin/env python3
"""Bridge to communicate with Umbriel (OpenClaw agent) from bsky.py."""

import subprocess
import json
import sys
import logging

logger = logging.getLogger(__name__)


def send_to_umbriel(message: str, timeout: int = 120) -> str:
    """Send a message to Umbriel via OpenClaw CLI and return the response.

    Args:
        message: The message/question to send to Umbriel.
        timeout: Timeout in seconds (default: 120).

    Returns:
        Umbriel's response text, or an error message on failure.
    """
    try:
        result = subprocess.run(
            ["openclaw", "agent", "-m", message, "--json", "--timeout", str(timeout)],
            capture_output=True,
            text=True,
            timeout=timeout + 10,  # extra buffer for subprocess overhead
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            logger.error(f"Umbriel bridge: non-zero exit ({result.returncode}): {stderr}")
            return f"[Umbriel error: process exited with code {result.returncode}]"

        stdout = result.stdout.strip()
        if not stdout:
            return "[Umbriel error: empty response]"

        # Try to parse JSON response and extract the reply text
        try:
            data = json.loads(stdout)
            # OpenClaw --json output may vary; try common fields
            if isinstance(data, dict):
                # Try 'reply', 'response', 'message', 'text', 'content'
                for key in ('reply', 'response', 'message', 'text', 'content', 'output'):
                    if key in data and data[key]:
                        return str(data[key])
                # If it's a dict but no known key, return the whole thing
                return json.dumps(data, indent=2)
            elif isinstance(data, str):
                return data
            else:
                return str(data)
        except json.JSONDecodeError:
            # Not JSON - return raw stdout
            return stdout

    except subprocess.TimeoutExpired:
        logger.error(f"Umbriel bridge: timeout after {timeout}s")
        return f"[Umbriel error: timed out after {timeout}s]"
    except FileNotFoundError:
        logger.error("Umbriel bridge: 'openclaw' command not found")
        return "[Umbriel error: openclaw CLI not found]"
    except Exception as e:
        logger.error(f"Umbriel bridge: unexpected error: {e}")
        return f"[Umbriel error: {e}]"


def main():
    """CLI entry point: pass question as arguments."""
    import argparse

    parser = argparse.ArgumentParser(description="Send a message to Umbriel via OpenClaw")
    parser.add_argument("message", nargs="+", help="Message to send")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout in seconds")
    args = parser.parse_args()

    message = " ".join(args.message)
    response = send_to_umbriel(message, timeout=args.timeout)
    print(response)


if __name__ == "__main__":
    main()
