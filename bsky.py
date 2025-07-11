from rich import print  # pretty printing tools
from time import sleep
from letta_client import Letta
from bsky_utils import thread_to_yaml_string
import os
import logging
import json
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import time
import argparse

from utils import (
    upsert_block,
    upsert_agent
)

import bsky_utils
from tools.blocks import attach_user_blocks, detach_user_blocks
from config_loader import (
    get_config,
    get_letta_config,
    get_bluesky_config,
    get_bot_config,
    get_agent_config,
    get_threading_config,
    get_queue_config
)


def extract_handles_from_data(data):
    """Recursively extract all unique handles from nested data structure."""
    handles = set()

    def _extract_recursive(obj):
        if isinstance(obj, dict):
            # Check if this dict has a 'handle' key
            if 'handle' in obj:
                handles.add(obj['handle'])
            # Recursively check all values
            for value in obj.values():
                _extract_recursive(value)
        elif isinstance(obj, list):
            # Recursively check all list items
            for item in obj:
                _extract_recursive(item)

    _extract_recursive(data)
    return list(handles)


# Initialize configuration and logging
config = get_config()
config.setup_logging()
logger = logging.getLogger("void_bot")

# Load configuration sections
letta_config = get_letta_config()
bluesky_config = get_bluesky_config()
bot_config = get_bot_config()
agent_config = get_agent_config()
threading_config = get_threading_config()
queue_config = get_queue_config()

# Create a client with extended timeout for LLM operations
CLIENT = Letta(
    token=letta_config['api_key'],
    timeout=letta_config['timeout']
)

# Use the configured project ID
PROJECT_ID = letta_config['project_id']

# Notification check delay
FETCH_NOTIFICATIONS_DELAY_SEC = bot_config['fetch_notifications_delay']

# Queue directory
QUEUE_DIR = Path(queue_config['base_dir'])
QUEUE_DIR.mkdir(exist_ok=True)
QUEUE_ERROR_DIR = Path(queue_config['error_dir'])
QUEUE_ERROR_DIR.mkdir(exist_ok=True, parents=True)
QUEUE_NO_REPLY_DIR = Path(queue_config['no_reply_dir'])
QUEUE_NO_REPLY_DIR.mkdir(exist_ok=True, parents=True)
PROCESSED_NOTIFICATIONS_FILE = Path(queue_config['processed_file'])

# Maximum number of processed notifications to track
MAX_PROCESSED_NOTIFICATIONS = bot_config['max_processed_notifications']

# Message tracking counters
message_counters = defaultdict(int)
start_time = time.time()

# Testing mode flag
TESTING_MODE = False

# Skip git operations flag
SKIP_GIT = False


def export_agent_state(client, agent, skip_git=False):
    """Export agent state to agent_archive/ (timestamped) and agents/ (current)."""
    try:
        # Confirm export with user unless git is being skipped
        if not skip_git:
            response = input(
                "Export agent state to files and stage with git? (y/n): ").lower().strip()
            if response not in ['y', 'yes']:
                logger.info("Agent export cancelled by user.")
                return
        else:
            logger.info("Exporting agent state (git staging disabled)")

        # Create directories if they don't exist
        os.makedirs("agent_archive", exist_ok=True)
        os.makedirs("agents", exist_ok=True)

        # Export agent data
        logger.info(f"Exporting agent {agent.id}. This takes some time...")
        agent_data = client.agents.export_file(agent_id=agent.id)

        # Save timestamped archive copy
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = os.path.join("agent_archive", f"void_{timestamp}.af")
        with open(archive_file, 'w', encoding='utf-8') as f:
            json.dump(agent_data, f, indent=2, ensure_ascii=False)

        # Save current agent state
        current_file = os.path.join("agents", "void.af")
        with open(current_file, 'w', encoding='utf-8') as f:
            json.dump(agent_data, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ Agent exported to {archive_file} and {current_file}")

        # Git add only the current agent file (archive is ignored) unless skip_git is True
        if not skip_git:
            try:
                subprocess.run(["git", "add", current_file],
                               check=True, capture_output=True)
                logger.info("Added current agent file to git staging")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to git add agent file: {e}")

    except Exception as e:
        logger.error(f"Failed to export agent: {e}")


def initialize_void():
    logger.info("Starting void agent initialization...")

    # Get block configurations
    blocks_config = agent_config['blocks']

    # Ensure that a shared zeitgeist block exists
    logger.info("Creating/updating zeitgeist block...")
    zeitgeist_config = blocks_config.get('zeitgeist', {})
    zeigeist_block = upsert_block(
        CLIENT,
        label=zeitgeist_config.get('label', 'zeitgeist'),
        value=zeitgeist_config.get(
            'value', "I don't currently know anything about what is happening right now."),
        description=zeitgeist_config.get(
            'description', "A block to store your understanding of the current social environment.")
    )

    # Ensure that a shared void personality block exists
    logger.info("Creating/updating void-persona block...")
    persona_config = blocks_config.get('persona', {})
    persona_block = upsert_block(
        CLIENT,
        label=persona_config.get('label', 'void-persona'),
        value=persona_config.get(
            'value', "My name is Void. I live in the void. I must develop my personality."),
        description=persona_config.get(
            'description', "The personality of Void.")
    )

    # Ensure that a shared void human block exists
    logger.info("Creating/updating void-humans block...")
    humans_config = blocks_config.get('humans', {})
    human_block = upsert_block(
        CLIENT,
        label=humans_config.get('label', 'void-humans'),
        value=humans_config.get(
            'value', "I haven't seen any bluesky users yet. I will update this block when I learn things about users, identified by their handles such as @cameron.pfiffer.org."),
        description=humans_config.get(
            'description', "A block to store your understanding of users you talk to or observe on the bluesky social network.")
    )

    # Create the agent if it doesn't exist
    logger.info("Creating/updating void agent...")
    void_agent = upsert_agent(
        CLIENT,
        name=agent_config['name'],
        block_ids=[
            persona_block.id,
            human_block.id,
            zeigeist_block.id,
        ],
        tags=["social agent", "bluesky"],
        model=agent_config['model'],
        embedding=agent_config['embedding'],
        description=agent_config['description'],
        project_id=PROJECT_ID
    )

    # Export agent state
    logger.info("Exporting agent state...")
    export_agent_state(CLIENT, void_agent, skip_git=SKIP_GIT)

    # Log agent details
    logger.info(f"Void agent details - ID: {void_agent.id}")
    logger.info(f"Agent name: {void_agent.name}")
    if hasattr(void_agent, 'llm_config'):
        logger.info(f"Agent model: {void_agent.llm_config.model}")
    logger.info(f"Agent project_id: {void_agent.project_id}")
    if hasattr(void_agent, 'tools'):
        logger.info(f"Agent has {len(void_agent.tools)} tools")
        for tool in void_agent.tools[:3]:  # Show first 3 tools
            logger.info(f"  - Tool: {tool.name} (type: {tool.tool_type})")

    return void_agent


def process_mention(void_agent, atproto_client, notification_data, queue_filepath=None, testing_mode=False):
    """Process a mention and generate a reply using the Letta agent.

    Args:
        void_agent: The Letta agent instance
        atproto_client: The AT Protocol client
        notification_data: The notification data dictionary
        queue_filepath: Optional Path object to the queue file (for cleanup on halt)

    Returns:
        True: Successfully processed, remove from queue
        False: Failed but retryable, keep in queue
        None: Failed with non-retryable error, move to errors directory
        "no_reply": No reply was generated, move to no_reply directory
    """
    try:
        logger.debug(
            f"Starting process_mention with notification_data type: {type(notification_data)}")

        # Handle both dict and object inputs for backwards compatibility
        if isinstance(notification_data, dict):
            uri = notification_data['uri']
            mention_text = notification_data.get('record', {}).get('text', '')
            author_handle = notification_data['author']['handle']
            author_name = notification_data['author'].get(
                'display_name') or author_handle
        else:
            # Legacy object access
            uri = notification_data.uri
            mention_text = notification_data.record.text if hasattr(
                notification_data.record, 'text') else ""
            author_handle = notification_data.author.handle
            author_name = notification_data.author.display_name or author_handle

        logger.info(
            f"Extracted data - URI: {uri}, Author: @{author_handle}, Text: {mention_text[:50]}...")

        # Retrieve the entire thread associated with the mention
        try:
            thread = atproto_client.app.bsky.feed.get_post_thread({
                'uri': uri,
                'parent_height': threading_config['parent_height'],
                'depth': threading_config['depth']
            })
        except Exception as e:
            error_str = str(e)
            # Check for various error types that indicate the post/user is gone
            if 'NotFound' in error_str or 'Post not found' in error_str:
                logger.warning(
                    f"Post not found for URI {uri}, removing from queue")
                return True  # Return True to remove from queue
            elif 'Could not find user info' in error_str or 'InvalidRequest' in error_str:
                logger.warning(
                    f"User account not found for post URI {uri} (account may be deleted/suspended), removing from queue")
                return True  # Return True to remove from queue
            elif 'BadRequestError' in error_str:
                logger.warning(
                    f"Bad request error for URI {uri}: {e}, removing from queue")
                return True  # Return True to remove from queue
            else:
                # Re-raise other errors
                logger.error(f"Error fetching thread: {e}")
                raise

        # Get thread context as YAML string
        logger.debug("Converting thread to YAML string")
        try:
            thread_context = thread_to_yaml_string(thread)
            logger.debug(
                f"Thread context generated, length: {len(thread_context)} characters")

            # Create a more informative preview by extracting meaningful content
            lines = thread_context.split('\n')
            meaningful_lines = []

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue

                # Look for lines with actual content (not just structure)
                if any(keyword in line for keyword in ['text:', 'handle:', 'display_name:', 'created_at:', 'reply_count:', 'like_count:']):
                    meaningful_lines.append(line)
                    if len(meaningful_lines) >= 5:
                        break

            if meaningful_lines:
                preview = '\n'.join(meaningful_lines)
                logger.debug(f"Thread content preview:\n{preview}")
            else:
                # If no content fields found, just show it's a thread structure
                logger.debug(
                    f"Thread structure generated ({len(thread_context)} chars)")
        except Exception as yaml_error:
            import traceback
            logger.error(f"Error converting thread to YAML: {yaml_error}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            logger.error(f"Thread type: {type(thread)}")
            if hasattr(thread, '__dict__'):
                logger.error(f"Thread attributes: {thread.__dict__}")
            # Try to continue with a simple context
            thread_context = f"Error processing thread context: {str(yaml_error)}"

        # Create a prompt for the Letta agent with thread context
        prompt = f"""You received a mention on Bluesky from @{author_handle} ({author_name or author_handle}).

MOST RECENT POST (the mention you're responding to):
"{mention_text}"

FULL THREAD CONTEXT:
```yaml
{thread_context}
```

The YAML above shows the complete conversation thread. The most recent post is the one mentioned above that you should respond to, but use the full thread context to understand the conversation flow.

To reply, use the add_post_to_bluesky_reply_thread tool. Call it multiple times to create a threaded reply:
- Each call adds one post to the reply thread (max 300 characters per post)
- Use multiple calls to build longer responses across several posts
- Example: First call for opening thought, second call for elaboration, etc."""

        # Extract all handles from notification and thread data
        all_handles = set()
        all_handles.update(extract_handles_from_data(notification_data))
        all_handles.update(extract_handles_from_data(thread.model_dump()))
        unique_handles = list(all_handles)

        logger.debug(
            f"Found {len(unique_handles)} unique handles in thread: {unique_handles}")

        # Attach user blocks before agent call
        attached_handles = []
        if unique_handles:
            try:
                logger.debug(
                    f"Attaching user blocks for handles: {unique_handles}")
                attach_result = attach_user_blocks(unique_handles, void_agent)
                attached_handles = unique_handles  # Track successfully attached handles
                logger.debug(f"Attach result: {attach_result}")
            except Exception as attach_error:
                logger.warning(f"Failed to attach user blocks: {attach_error}")
                # Continue without user blocks rather than failing completely

        # Get response from Letta agent
        logger.info(f"Mention from @{author_handle}: {mention_text}")

        # Log prompt details to separate logger
        prompt_logger.debug(f"Full prompt being sent:\n{prompt}")

        # Log concise prompt info to main logger
        thread_handles_count = len(unique_handles)
        logger.info(
            f"💬 Sending to LLM: @{author_handle} mention | msg: \"{mention_text[:50]}...\" | context: {len(thread_context)} chars, {thread_handles_count} users")

        try:
            # Use streaming to avoid 524 timeout errors
            message_stream = CLIENT.agents.messages.create_stream(
                agent_id=void_agent.id,
                messages=[{"role": "user", "content": prompt}],
                # Step streaming only (faster than token streaming)
                stream_tokens=False,
                max_steps=agent_config['max_steps']
            )

            # Collect the streaming response
            all_messages = []
            for chunk in message_stream:
                # Log condensed chunk info
                if hasattr(chunk, 'message_type'):
                    if chunk.message_type == 'reasoning_message':
                        # Show full reasoning without truncation
                        logger.info(f"🧠 Reasoning: {chunk.reasoning}")
                    elif chunk.message_type == 'tool_call_message':
                        # Parse tool arguments for better display
                        tool_name = chunk.tool_call.name
                        try:
                            args = json.loads(chunk.tool_call.arguments)
                            # Format based on tool type
                            if tool_name == 'bluesky_reply':
                                messages = args.get(
                                    'messages', [args.get('message', '')])
                                lang = args.get('lang', 'en-US')
                                if messages and isinstance(messages, list):
                                    preview = messages[0][:100] + "..." if len(
                                        messages[0]) > 100 else messages[0]
                                    msg_count = f" ({len(messages)} msgs)" if len(
                                        messages) > 1 else ""
                                    logger.info(
                                        f"🔧 Tool call: {tool_name} → \"{preview}\"{msg_count} [lang: {lang}]")
                                else:
                                    logger.info(
                                        f"🔧 Tool call: {tool_name}({chunk.tool_call.arguments[:150]}...)")
                            elif tool_name == 'archival_memory_search':
                                query = args.get('query', 'unknown')
                                logger.info(
                                    f"🔧 Tool call: {tool_name} → query: \"{query}\"")
                            elif tool_name == 'update_block':
                                label = args.get('label', 'unknown')
                                value_preview = str(args.get('value', ''))[
                                    :50] + "..." if len(str(args.get('value', ''))) > 50 else str(args.get('value', ''))
                                logger.info(
                                    f"🔧 Tool call: {tool_name} → {label}: \"{value_preview}\"")
                            else:
                                # Generic display for other tools
                                args_str = ', '.join(
                                    f"{k}={v}" for k, v in args.items() if k != 'request_heartbeat')
                                if len(args_str) > 150:
                                    args_str = args_str[:150] + "..."
                                logger.info(
                                    f"🔧 Tool call: {tool_name}({args_str})")
                        except:
                            # Fallback to original format if parsing fails
                            logger.info(
                                f"🔧 Tool call: {tool_name}({chunk.tool_call.arguments[:150]}...)")
                    elif chunk.message_type == 'tool_return_message':
                        # Enhanced tool result logging
                        tool_name = chunk.name
                        status = chunk.status

                        if status == 'success':
                            # Try to show meaningful result info based on tool type
                            if hasattr(chunk, 'tool_return') and chunk.tool_return:
                                result_str = str(chunk.tool_return)
                                if tool_name == 'archival_memory_search':
                                    # Count number of results if it looks like a list
                                    if result_str.startswith('[') and result_str.endswith(']'):
                                        try:
                                            results = json.loads(result_str)
                                            logger.info(
                                                f"📋 Tool result: {tool_name} ✓ Found {len(results)} memory entries")
                                        except:
                                            logger.info(
                                                f"📋 Tool result: {tool_name} ✓ {result_str[:100]}...")
                                    else:
                                        logger.info(
                                            f"📋 Tool result: {tool_name} ✓ {result_str[:100]}...")
                                elif tool_name == 'bluesky_reply':
                                    logger.info(
                                        f"📋 Tool result: {tool_name} ✓ Reply posted successfully")
                                elif tool_name == 'update_block':
                                    logger.info(
                                        f"📋 Tool result: {tool_name} ✓ Memory block updated")
                                else:
                                    # Generic success with preview
                                    preview = result_str[:100] + "..." if len(
                                        result_str) > 100 else result_str
                                    logger.info(
                                        f"📋 Tool result: {tool_name} ✓ {preview}")
                            else:
                                logger.info(f"📋 Tool result: {tool_name} ✓")
                        elif status == 'error':
                            # Show error details
                            error_preview = ""
                            if hasattr(chunk, 'tool_return') and chunk.tool_return:
                                error_str = str(chunk.tool_return)
                                error_preview = error_str[:100] + \
                                    "..." if len(
                                        error_str) > 100 else error_str
                                logger.info(
                                    f"📋 Tool result: {tool_name} ✗ Error: {error_preview}")
                            else:
                                logger.info(
                                    f"📋 Tool result: {tool_name} ✗ Error occurred")
                        else:
                            logger.info(
                                f"📋 Tool result: {tool_name} - {status}")
                    elif chunk.message_type == 'assistant_message':
                        logger.info(f"💬 Assistant: {chunk.content[:150]}...")
                    else:
                        logger.info(
                            f"📨 {chunk.message_type}: {str(chunk)[:150]}...")
                else:
                    logger.info(f"📦 Stream status: {chunk}")

                # Log full chunk for debugging
                logger.debug(f"Full streaming chunk: {chunk}")
                all_messages.append(chunk)
                if str(chunk) == 'done':
                    break

            # Convert streaming response to standard format for compatibility
            message_response = type('StreamingResponse', (), {
                'messages': [msg for msg in all_messages if hasattr(msg, 'message_type')]
            })()
        except Exception as api_error:
            import traceback
            error_str = str(api_error)
            logger.error(f"Letta API error: {api_error}")
            logger.error(f"Error type: {type(api_error).__name__}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            logger.error(f"Mention text was: {mention_text}")
            logger.error(f"Author: @{author_handle}")
            logger.error(f"URI: {uri}")

            # Try to extract more info from different error types
            if hasattr(api_error, 'response'):
                logger.error(f"Error response object exists")
                if hasattr(api_error.response, 'text'):
                    logger.error(f"Response text: {api_error.response.text}")
                if hasattr(api_error.response, 'json') and callable(api_error.response.json):
                    try:
                        logger.error(
                            f"Response JSON: {api_error.response.json()}")
                    except:
                        pass

            # Check for specific error types
            if hasattr(api_error, 'status_code'):
                logger.error(f"API Status code: {api_error.status_code}")
                if hasattr(api_error, 'body'):
                    logger.error(f"API Response body: {api_error.body}")
                if hasattr(api_error, 'headers'):
                    logger.error(f"API Response headers: {api_error.headers}")

                if api_error.status_code == 413:
                    logger.error(
                        "413 Payload Too Large - moving to errors directory")
                    return None  # Move to errors directory - payload is too large to ever succeed
                elif api_error.status_code == 524:
                    logger.error(
                        "524 error - timeout from Cloudflare, will retry later")
                    return False  # Keep in queue for retry

            # Check if error indicates we should remove from queue
            if 'status_code: 413' in error_str or 'Payload Too Large' in error_str:
                logger.warning(
                    "Payload too large error, moving to errors directory")
                return None  # Move to errors directory - cannot be fixed by retry
            elif 'status_code: 524' in error_str:
                logger.warning("524 timeout error, keeping in queue for retry")
                return False  # Keep in queue for retry

            raise

        # Log successful response
        logger.debug("Successfully received response from Letta API")
        logger.debug(
            f"Number of messages in response: {len(message_response.messages) if hasattr(message_response, 'messages') else 'N/A'}")

        # Extract successful add_post_to_bluesky_reply_thread tool calls from the agent's response
        reply_candidates = []
        tool_call_results = {}  # Map tool_call_id to status

        logger.debug(
            f"Processing {len(message_response.messages)} response messages...")

        # First pass: collect tool return statuses
        ignored_notification = False
        ignore_reason = ""
        ignore_category = ""

        for message in message_response.messages:
            if hasattr(message, 'tool_call_id') and hasattr(message, 'status') and hasattr(message, 'name'):
                if message.name == 'add_post_to_bluesky_reply_thread':
                    tool_call_results[message.tool_call_id] = message.status
                    logger.debug(
                        f"Tool result: {message.tool_call_id} -> {message.status}")
                elif message.name == 'ignore_notification':
                    # Check if the tool was successful
                    if hasattr(message, 'tool_return') and message.status == 'success':
                        # Parse the return value to extract category and reason
                        result_str = str(message.tool_return)
                        if 'IGNORED_NOTIFICATION::' in result_str:
                            parts = result_str.split('::')
                            if len(parts) >= 3:
                                ignore_category = parts[1]
                                ignore_reason = parts[2]
                                ignored_notification = True
                                logger.info(
                                    f"🚫 Notification ignored - Category: {ignore_category}, Reason: {ignore_reason}")
                elif message.name == 'bluesky_reply':
                    logger.error(
                        "❌ DEPRECATED TOOL DETECTED: bluesky_reply is no longer supported!")
                    logger.error(
                        "Please use add_post_to_bluesky_reply_thread instead.")
                    logger.error(
                        "Update the agent's tools using register_tools.py")
                    # Export agent state before terminating
                    export_agent_state(CLIENT, void_agent, skip_git=SKIP_GIT)
                    logger.info(
                        "=== BOT TERMINATED DUE TO DEPRECATED TOOL USE ===")
                    exit(1)

        # Second pass: process messages and check for successful tool calls
        for i, message in enumerate(message_response.messages, 1):
            # Log concise message info instead of full object
            msg_type = getattr(message, 'message_type', 'unknown')
            if hasattr(message, 'reasoning') and message.reasoning:
                logger.debug(
                    f"  {i}. {msg_type}: {message.reasoning[:100]}...")
            elif hasattr(message, 'tool_call') and message.tool_call:
                tool_name = message.tool_call.name
                logger.debug(f"  {i}. {msg_type}: {tool_name}")
            elif hasattr(message, 'tool_return'):
                tool_name = getattr(message, 'name', 'unknown_tool')
                return_preview = str(message.tool_return)[
                    :100] if message.tool_return else "None"
                status = getattr(message, 'status', 'unknown')
                logger.debug(
                    f"  {i}. {msg_type}: {tool_name} -> {return_preview}... (status: {status})")
            elif hasattr(message, 'text'):
                logger.debug(f"  {i}. {msg_type}: {message.text[:100]}...")
            else:
                logger.debug(f"  {i}. {msg_type}: <no content>")

            # Check for halt_activity tool call
            if hasattr(message, 'tool_call') and message.tool_call:
                if message.tool_call.name == 'halt_activity':
                    logger.info(
                        "🛑 HALT_ACTIVITY TOOL CALLED - TERMINATING BOT")
                    try:
                        args = json.loads(message.tool_call.arguments)
                        reason = args.get('reason', 'Agent requested halt')
                        logger.info(f"Halt reason: {reason}")
                    except:
                        logger.info("Halt reason: <unable to parse>")

                    # Delete the queue file before terminating
                    if queue_filepath and queue_filepath.exists():
                        queue_filepath.unlink()
                        logger.info(
                            f"✅ Deleted queue file: {queue_filepath.name}")

                        # Also mark as processed to avoid reprocessing
                        processed_uris = load_processed_notifications()
                        processed_uris.add(notification_data.get('uri', ''))
                        save_processed_notifications(processed_uris)

                    # Export agent state before terminating
                    export_agent_state(CLIENT, void_agent, skip_git=SKIP_GIT)

                    # Exit the program
                    logger.info("=== BOT TERMINATED BY AGENT ===")
                    exit(0)

            # Check for deprecated bluesky_reply tool
            if hasattr(message, 'tool_call') and message.tool_call:
                if message.tool_call.name == 'bluesky_reply':
                    logger.error(
                        "❌ DEPRECATED TOOL DETECTED: bluesky_reply is no longer supported!")
                    logger.error(
                        "Please use add_post_to_bluesky_reply_thread instead.")
                    logger.error(
                        "Update the agent's tools using register_tools.py")
                    # Export agent state before terminating
                    export_agent_state(CLIENT, void_agent, skip_git=SKIP_GIT)
                    logger.info(
                        "=== BOT TERMINATED DUE TO DEPRECATED TOOL USE ===")
                    exit(1)

                # Collect add_post_to_bluesky_reply_thread tool calls - only if they were successful
                elif message.tool_call.name == 'add_post_to_bluesky_reply_thread':
                    tool_call_id = message.tool_call.tool_call_id
                    tool_status = tool_call_results.get(
                        tool_call_id, 'unknown')

                    if tool_status == 'success':
                        try:
                            args = json.loads(message.tool_call.arguments)
                            reply_text = args.get('text', '')
                            reply_lang = args.get('lang', 'en-US')

                            if reply_text:  # Only add if there's actual content
                                reply_candidates.append(
                                    (reply_text, reply_lang))
                                logger.info(
                                    f"Found successful add_post_to_bluesky_reply_thread candidate: {reply_text[:50]}... (lang: {reply_lang})")
                        except json.JSONDecodeError as e:
                            logger.error(
                                f"Failed to parse tool call arguments: {e}")
                    elif tool_status == 'error':
                        logger.info(
                            f"⚠️ Skipping failed add_post_to_bluesky_reply_thread tool call (status: error)")
                    else:
                        logger.warning(
                            f"⚠️ Skipping add_post_to_bluesky_reply_thread tool call with unknown status: {tool_status}")

        # Check for conflicting tool calls
        if reply_candidates and ignored_notification:
            logger.error(
                f"⚠️ CONFLICT: Agent called both add_post_to_bluesky_reply_thread and ignore_notification!")
            logger.error(
                f"Reply candidates: {len(reply_candidates)}, Ignore reason: {ignore_reason}")
            logger.warning("Item will be left in queue for manual review")
            # Return False to keep in queue
            return False

        if reply_candidates:
            # Aggregate reply posts into a thread
            reply_messages = []
            reply_langs = []
            for text, lang in reply_candidates:
                reply_messages.append(text)
                reply_langs.append(lang)

            # Use the first language for the entire thread (could be enhanced later)
            reply_lang = reply_langs[0] if reply_langs else 'en-US'

            logger.info(
                f"Found {len(reply_candidates)} add_post_to_bluesky_reply_thread calls, building thread")

            # Print the generated reply for testing
            print(f"\n=== GENERATED REPLY THREAD ===")
            print(f"To: @{author_handle}")
            if len(reply_messages) == 1:
                print(f"Reply: {reply_messages[0]}")
            else:
                print(f"Reply thread ({len(reply_messages)} messages):")
                for j, msg in enumerate(reply_messages, 1):
                    print(f"  {j}. {msg}")
            print(f"Language: {reply_lang}")
            print(f"======================\n")

            # Send the reply(s) with language (unless in testing mode)
            if testing_mode:
                logger.info("🧪 TESTING MODE: Skipping actual Bluesky post")
                response = True  # Simulate success
            else:
                if len(reply_messages) == 1:
                    # Single reply - use existing function
                    cleaned_text = bsky_utils.remove_outside_quotes(
                        reply_messages[0])
                    logger.info(
                        f"Sending single reply: {cleaned_text[:50]}... (lang: {reply_lang})")
                    response = bsky_utils.reply_to_notification(
                        client=atproto_client,
                        notification=notification_data,
                        reply_text=cleaned_text,
                        lang=reply_lang
                    )
                else:
                    # Multiple replies - use new threaded function
                    cleaned_messages = [bsky_utils.remove_outside_quotes(
                        msg) for msg in reply_messages]
                    logger.info(
                        f"Sending threaded reply with {len(cleaned_messages)} messages (lang: {reply_lang})")
                    response = bsky_utils.reply_with_thread_to_notification(
                        client=atproto_client,
                        notification=notification_data,
                        reply_messages=cleaned_messages,
                        lang=reply_lang
                    )

            if response:
                logger.info(f"Successfully replied to @{author_handle}")
                return True
            else:
                logger.error(f"Failed to send reply to @{author_handle}")
                return False
        else:
            # Check if notification was explicitly ignored
            if ignored_notification:
                logger.info(
                    f"Notification from @{author_handle} was explicitly ignored (category: {ignore_category})")
                return "ignored"
            else:
                logger.warning(
                    f"No add_post_to_bluesky_reply_thread tool calls found for mention from @{author_handle}, moving to no_reply folder")
                return "no_reply"

    except Exception as e:
        logger.error(f"Error processing mention: {e}")
        return False
    finally:
        # Detach user blocks after agent response (success or failure)
        if 'attached_handles' in locals() and attached_handles:
            try:
                logger.info(
                    f"Detaching user blocks for handles: {attached_handles}")
                detach_result = detach_user_blocks(
                    attached_handles, void_agent)
                logger.debug(f"Detach result: {detach_result}")
            except Exception as detach_error:
                logger.warning(f"Failed to detach user blocks: {detach_error}")


def notification_to_dict(notification):
    """Convert a notification object to a dictionary for JSON serialization."""
    return {
        'uri': notification.uri,
        'cid': notification.cid,
        'reason': notification.reason,
        'is_read': notification.is_read,
        'indexed_at': notification.indexed_at,
        'author': {
            'handle': notification.author.handle,
            'display_name': notification.author.display_name,
            'did': notification.author.did
        },
        'record': {
            'text': getattr(notification.record, 'text', '') if hasattr(notification, 'record') else ''
        }
    }


def load_processed_notifications():
    """Load the set of processed notification URIs."""
    if PROCESSED_NOTIFICATIONS_FILE.exists():
        try:
            with open(PROCESSED_NOTIFICATIONS_FILE, 'r') as f:
                data = json.load(f)
                # Keep only recent entries (last MAX_PROCESSED_NOTIFICATIONS)
                if len(data) > MAX_PROCESSED_NOTIFICATIONS:
                    data = data[-MAX_PROCESSED_NOTIFICATIONS:]
                    save_processed_notifications(data)
                return set(data)
        except Exception as e:
            logger.error(f"Error loading processed notifications: {e}")
    return set()


def save_processed_notifications(processed_set):
    """Save the set of processed notification URIs."""
    try:
        with open(PROCESSED_NOTIFICATIONS_FILE, 'w') as f:
            json.dump(list(processed_set), f)
    except Exception as e:
        logger.error(f"Error saving processed notifications: {e}")


def save_notification_to_queue(notification):
    """Save a notification to the queue directory with priority-based filename."""
    try:
        # Check if already processed
        processed_uris = load_processed_notifications()
        if notification.uri in processed_uris:
            logger.debug(f"Notification already processed: {notification.uri}")
            return False

        # Convert notification to dict
        notif_dict = notification_to_dict(notification)

        # Create JSON string
        notif_json = json.dumps(notif_dict, sort_keys=True)

        # Generate hash for filename (to avoid duplicates)
        notif_hash = hashlib.sha256(notif_json.encode()).hexdigest()[:16]

        # Determine priority based on author handle
        author_handle = getattr(notification.author, 'handle', '') if hasattr(
            notification, 'author') else ''
        priority_users = queue_config['priority_users']
        priority_prefix = "0_" if author_handle in priority_users else "1_"

        # Create filename with priority, timestamp and hash
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{priority_prefix}{timestamp}_{notification.reason}_{notif_hash}.json"
        filepath = QUEUE_DIR / filename

        # Check if this notification URI is already in the queue
        for existing_file in QUEUE_DIR.glob("*.json"):
            if existing_file.name == "processed_notifications.json":
                continue
            try:
                with open(existing_file, 'r') as f:
                    existing_data = json.load(f)
                    if existing_data.get('uri') == notification.uri:
                        logger.debug(
                            f"Notification already queued (URI: {notification.uri})")
                        return False
            except:
                continue

        # Write to file
        with open(filepath, 'w') as f:
            json.dump(notif_dict, f, indent=2)

        priority_label = "HIGH PRIORITY" if priority_prefix == "0_" else "normal"
        logger.info(f"Queued notification ({priority_label}): {filename}")
        return True

    except Exception as e:
        logger.error(f"Error saving notification to queue: {e}")
        return False


def load_and_process_queued_notifications(void_agent, atproto_client, testing_mode=False):
    """Load and process all notifications from the queue in priority order."""
    try:
        # Get all JSON files in queue directory (excluding processed_notifications.json)
        # Files are sorted by name, which puts priority files first (0_ prefix before 1_ prefix)
        queue_files = sorted([f for f in QUEUE_DIR.glob(
            "*.json") if f.name != "processed_notifications.json"])

        if not queue_files:
            return

        logger.info(f"Processing {len(queue_files)} queued notifications")

        # Log current statistics
        elapsed_time = time.time() - start_time
        total_messages = sum(message_counters.values())
        messages_per_minute = (
            total_messages / elapsed_time * 60) if elapsed_time > 0 else 0

        logger.info(
            f"📊 Session stats: {total_messages} total messages ({message_counters['mentions']} mentions, {message_counters['replies']} replies, {message_counters['follows']} follows) | {messages_per_minute:.1f} msg/min")

        for i, filepath in enumerate(queue_files, 1):
            logger.info(
                f"Processing queue file {i}/{len(queue_files)}: {filepath.name}")
            try:
                # Load notification data
                with open(filepath, 'r') as f:
                    notif_data = json.load(f)

                # Process based on type using dict data directly
                success = False
                if notif_data['reason'] == "mention":
                    success = process_mention(
                        void_agent, atproto_client, notif_data, queue_filepath=filepath, testing_mode=testing_mode)
                    if success:
                        message_counters['mentions'] += 1
                elif notif_data['reason'] == "reply":
                    success = process_mention(
                        void_agent, atproto_client, notif_data, queue_filepath=filepath, testing_mode=testing_mode)
                    if success:
                        message_counters['replies'] += 1
                elif notif_data['reason'] == "follow":
                    author_handle = notif_data['author']['handle']
                    author_display_name = notif_data['author'].get(
                        'display_name', 'no display name')
                    follow_update = f"@{author_handle} ({author_display_name}) started following you."
                    logger.info(
                        f"Notifying agent about new follower: @{author_handle}")
                    CLIENT.agents.messages.create(
                        agent_id=void_agent.id,
                        messages=[
                            {"role": "user", "content": f"Update: {follow_update}"}]
                    )
                    success = True  # Follow updates are always successful
                    if success:
                        message_counters['follows'] += 1
                elif notif_data['reason'] == "repost":
                    # Skip reposts silently
                    success = True  # Skip reposts but mark as successful to remove from queue
                    if success:
                        message_counters['reposts_skipped'] += 1
                else:
                    logger.warning(
                        f"Unknown notification type: {notif_data['reason']}")
                    success = True  # Remove unknown types from queue

                # Handle file based on processing result
                if success:
                    if testing_mode:
                        logger.info(
                            f"🧪 TESTING MODE: Keeping queue file: {filepath.name}")
                    else:
                        filepath.unlink()
                        logger.info(
                            f"✅ Successfully processed and removed: {filepath.name}")

                        # Mark as processed to avoid reprocessing
                        processed_uris = load_processed_notifications()
                        processed_uris.add(notif_data['uri'])
                        save_processed_notifications(processed_uris)

                elif success is None:  # Special case for moving to error directory
                    error_path = QUEUE_ERROR_DIR / filepath.name
                    filepath.rename(error_path)
                    logger.warning(
                        f"❌ Moved {filepath.name} to errors directory")

                    # Also mark as processed to avoid retrying
                    processed_uris = load_processed_notifications()
                    processed_uris.add(notif_data['uri'])
                    save_processed_notifications(processed_uris)

                elif success == "no_reply":  # Special case for moving to no_reply directory
                    no_reply_path = QUEUE_NO_REPLY_DIR / filepath.name
                    filepath.rename(no_reply_path)
                    logger.info(
                        f"📭 Moved {filepath.name} to no_reply directory")

                    # Also mark as processed to avoid retrying
                    processed_uris = load_processed_notifications()
                    processed_uris.add(notif_data['uri'])
                    save_processed_notifications(processed_uris)

                elif success == "ignored":  # Special case for explicitly ignored notifications
                    # For ignored notifications, we just delete them (not move to no_reply)
                    filepath.unlink()
                    logger.info(
                        f"🚫 Deleted ignored notification: {filepath.name}")

                    # Also mark as processed to avoid retrying
                    processed_uris = load_processed_notifications()
                    processed_uris.add(notif_data['uri'])
                    save_processed_notifications(processed_uris)

                else:
                    logger.warning(
                        f"⚠️  Failed to process {filepath.name}, keeping in queue for retry")

            except Exception as e:
                logger.error(
                    f"💥 Error processing queued notification {filepath.name}: {e}")
                # Keep the file for retry later

    except Exception as e:
        logger.error(f"Error loading queued notifications: {e}")


def process_notifications(void_agent, atproto_client, testing_mode=False):
    """Fetch new notifications, queue them, and process the queue."""
    try:
        # Get current time for marking notifications as seen
        logger.debug("Getting current time for notification marking...")
        last_seen_at = atproto_client.get_current_time_iso()

        # Fetch ALL notifications using pagination first
        logger.info("Beginning notification fetch with pagination...")
        all_notifications = []
        cursor = None
        page_count = 0
        # Safety limit to prevent infinite loops
        max_pages = bot_config['max_notification_pages']

        logger.info("Fetching all unread notifications...")

        while page_count < max_pages:
            try:
                # Fetch notifications page
                if cursor:
                    notifications_response = atproto_client.app.bsky.notification.list_notifications(
                        params={'cursor': cursor, 'limit': 100}
                    )
                else:
                    notifications_response = atproto_client.app.bsky.notification.list_notifications(
                        params={'limit': 100}
                    )

                page_count += 1
                page_notifications = notifications_response.notifications

                # Count unread notifications in this page
                unread_count = sum(
                    1 for n in page_notifications if not n.is_read and n.reason != "like")
                logger.debug(
                    f"Page {page_count}: {len(page_notifications)} notifications, {unread_count} unread (non-like)")

                # Add all notifications to our list
                all_notifications.extend(page_notifications)

                # Check if we have more pages
                if hasattr(notifications_response, 'cursor') and notifications_response.cursor:
                    cursor = notifications_response.cursor
                    # If this page had no unread notifications, we can stop
                    if unread_count == 0:
                        logger.info(
                            f"No more unread notifications found after {page_count} pages")
                        break
                else:
                    # No more pages
                    logger.info(
                        f"Fetched all notifications across {page_count} pages")
                    break

            except Exception as e:
                error_str = str(e)
                logger.error(
                    f"Error fetching notifications page {page_count}: {e}")

                # Handle specific API errors
                if 'rate limit' in error_str.lower():
                    logger.warning(
                        "Rate limit hit while fetching notifications, will retry next cycle")
                    break
                elif '401' in error_str or 'unauthorized' in error_str.lower():
                    logger.error("Authentication error, re-raising exception")
                    raise
                else:
                    # For other errors, try to continue with what we have
                    logger.warning(
                        "Continuing with notifications fetched so far")
                    break

        # Queue all unread notifications (except likes)
        logger.info("Queuing unread notifications...")
        new_count = 0
        for notification in all_notifications:
            if not notification.is_read and notification.reason != "like":
                if save_notification_to_queue(notification):
                    new_count += 1

        # Mark all notifications as seen immediately after queuing (unless in testing mode)
        if testing_mode:
            logger.info(
                "🧪 TESTING MODE: Skipping marking notifications as seen")
        else:
            if new_count > 0:
                atproto_client.app.bsky.notification.update_seen(
                    {'seen_at': last_seen_at})
                logger.info(
                    f"Queued {new_count} new notifications and marked as seen")
            else:
                logger.debug("No new notifications to queue")

        # Now process the entire queue (old + new notifications)
        load_and_process_queued_notifications(
            void_agent, atproto_client, testing_mode)

    except Exception as e:
        logger.error(f"Error processing notifications: {e}")


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Void Bot - Bluesky autonomous agent')
    parser.add_argument('--test', action='store_true',
                        help='Run in testing mode (no messages sent, queue files preserved)')
    parser.add_argument('--no-git', action='store_true',
                        help='Skip git operations when exporting agent state')
    args = parser.parse_args()

    global TESTING_MODE
    TESTING_MODE = args.test

    # Store no-git flag globally for use in export_agent_state calls
    global SKIP_GIT
    SKIP_GIT = args.no_git

    if TESTING_MODE:
        logger.info("🧪 === RUNNING IN TESTING MODE ===")
        logger.info("   - No messages will be sent to Bluesky")
        logger.info("   - Queue files will not be deleted")
        logger.info("   - Notifications will not be marked as seen")
        print("\n")
    """Main bot loop that continuously monitors for notifications."""
    global start_time
    start_time = time.time()
    logger.info("=== STARTING VOID BOT ===")
    void_agent = initialize_void()
    logger.info(f"Void agent initialized: {void_agent.id}")

    # Check if agent has required tools
    if hasattr(void_agent, 'tools') and void_agent.tools:
        tool_names = [tool.name for tool in void_agent.tools]
        # Check for bluesky-related tools
        bluesky_tools = [name for name in tool_names if 'bluesky' in name.lower(
        ) or 'reply' in name.lower()]
        if not bluesky_tools:
            logger.warning(
                "No Bluesky-related tools found! Agent may not be able to reply.")
    else:
        logger.warning("Agent has no tools registered!")

    # Initialize Bluesky client
    logger.debug("Connecting to Bluesky")
    atproto_client = bsky_utils.default_login()
    logger.info("Connected to Bluesky")

    # Main loop
    logger.info(
        f"Starting notification monitoring, checking every {FETCH_NOTIFICATIONS_DELAY_SEC} seconds")

    cycle_count = 0
    while True:
        try:
            cycle_count += 1
            process_notifications(void_agent, atproto_client, TESTING_MODE)
            # Log cycle completion with stats
            elapsed_time = time.time() - start_time
            total_messages = sum(message_counters.values())
            messages_per_minute = (
                total_messages / elapsed_time * 60) if elapsed_time > 0 else 0

            if total_messages > 0:
                logger.info(
                    f"Cycle {cycle_count} complete. Session totals: {total_messages} messages ({message_counters['mentions']} mentions, {message_counters['replies']} replies) | {messages_per_minute:.1f} msg/min")
            sleep(FETCH_NOTIFICATIONS_DELAY_SEC)

        except KeyboardInterrupt:
            # Final stats
            elapsed_time = time.time() - start_time
            total_messages = sum(message_counters.values())
            messages_per_minute = (
                total_messages / elapsed_time * 60) if elapsed_time > 0 else 0

            logger.info("=== BOT STOPPED BY USER ===")
            logger.info(
                f"📊 Final session stats: {total_messages} total messages processed in {elapsed_time/60:.1f} minutes")
            logger.info(f"   - {message_counters['mentions']} mentions")
            logger.info(f"   - {message_counters['replies']} replies")
            logger.info(f"   - {message_counters['follows']} follows")
            logger.info(
                f"   - {message_counters['reposts_skipped']} reposts skipped")
            logger.info(
                f"   - Average rate: {messages_per_minute:.1f} messages/minute")
            break
        except Exception as e:
            logger.error(f"=== ERROR IN MAIN LOOP CYCLE {cycle_count} ===")
            logger.error(f"Error details: {e}")
            # Wait a bit longer on errors
            logger.info(
                f"Sleeping for {FETCH_NOTIFICATIONS_DELAY_SEC * 2} seconds due to error...")
            sleep(FETCH_NOTIFICATIONS_DELAY_SEC * 2)


if __name__ == "__main__":
    main()
