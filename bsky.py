# Rich imports removed - using simple text formatting
from letta_client import Letta
from bsky_utils import thread_to_yaml_string, extract_images_from_thread
import os
import logging
import json
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, date
from collections import defaultdict
import time
import random
import argparse

from utils import (
    upsert_block,
    upsert_agent
)
from config_loader import get_letta_config, get_config, get_queue_config, get_bluesky_config

import bsky_utils
from tools.blocks import attach_user_blocks, detach_user_blocks
from notification_db import NotificationDB
import scheduled_prompts
from scheduled_prompts import (
    TASK_CONFIGS,
    send_synthesis_message,
    send_mutuals_engagement_message,
    send_feed_engagement_message,
    send_curiosities_exploration_message,
    send_daily_review_message,
    initialize_all_scheduled_tasks,
    reschedule_task_after_execution,
    attach_temporal_blocks,
    detach_temporal_blocks,
)

def build_multimodal_content(text_prompt: str, images: list[dict]) -> list | str:
    """Build multimodal content blocks with text and images.

    Creates content blocks in the format expected by Letta for multimodal messages.
    If no images are provided, returns the plain text string for backwards compatibility.

    Args:
        text_prompt: The text prompt to send
        images: List of image dicts from extract_images_from_thread()

    Returns:
        List of content blocks if images present, otherwise plain text string.
    """
    if not images:
        return text_prompt

    content = [{"type": "text", "text": text_prompt}]

    for img in images:
        url = img.get('fullsize')
        if not url:
            continue

        content.append({
            "type": "image",
            "source": {"type": "url", "url": url}
        })

        # Add alt text as context if present
        alt = img.get('alt', '')
        if alt:
            author = img.get('author_handle', 'unknown')
            content.append({
                "type": "text",
                "text": f"[Image from @{author}, alt text: {alt}]"
            })

    return content


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

# Logging will be configured after argument parsing
logger = None
prompt_logger = None
# Simple text formatting (Rich no longer used)
SHOW_REASONING = False
last_archival_query = "archival memory search"

def log_with_panel(message, title=None, border_color="white"):
    """Log a message with Unicode box-drawing characters"""
    if title:
        # Map old color names to appropriate symbols
        symbol_map = {
            "blue": "⚙",      # Tool calls
            "green": "✓",     # Success/completion
            "yellow": "◆",    # Reasoning
            "red": "✗",       # Errors
            "white": "▶",     # Default/mentions
            "cyan": "✎",      # Posts
        }
        symbol = symbol_map.get(border_color, "▶")
        
        print(f"\n{symbol} {title}")
        print(f"  {'─' * len(title)}")
        # Indent message lines
        for line in message.split('\n'):
            print(f"  {line}")
    else:
        print(message)


# Load Letta configuration from config.yaml (will be initialized later with custom path if provided)
letta_config = None
CLIENT = None

# Notification check delay
FETCH_NOTIFICATIONS_DELAY_SEC = 10  # Check every 10 seconds for faster response

# Check for new notifications every N queue items
CHECK_NEW_NOTIFICATIONS_EVERY_N_ITEMS = 2  # Check more frequently during processing

# Queue paths (will be initialized from config in main())
QUEUE_DIR = None
QUEUE_ERROR_DIR = None
QUEUE_NO_REPLY_DIR = None
PROCESSED_NOTIFICATIONS_FILE = None

# Maximum number of processed notifications to track
MAX_PROCESSED_NOTIFICATIONS = 10000

# Maximum retry attempts for failed notifications
MAX_RETRY_COUNT = 3

# Message tracking counters
message_counters = defaultdict(int)
start_time = time.time()

# Testing mode flag
TESTING_MODE = False

# Skip git operations flag
SKIP_GIT = False

# Database for notification tracking
NOTIFICATION_DB = None

# Scheduled task enabled overrides (set from command line args)
# These override the defaults in TASK_CONFIGS
TASK_ENABLED_OVERRIDES = {}

def export_agent_state(client, agent, skip_git=False):
    """Export agent state to agent_archive/ (timestamped) and agents/ (current)."""
    try:
        # Confirm export with user unless git is being skipped
        if not skip_git:
            response = input("Export agent state to files and stage with git? (y/n): ").lower().strip()
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
        archive_file = os.path.join("agent_archive", f"umbra_{timestamp}.af")
        with open(archive_file, 'w', encoding='utf-8') as f:
            json.dump(agent_data, f, indent=2, ensure_ascii=False)
        
        # Save current agent state
        current_file = os.path.join("agents", "umbra.af")
        with open(current_file, 'w', encoding='utf-8') as f:
            json.dump(agent_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Agent exported to {archive_file} and {current_file}")
        
        # Git add only the current agent file (archive is ignored) unless skip_git is True
        if not skip_git:
            try:
                subprocess.run(["git", "add", current_file], check=True, capture_output=True)
                logger.info("Added current agent file to git staging")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to git add agent file: {e}")
        
    except Exception as e:
        logger.error(f"Failed to export agent: {e}")

def initialize_umbra():
    logger.info("Starting umbra agent initialization...")

    # Get the configured umbra agent by ID
    logger.info("Loading umbra agent from config...")
    agent_id = letta_config['agent_id']
    
    try:
        umbra_agent = CLIENT.agents.retrieve(agent_id=agent_id)
        logger.info(f"Successfully loaded umbra agent: {umbra_agent.name} ({agent_id})")
    except Exception as e:
        logger.error(f"Failed to load umbra agent {agent_id}: {e}")
        logger.error("Please ensure the agent_id in config.yaml is correct")
        raise e
    
    # Export agent state
    logger.info("Exporting agent state...")
    export_agent_state(CLIENT, umbra_agent, skip_git=SKIP_GIT)
    
    # Log agent details
    logger.info(f"Umbra agent details - ID: {umbra_agent.id}")
    logger.info(f"Agent name: {umbra_agent.name}")
    if hasattr(umbra_agent, 'llm_config'):
        logger.info(f"Agent model: {umbra_agent.llm_config.model}")
    if hasattr(umbra_agent, 'project_id') and umbra_agent.project_id:
        logger.info(f"Agent project_id: {umbra_agent.project_id}")
    if hasattr(umbra_agent, 'tools'):
        logger.info(f"Agent has {len(umbra_agent.tools)} tools")
        for tool in umbra_agent.tools[:3]:  # Show first 3 tools
            logger.info(f"  - Tool: {tool.name} (type: {tool.tool_type})")

    return umbra_agent


def process_debounced_thread(umbra_agent, atproto_client, notification_data, queue_filepath=None, testing_mode=False):
    """Process a notification whose debounce period has expired, with full thread context.

    Args:
        umbra_agent: The Letta agent instance
        atproto_client: The AT Protocol client
        notification_data: The notification data dictionary
        queue_filepath: Optional Path object to the queue file
        testing_mode: If True, don't actually send messages

    Returns:
        True: Successfully processed
        False: Failed but retryable
        None: Critical error, move to errors
        "no_reply": Agent chose not to reply
        "ignored": Ignored (blocked user, etc.)
    """
    try:
        # Get thread configuration
        config = get_config()
        threading_config = config.get('threading', {})

        # Extract notification info
        uri = notification_data.get('uri', '')
        author_handle = notification_data.get('author', {}).get('handle', 'unknown')

        logger.info(f"⏰ Processing debounced thread from @{author_handle}")
        logger.info(f"   Notification URI: {uri}")

        # Fetch the complete current thread state from Bluesky
        # Use high depth (25) to ensure we get ALL replies in the thread
        # The notification URI is the post that mentioned umbra - fetch all its replies
        parent_height = threading_config.get('parent_height', 80)
        depth = 25  # High depth to get complete thread including all self-replies

        logger.info(f"   Fetching thread with depth={depth} to capture all replies...")

        try:
            thread = bsky_utils.get_post_thread(atproto_client, uri, parent_height=parent_height, depth=depth)
        except Exception as e:
            logger.error(f"Failed to fetch thread for debounced notification: {e}")
            return False  # Retry later

        if not thread:
            logger.error("Failed to get thread context for debounced notification")
            return False  # Retry later

        # Find the last post in the thread to get its URI and CID for replying
        def find_last_post(node):
            """Recursively find the last (deepest) post in a thread."""
            if not node:
                return None

            last_post = None

            # Check if this node has a post
            if hasattr(node, 'post') and node.post:
                last_post = node.post

            # Check for replies and recursively find the last one
            if hasattr(node, 'replies') and node.replies:
                for reply in node.replies:
                    deeper_post = find_last_post(reply)
                    if deeper_post:
                        last_post = deeper_post

            return last_post

        last_post = None
        last_post_uri = None
        last_post_cid = None

        if hasattr(thread, 'thread'):
            last_post = find_last_post(thread.thread)

        if last_post:
            last_post_uri = last_post.uri if hasattr(last_post, 'uri') else None
            last_post_cid = last_post.cid if hasattr(last_post, 'cid') else None
            last_post_author = last_post.author.handle if hasattr(last_post, 'author') and hasattr(last_post.author, 'handle') else 'unknown'
            logger.info(f"   Last post in thread: {last_post_uri} by @{last_post_author}")

        # Convert thread to YAML (no tree view needed for linear reply chains)
        thread_yaml = thread_to_yaml_string(thread, include_tree_view=False)

        # Clear debounce from database
        if NOTIFICATION_DB:
            NOTIFICATION_DB.clear_debounce(uri)

        # Build prompt for agent with explicit context about this being a complete thread
        reply_instructions = ""
        if last_post_uri and last_post_cid:
            reply_instructions = f"""

TO REPLY TO THE LAST POST IN THIS THREAD:
Use the reply_to_bluesky_post tool with these parameters:
- post_uri: {last_post_uri}
- post_cid: {last_post_cid}

This will ensure your reply goes to the end of the thread, not the beginning."""

        system_message = f"""
This is a debounced thread that you previously marked for later review. The thread has had time to complete, and you're now seeing the full context.

Original notification: You were mentioned in a post from @{author_handle}
Original post URI: {uri}

The complete thread (as it exists now) is provided below. This includes ALL posts the author added after the original mention - the full thread has been fetched from Bluesky.

{thread_yaml}

You may now respond to this thread with full context of all posts.{reply_instructions}""".strip()

        # Send to agent using standard processing
        # But use a special flag to indicate this is a debounced thread
        logger.info(f"Sending debounced thread to agent | prompt: {len(system_message)} chars")

        if testing_mode:
            logger.info("TESTING MODE: Skipping agent call for debounced thread")
            return True

        try:
            # Attach user memory block
            attached_handles = []
            try:
                attach_result = attach_user_blocks([author_handle], umbra_agent)
                attached_handles = [author_handle]
                logger.debug(f"Attach result: {attach_result}")
            except Exception as e:
                logger.warning(f"Failed to attach user blocks: {e}")

            # Call the agent with the complete thread context
            message_response = CLIENT.agents.messages.create(
                agent_id=umbra_agent.id,
                messages=[{"role": "user", "content": system_message}]
            )

            logger.info(f"✓ Successfully received response from Letta API for debounced thread")

            # Extract tool calls from the agent's response
            reply_candidates = []
            tool_call_results = {}  # Map tool_call_id to status
            ignored_notification = False
            ignore_reason = ""
            ignore_category = ""
            direct_reply_posted = False  # Track if reply_to_bluesky_post was called

            # First pass: collect tool return statuses
            for message in message_response.messages:
                # Check for tool_return_message type
                if hasattr(message, 'message_type') and message.message_type == 'tool_return_message':
                    if hasattr(message, 'tool_call_id') and hasattr(message, 'status'):
                        tool_call_id = message.tool_call_id
                        status = message.status
                        if tool_call_id:
                            tool_call_results[tool_call_id] = status

                # Check for ignore_notification tool
                if hasattr(message, 'tool_call_id') and hasattr(message, 'status') and hasattr(message, 'name'):
                    if message.name == 'ignore_notification':
                        if hasattr(message, 'tool_return') and message.status == 'success':
                            result_str = str(message.tool_return)
                            if 'IGNORED_NOTIFICATION::' in result_str:
                                parts = result_str.split('::')
                                if len(parts) >= 3:
                                    ignore_category = parts[1]
                                    ignore_reason = parts[2]
                                    ignored_notification = True
                                    logger.info(f"🚫 Debounced thread ignored - Category: {ignore_category}, Reason: {ignore_reason}")

            # Second pass: extract tool calls
            for message in message_response.messages:
                if hasattr(message, 'tool_call') and message.tool_call:
                    # Collect add_post_to_bluesky_reply_thread tool calls
                    if message.tool_call.name == 'add_post_to_bluesky_reply_thread':
                        tool_call_id = message.tool_call.tool_call_id
                        tool_status = tool_call_results.get(tool_call_id, 'unknown')

                        if tool_status == 'success':
                            try:
                                args = json.loads(message.tool_call.arguments)
                                reply_text = args.get('text', '')
                                reply_lang = args.get('lang', 'en-US')

                                if reply_text:
                                    reply_candidates.append((reply_text, reply_lang))
                                    logger.debug(f"Found successful add_post_to_bluesky_reply_thread: {reply_text[:50]}...")
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse tool call arguments: {e}")

                    # Track reply_to_bluesky_post tool calls (posts directly to Bluesky)
                    elif message.tool_call.name == 'reply_to_bluesky_post':
                        tool_call_id = message.tool_call.tool_call_id
                        tool_status = tool_call_results.get(tool_call_id, 'unknown')

                        if tool_status == 'success':
                            direct_reply_posted = True
                            logger.debug(f"Detected successful reply_to_bluesky_post (posted directly)")

            # Detach user blocks
            if attached_handles:
                try:
                    detach_result = detach_user_blocks(attached_handles, umbra_agent)
                    logger.debug(f"Detach result: {detach_result}")
                except Exception as e:
                    logger.warning(f"Failed to detach user blocks: {e}")

            # Process the extracted tool calls
            if reply_candidates:
                # Build reply thread
                reply_messages = []
                reply_langs = []
                for text, lang in reply_candidates:
                    reply_messages.append(text)
                    reply_langs.append(lang)

                reply_lang = reply_langs[0] if reply_langs else 'en-US'

                logger.debug(f"Found {len(reply_candidates)} add_post_to_bluesky_reply_thread calls")

                # Send the reply(s)
                if testing_mode:
                    logger.info("TESTING MODE: Skipping actual Bluesky post")
                    response = True
                else:
                    if len(reply_messages) == 1:
                        # Single reply
                        cleaned_text = bsky_utils.remove_outside_quotes(reply_messages[0])
                        logger.info(f"Sending single reply to debounced thread: {cleaned_text[:50]}... (lang: {reply_lang})")
                        response = bsky_utils.reply_to_notification(
                            client=atproto_client,
                            notification=notification_data,
                            reply_text=cleaned_text,
                            lang=reply_lang
                        )
                    else:
                        # Multiple replies - threaded
                        cleaned_messages = [bsky_utils.remove_outside_quotes(msg) for msg in reply_messages]
                        logger.info(f"Sending threaded reply to debounced thread with {len(cleaned_messages)} messages (lang: {reply_lang})")
                        response = bsky_utils.reply_with_thread_to_notification(
                            client=atproto_client,
                            notification=notification_data,
                            reply_messages=cleaned_messages,
                            lang=reply_lang
                        )

                # Verify reply was sent successfully
                reply_sent_successfully = False
                if response is not None and response is not False:
                    if isinstance(response, list):
                        if len(response) == len(reply_messages):
                            reply_sent_successfully = True
                    else:
                        reply_sent_successfully = True

                if reply_sent_successfully:
                    logger.info(f"✓ Successfully replied to debounced thread from @{author_handle}")

                    # Delete queue file
                    if queue_filepath and queue_filepath.exists():
                        try:
                            queue_filepath.unlink()
                            logger.debug(f"Deleted queue file: {queue_filepath.name}")
                        except Exception as e:
                            logger.warning(f"Failed to delete queue file: {e}")

                    return True
                else:
                    logger.error(f"Failed to send reply to debounced thread from @{author_handle}")
                    return False

            else:
                # No reply candidates - check other cases
                if ignored_notification:
                    logger.info(f"Debounced thread from @{author_handle} was explicitly ignored (category: {ignore_category})")

                    # Delete queue file
                    if queue_filepath and queue_filepath.exists():
                        try:
                            queue_filepath.unlink()
                            logger.debug(f"Deleted queue file: {queue_filepath.name}")
                        except Exception as e:
                            logger.warning(f"Failed to delete queue file: {e}")

                    return "ignored"

                elif direct_reply_posted:
                    logger.info(f"Direct reply was posted to debounced thread from @{author_handle} via reply_to_bluesky_post")

                    # Delete queue file
                    if queue_filepath and queue_filepath.exists():
                        try:
                            queue_filepath.unlink()
                            logger.debug(f"Deleted queue file: {queue_filepath.name}")
                        except Exception as e:
                            logger.warning(f"Failed to delete queue file: {e}")

                    return True

                else:
                    logger.warning(f"No reply generated for debounced thread from @{author_handle}")

                    # Delete queue file and move to no_reply
                    if queue_filepath and queue_filepath.exists():
                        try:
                            queue_filepath.unlink()
                            logger.debug(f"Deleted queue file: {queue_filepath.name}")
                        except Exception as e:
                            logger.warning(f"Failed to delete queue file: {e}")

                    return "no_reply"

        except Exception as e:
            logger.error(f"Error calling agent for debounced thread: {e}")
            return False  # Retry later

    except Exception as e:
        logger.error(f"Error processing debounced thread: {e}")
        return None  # Critical error


def process_high_traffic_batch(umbra_agent, atproto_client, notification_data, queue_filepath=None, testing_mode=False):
    """Process a batch of high-traffic thread notifications that have been debounced together.

    Args:
        umbra_agent: The Letta agent instance
        atproto_client: The AT Protocol client
        notification_data: The first notification data dictionary (triggers batch processing)
        queue_filepath: Optional Path object to the queue file
        testing_mode: If True, don't actually send messages

    Returns:
        True: Successfully processed
        False: Failed but retryable
        None: Critical error, move to errors
        "no_reply": Agent chose not to reply
        "ignored": Ignored (blocked user, etc.)
    """
    try:
        # Get thread configuration
        config = get_config()
        threading_config = config.get('threading', {})

        # Extract root URI to find all notifications in this batch
        uri = notification_data.get('uri', '')
        record = notification_data.get('record', {})
        root_uri = None

        if record and 'reply' in record and record['reply']:
            reply_info = record['reply']
            if reply_info and isinstance(reply_info, dict):
                root_info = reply_info.get('root', {})
                if root_info:
                    root_uri = root_info.get('uri')

        if not root_uri:
            root_uri = uri

        logger.info(f"⚡ Processing high-traffic thread batch")
        logger.info(f"   Thread root: {root_uri}")

        # Get all debounced notifications for this thread
        if not NOTIFICATION_DB:
            logger.error("Database not available for batch processing")
            return None

        batch_notifications = NOTIFICATION_DB.get_thread_debounced_notifications(root_uri)

        if not batch_notifications:
            logger.warning("No debounced notifications found for batch processing")
            return False

        # If only 1 notification in batch, fall back to normal processing
        # This handles the case where thread activity died down during debounce
        if len(batch_notifications) == 1:
            single_uri = batch_notifications[0]['uri']
            logger.info(f"⚡ High-traffic batch has only 1 notification, falling back to normal processing")
            # Clear high-traffic flags so it processes normally on next cycle
            NOTIFICATION_DB.clear_high_traffic_flags(single_uri)
            return False  # Will be processed normally on next iteration

        # Mark all batch notifications as in_progress to prevent re-queuing
        # This must happen AFTER retrieval (otherwise the query would exclude them)
        for notif in batch_notifications:
            NOTIFICATION_DB.mark_in_progress(notif['uri'])

        logger.info(f"   Found {len(batch_notifications)} debounced notifications in batch")

        # Fetch the complete current thread state from Bluesky
        parent_height = threading_config.get('parent_height', 80)
        depth = threading_config.get('depth', 10)

        logger.info(f"   Fetching thread context (depth={depth})...")

        try:
            thread = bsky_utils.get_post_thread(atproto_client, root_uri, parent_height=parent_height, depth=depth)
        except Exception as e:
            logger.error(f"Failed to fetch thread for high-traffic batch: {e}")
            return False  # Retry later

        if not thread:
            logger.error("Failed to get thread context for high-traffic batch")
            return False  # Retry later

        # Extract all posts from thread
        flattened = bsky_utils.flatten_thread_structure(thread)
        posts = flattened.get('posts', [])
        existing_uris = {p.get('uri') for p in posts}

        # For each notification, fetch its parent chain to ensure we have full context
        # This handles cases where depth limit prevents reaching notification's ancestors
        for notif in batch_notifications:
            notif_uri = notif.get('uri')
            if not notif_uri:
                continue

            # Fetch notification's thread to get its parent chain
            try:
                notif_thread = bsky_utils.get_post_thread(
                    atproto_client,
                    notif_uri,
                    parent_height=20,  # Get up to 20 parents
                    depth=0            # Don't need replies, just parents
                )
                if notif_thread:
                    # Extract posts from notification's thread (includes parents)
                    notif_flattened = bsky_utils.flatten_thread_structure(notif_thread)
                    notif_posts = notif_flattened.get('posts', [])

                    # Add any posts not already in our posts list
                    for p in notif_posts:
                        p_uri = p.get('uri')
                        if p_uri and p_uri not in existing_uris:
                            posts.append(p)
                            existing_uris.add(p_uri)
                            logger.debug(f"   Added missing parent post: {p_uri}")
            except Exception as e:
                logger.warning(f"Failed to fetch parent chain for notification {notif_uri}: {e}")

        # Re-sort posts chronologically after merging
        posts.sort(key=lambda p: p.get('record', {}).get('createdAt', ''))

        # Get batch history to determine what's new vs previously reviewed
        batch_history = NOTIFICATION_DB.get_thread_batch_history(root_uri)
        last_batch_cutoff = batch_history.get('last_batch_newest_post_indexed_at') if batch_history else None

        # Split posts into previously reviewed vs new (for incremental context)
        if last_batch_cutoff:
            previous_posts = [p for p in posts if p.get('record', {}).get('createdAt', '') <= last_batch_cutoff]
            new_posts = [p for p in posts if p.get('record', {}).get('createdAt', '') > last_batch_cutoff]
            logger.info(f"   Incremental batch: {len(previous_posts)} previously reviewed, {len(new_posts)} new posts")
        else:
            previous_posts = []
            new_posts = posts  # First batch - everything is new
            logger.info(f"   First batch for this thread: {len(new_posts)} posts")

        # Create set of notification URIs to identify which posts are notifications
        notification_uris = {notif['uri'] for notif in batch_notifications}

        # Split posts into context (non-notification posts) and notification posts
        context_posts = []
        notification_posts_data = []  # Will match with batch_notifications

        for post in posts:
            if post.get('uri') in notification_uris:
                notification_posts_data.append(post)
            else:
                context_posts.append(post)

        # Further split context by what's new vs previously reviewed
        new_context_posts = [p for p in context_posts if p.get('uri') in {np.get('uri') for np in new_posts}]

        # Build THREAD CONTEXT section
        is_incremental_batch = len(previous_posts) > 0

        if is_incremental_batch:
            # INCREMENTAL BATCH: Show summary of previous + full detail of new
            # Build summary of previous context
            if previous_posts:
                first_post = previous_posts[0]
                first_author = first_post.get('author', {}).get('handle', 'unknown') if isinstance(first_post.get('author'), dict) else 'unknown'
                last_reviewed = batch_history.get('last_batch_processed_at', 'unknown') if batch_history else 'unknown'
                previous_summary = f"""You previously reviewed {len(previous_posts)} posts in this thread.
- Thread started by: @{first_author}
- Last review: {last_reviewed}
- Previous posts will NOT be shown again to save context."""
            else:
                previous_summary = "(No previous context)"

            # Build tree view of new posts (non-notification context posts that are new)
            # Only tree view is needed for context - full metadata is in the NOTIFICATIONS section
            if new_context_posts:
                tree_view = bsky_utils.build_tree_view(new_context_posts)
                new_context_yaml = f"Thread Structure:\n{tree_view}"
            else:
                new_context_yaml = "(No new context posts - only notifications are new)"

            pre_notification_yaml = f"""=== PREVIOUS CONTEXT (already reviewed) ===
{previous_summary}

=== NEW CONTEXT (since last review) ===
{new_context_yaml}"""
        else:
            # FIRST BATCH: Show tree view for context
            # Only tree view is needed for context - full metadata is in the NOTIFICATIONS section
            if context_posts:
                tree_view = bsky_utils.build_tree_view(context_posts)
                pre_notification_yaml = f"Thread Structure:\n{tree_view}"
            else:
                pre_notification_yaml = "(No context posts - notifications start the thread)"

        # Build NOTIFICATIONS section with full text and metadata
        notification_entries = []
        for idx, notif in enumerate(batch_notifications, 1):
            # Find matching post to get full text and complete metadata
            matching_post = next((p for p in notification_posts_data if p.get('uri') == notif['uri']), None)

            if matching_post:
                # Extract full metadata
                uri = matching_post.get('uri', 'unknown')
                cid = matching_post.get('cid', 'unknown')

                # Get author info
                author = matching_post.get('author', {})
                author_handle = author.get('handle', 'unknown') if isinstance(author, dict) else 'unknown'

                # Get FULL text (not truncated)
                record = matching_post.get('record', {})
                full_text = record.get('text', '') if isinstance(record, dict) else ''

                # Get timestamps
                indexed_at = notif.get('indexed_at', 'unknown')  # When umbra received notification
                created_at = record.get('createdAt', 'unknown') if isinstance(record, dict) else 'unknown'  # When post was created

                reason = notif.get('reason', 'unknown')

                # Find preceding posts by same author (for multi-part replies)
                # Look for consecutive parent posts by the same author
                preceding_parts = []
                current_uri = uri
                visited_uris = {current_uri}  # Prevent infinite loops

                # Traverse up through parents to find consecutive posts by same author
                while True:
                    # Find the current post in our posts list
                    current_post = next((p for p in posts if p.get('uri') == current_uri), None)
                    if not current_post:
                        break

                    # Get parent URI from record.reply.parent
                    current_record = current_post.get('record', {})
                    reply_info = current_record.get('reply', {}) if isinstance(current_record, dict) else {}
                    parent_info = reply_info.get('parent', {}) if isinstance(reply_info, dict) else {}
                    parent_uri = parent_info.get('uri') if isinstance(parent_info, dict) else None

                    if not parent_uri or parent_uri in visited_uris:
                        break

                    visited_uris.add(parent_uri)

                    # Find parent post
                    parent_post = next((p for p in posts if p.get('uri') == parent_uri), None)
                    if not parent_post:
                        break

                    # Check if parent is by same author
                    parent_author = parent_post.get('author', {})
                    parent_handle = parent_author.get('handle', '') if isinstance(parent_author, dict) else ''

                    if parent_handle != author_handle:
                        # Different author, stop here
                        break

                    # Add parent to preceding parts
                    parent_record = parent_post.get('record', {})
                    parent_text = parent_record.get('text', '') if isinstance(parent_record, dict) else ''
                    parent_created = parent_record.get('createdAt', 'unknown') if isinstance(parent_record, dict) else 'unknown'
                    preceding_parts.append({
                        'text': parent_text,
                        'createdAt': parent_created
                    })

                    # Continue up the chain
                    current_uri = parent_uri

                # Reverse to get chronological order (oldest first)
                preceding_parts.reverse()

                # Build entry with preceding parts context if present
                preceding_context = ""
                if preceding_parts:
                    preceding_lines = []
                    for part_idx, part in enumerate(preceding_parts, 1):
                        preceding_lines.append(f"  [Part {part_idx} by same author]: \"{part['text']}\" (Posted: {part['createdAt']})")
                    preceding_context = "\n" + "\n".join(preceding_lines) + "\n"

                # Build entry
                entry = f"""[Notification {idx}] @{author_handle} ({reason}) - Received: {indexed_at}{preceding_context}
  Post: "{full_text}"
  URI: {uri}
  CID: {cid}
  Posted: {created_at}"""

                notification_entries.append(entry)
            else:
                # Fallback if post not found in thread
                logger.debug(f"Post not found in thread for notification {uri}, using database fallback")
                author_handle = notif.get('author_handle', 'unknown')
                text = notif.get('text', '(text unavailable)')
                uri = notif.get('uri', 'unknown')
                indexed_at = notif.get('indexed_at', 'unknown')
                reason = notif.get('reason', 'unknown')

                # Extract CID from metadata JSON if available
                cid = 'unknown'
                metadata_str = notif.get('metadata')
                if metadata_str:
                    try:
                        metadata = json.loads(metadata_str)
                        cid = metadata.get('cid', 'unknown')
                    except (json.JSONDecodeError, TypeError):
                        pass

                entry = f"""[Notification {idx}] @{author_handle} ({reason}) - Received: {indexed_at}
  Post: "{text}"
  URI: {uri}
  CID: {cid}
  Posted: {indexed_at}"""

                notification_entries.append(entry)

        notifications_section = "\n\n".join(notification_entries)

        # Build prompt for agent with new two-section format
        separator = "━" * 80
        system_message = f"""
This is a HIGH-TRAFFIC THREAD that generated {len(batch_notifications)} notifications during the debounce period.

{separator}
1. THREAD CONTEXT (Pre-notification history)
{separator}

These posts were in the thread BEFORE you received your notifications:

{pre_notification_yaml}

{separator}
2. NOTIFICATIONS ({len(batch_notifications)} posts you were notified about)
{separator}

{notifications_section}

{separator}
RESPONSE INSTRUCTIONS
{separator}

- Review THREAD CONTEXT to understand the conversation history
- You received {len(batch_notifications)} NOTIFICATIONS - these are the posts that might warrant a response
- Respond to 0-3 notifications depending on what's interesting
- Use reply_to_bluesky_post with the URI and CID from the notification you want to reply to""".strip()

        logger.info(f"Sending high-traffic batch to agent | {len(posts)} posts in thread | {len(batch_notifications)} notifications | prompt: {len(system_message)} chars")

        if testing_mode:
            logger.info("TESTING MODE: Skipping agent call for high-traffic batch")
            return True

        try:
            # Attach user memory blocks for all participants in the thread
            all_handles = set()
            for notif in batch_notifications:
                handle = notif.get('author_handle')
                if handle:
                    all_handles.add(handle)

            attached_handles = []
            if all_handles:
                try:
                    attach_result = attach_user_blocks(list(all_handles), umbra_agent)
                    attached_handles = list(all_handles)
                    logger.debug(f"Attach result: {attach_result}")
                except Exception as e:
                    logger.warning(f"Failed to attach user blocks: {e}")

            # Call the agent with the batch context using streaming
            message_stream = CLIENT.agents.messages.create_stream(
                agent_id=umbra_agent.id,
                messages=[{"role": "user", "content": system_message}],
                stream_tokens=False,  # Step streaming only (faster than token streaming)
                max_steps=100
            )

            # Process response stream (message-based pattern) with timeout detection
            all_messages = []
            last_meaningful_chunk_time = time.time()
            consecutive_ping_count = 0
            STREAMING_TIMEOUT_SECONDS = 300  # 5 minutes without meaningful content = timeout
            MAX_CONSECUTIVE_PINGS = 30  # Allow ~5 minutes of pings at 10s intervals

            for chunk in message_stream:
                # Log condensed chunk info
                if hasattr(chunk, 'message_type'):
                    # Reset timeout tracking for meaningful message types
                    if chunk.message_type not in ['ping', 'usage_statistics', 'stop_reason']:
                        consecutive_ping_count = 0
                        last_meaningful_chunk_time = time.time()

                    if chunk.message_type == 'reasoning_message':
                        logger.debug(f"⚡ Reasoning: {chunk.reasoning[:100]}...")
                    elif chunk.message_type == 'tool_call_message':
                        tool_name = chunk.tool_call.name
                        logger.info(f"⚡ Tool call: {tool_name}")
                    elif chunk.message_type == 'tool_return_message':
                        logger.debug(f"⚡ Tool result: {chunk.name} - {chunk.status}")
                    elif chunk.message_type == 'assistant_message':
                        logger.info(f"⚡ Assistant: {chunk.content[:100]}...")
                    elif chunk.message_type == 'error_message':
                        logger.error(f"⚡ Agent error: {chunk}")
                    elif chunk.message_type == 'ping':
                        # Handle ping messages - track but don't log verbosely
                        consecutive_ping_count += 1
                        logger.debug(f"⚡ Received ping #{consecutive_ping_count}")

                        # Check for timeout conditions
                        time_since_meaningful = time.time() - last_meaningful_chunk_time
                        if time_since_meaningful > STREAMING_TIMEOUT_SECONDS:
                            logger.error(f"⏱️ Streaming timeout: {time_since_meaningful:.0f}s without meaningful content")
                            raise TimeoutError(f"Streaming response timeout after {time_since_meaningful:.0f}s of only ping messages")
                        if consecutive_ping_count >= MAX_CONSECUTIVE_PINGS:
                            logger.error(f"⏱️ Streaming timeout: received {consecutive_ping_count} consecutive ping messages")
                            raise TimeoutError(f"Streaming response timeout after {consecutive_ping_count} consecutive ping messages")
                        # Don't append ping messages to all_messages
                        continue
                    else:
                        # Filter out verbose message types
                        if chunk.message_type not in ['usage_statistics', 'stop_reason']:
                            logger.debug(f"⚡ {chunk.message_type}: {str(chunk)[:100]}...")

                all_messages.append(chunk)
                if str(chunk) == 'done':
                    break

            # Extract tool results and calls for threading
            tool_call_results = {}  # tool_call_id -> status
            tool_return_data = {}   # tool_call_id -> return message content
            reply_candidates = []   # (text, lang) tuples

            # First pass: collect tool return statuses and data
            for message in all_messages:
                if hasattr(message, 'message_type') and message.message_type == 'tool_return_message':
                    tool_call_id = getattr(message, 'tool_call_id', None)
                    status = getattr(message, 'status', None)
                    if tool_call_id:
                        tool_call_results[tool_call_id] = status
                        # Store the full tool_return for reply_to_bluesky_post to extract URI/CID
                        if hasattr(message, 'tool_return'):
                            tool_return_data[tool_call_id] = str(message.tool_return)

            # Second pass: extract tool calls
            last_reply_uri = None  # Track URI from reply_to_bluesky_post for threading
            last_reply_cid = None  # Track CID from reply_to_bluesky_post for threading

            for message in all_messages:
                if hasattr(message, 'message_type') and message.message_type == 'tool_call_message':
                    if not hasattr(message, 'tool_call') or not message.tool_call:
                        continue

                    tool_name = message.tool_call.name
                    tool_call_id = message.tool_call.tool_call_id
                    tool_status = tool_call_results.get(tool_call_id, 'unknown')

                    if tool_status != 'success':
                        continue

                    if tool_name == 'reply_to_bluesky_post':
                        # Extract the reply URI and CID from the tool return
                        tool_return = tool_return_data.get(tool_call_id, '')
                        # Format: "Successfully posted reply: at://... (CID: ...)"
                        if 'Successfully posted reply:' in tool_return:
                            uri_match = re.search(r'at://[^\s]+', tool_return)
                            cid_match = re.search(r'\(CID: ([^)]+)\)', tool_return)
                            if uri_match and cid_match:
                                last_reply_uri = uri_match.group(0)
                                last_reply_cid = cid_match.group(1)
                                logger.debug(f"⚡ Captured reply for threading: {last_reply_uri}")

                    elif tool_name == 'add_post_to_bluesky_reply_thread':
                        try:
                            args = json.loads(message.tool_call.arguments)
                            reply_text = args.get('text', '')
                            reply_lang = args.get('lang', 'en-US')

                            if reply_text:
                                reply_candidates.append((reply_text, reply_lang))
                                logger.debug(f"⚡ Found add_post_to_bluesky_reply_thread: {reply_text[:50]}...")
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse tool call arguments: {e}")

            # Post the collected add_post_to_bluesky_reply_thread replies
            if reply_candidates:
                reply_messages_list = [text for text, lang in reply_candidates]
                reply_lang = reply_candidates[0][1] if reply_candidates else 'en-US'
                cleaned_messages = [bsky_utils.remove_outside_quotes(msg) for msg in reply_messages_list]

                logger.info(f"⚡ Posting {len(cleaned_messages)} threaded posts from high-traffic batch")

                if last_reply_uri and last_reply_cid:
                    # Chain off the previously posted reply
                    logger.debug(f"⚡ Chaining thread off reply: {last_reply_uri}")
                    # Create a synthetic notification for the reply we just posted
                    synthetic_notif = {
                        'uri': last_reply_uri,
                        'cid': last_reply_cid,
                        'record': {}  # No reply info needed since this IS the new thread head
                    }
                    if len(cleaned_messages) == 1:
                        response = bsky_utils.reply_to_notification(
                            client=atproto_client,
                            notification=synthetic_notif,
                            reply_text=cleaned_messages[0],
                            lang=reply_lang
                        )
                    else:
                        response = bsky_utils.reply_with_thread_to_notification(
                            client=atproto_client,
                            notification=synthetic_notif,
                            reply_messages=cleaned_messages,
                            lang=reply_lang
                        )
                else:
                    # No prior reply, use first notification as parent
                    first_notif = batch_notifications[0]
                    if len(cleaned_messages) == 1:
                        response = bsky_utils.reply_to_notification(
                            client=atproto_client,
                            notification=first_notif,
                            reply_text=cleaned_messages[0],
                            lang=reply_lang
                        )
                    else:
                        response = bsky_utils.reply_with_thread_to_notification(
                            client=atproto_client,
                            notification=first_notif,
                            reply_messages=cleaned_messages,
                            lang=reply_lang
                        )

                if response:
                    logger.info(f"⚡ Successfully posted {len(cleaned_messages)} threaded replies")
                else:
                    logger.error(f"⚡ Failed to post threaded replies")

            # Detach user blocks
            if attached_handles:
                try:
                    detach_result = detach_user_blocks(attached_handles, umbra_agent)
                    logger.debug(f"Detach result: {detach_result}")
                except Exception as e:
                    logger.warning(f"Failed to detach user blocks: {e}")

            # Mark ALL batch notifications as processed and clear debounces
            # This is critical: without marking as processed, other notifications in the batch
            # would be processed individually on the next cycle after debounce flags are cleared
            batch_uris = [notif['uri'] for notif in batch_notifications]
            for batch_uri in batch_uris:
                NOTIFICATION_DB.mark_processed(batch_uri, status='processed')
            logger.info(f"⚡ Marked {len(batch_uris)} notifications as processed")

            # Clear debounce metadata for this thread
            cleared_count = NOTIFICATION_DB.clear_batch_debounce(root_uri)
            logger.info(f"⚡ Cleared {cleared_count} debounces after successful processing")

            # Transition thread to COOLDOWN state
            config = get_config()
            time_window = config.get('threading', {}).get('high_traffic_detection', {}).get('time_window_minutes', 60)
            cooldown_until = (datetime.now() + timedelta(minutes=time_window)).isoformat()
            NOTIFICATION_DB.set_thread_cooldown(root_uri, cooldown_until)
            logger.info(f"⏳ Thread entering cooldown until {cooldown_until}")

            # Update batch history for incremental context in future batches
            # Store the newest post timestamp so next batch only shows new content
            if posts:
                newest_post = posts[-1]  # Already sorted chronologically
                newest_indexed_at = newest_post.get('record', {}).get('createdAt', '')
                if newest_indexed_at:
                    NOTIFICATION_DB.update_thread_batch_history(
                        root_uri,
                        processed_at=datetime.now().isoformat(),
                        newest_post_indexed_at=newest_indexed_at
                    )
                    logger.info(f"📝 Updated batch history (newest post: {newest_indexed_at})")

            logger.info(f"✓ High-traffic batch processed successfully")

            # Delete ALL queue files for this batch (not just the triggering one)
            # Queue files contain URI hashes, so we need to find them by content
            deleted_count = 0
            batch_uri_set = set(batch_uris)
            for qfile in QUEUE_DIR.glob("*.json"):
                if qfile.name == "processed_notifications.json":
                    continue
                try:
                    with open(qfile, 'r') as f:
                        qdata = json.load(f)
                    if qdata.get('uri') in batch_uri_set:
                        qfile.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted queue file for batch notification: {qfile.name}")
                except Exception as e:
                    logger.warning(f"Failed to check/delete queue file {qfile.name}: {e}")

            logger.info(f"⚡ Deleted {deleted_count} queue files for batch")

            return True

        except Exception as e:
            logger.error(f"Error calling agent for high-traffic batch: {e}")
            return False  # Retry later

    except Exception as e:
        logger.error(f"Error processing high-traffic batch: {e}")
        return None  # Critical error


def process_mention(umbra_agent, atproto_client, notification_data, queue_filepath=None, testing_mode=False):
    """Process a mention and generate a reply using the Letta agent.
    
    Args:
        umbra_agent: The Letta agent instance
        atproto_client: The AT Protocol client
        notification_data: The notification data dictionary
        queue_filepath: Optional Path object to the queue file (for cleanup on halt)
    
    Returns:
        True: Successfully processed, remove from queue
        False: Failed but retryable, keep in queue
        None: Failed with non-retryable error, move to errors directory
        "no_reply": No reply was generated, move to no_reply directory
    """
    import uuid
    
    # Generate correlation ID for tracking this notification through the pipeline
    correlation_id = str(uuid.uuid4())[:8]
    
    try:
        logger.info(f"[{correlation_id}] Starting process_mention", extra={
            'correlation_id': correlation_id,
            'notification_type': type(notification_data).__name__
        })
        
        # Handle both dict and object inputs for backwards compatibility
        if isinstance(notification_data, dict):
            uri = notification_data['uri']
            mention_text = notification_data.get('record', {}).get('text', '')
            author_handle = notification_data['author']['handle']
            author_name = notification_data['author'].get('display_name') or author_handle
        else:
            # Legacy object access
            uri = notification_data.uri
            mention_text = notification_data.record.text if hasattr(notification_data.record, 'text') else ""
            author_handle = notification_data.author.handle
            author_name = notification_data.author.display_name or author_handle
        
        logger.info(f"[{correlation_id}] Processing mention from @{author_handle}", extra={
            'correlation_id': correlation_id,
            'author_handle': author_handle,
            'author_name': author_name,
            'mention_uri': uri,
            'mention_text_length': len(mention_text),
            'mention_preview': mention_text[:100] if mention_text else ''
        })

        # Retrieve the entire thread associated with the mention
        try:
            thread = atproto_client.app.bsky.feed.get_post_thread({
                'uri': uri,
                'parent_height': 40,
                'depth': 10
            })
        except Exception as e:
            error_str = str(e)
            # Check if this is a NotFound error
            if 'NotFound' in error_str or 'Post not found' in error_str:
                logger.warning(f"Post not found for URI {uri}, removing from queue")
                return True  # Return True to remove from queue
            else:
                # Re-raise other errors
                logger.error(f"Error fetching thread: {e}")
                raise

        # Find the last consecutive post by the same author in the direct reply chain
        last_consecutive_post = None
        is_using_last_consecutive = False
        if hasattr(thread, 'thread') and thread.thread:
            last_consecutive_post = bsky_utils.find_last_consecutive_post_in_chain(
                thread.thread,
                author_handle
            )

            if last_consecutive_post:
                last_uri, last_cid, last_text = last_consecutive_post
                # Check if it's different from the mention post (i.e., there are consecutive posts)
                if last_uri != uri:
                    # Save original notification URI before updating
                    original_mention_uri = uri
                    logger.info(f"[{correlation_id}] Found last consecutive post in chain:", extra={
                        'correlation_id': correlation_id,
                        'mention_uri': original_mention_uri,
                        'last_consecutive_uri': last_uri,
                        'consecutive_posts': 'yes'
                    })
                    # Update to use last consecutive post's metadata
                    uri = last_uri
                    post_cid = last_cid
                    mention_text = last_text
                    is_using_last_consecutive = True

                    # IMPORTANT: Update notification_data dict so reply functions use the correct URI/CID
                    if isinstance(notification_data, dict):
                        notification_data['uri'] = last_uri
                        notification_data['cid'] = last_cid
                        # Also update the text in the record if it exists
                        if 'record' in notification_data and isinstance(notification_data['record'], dict):
                            notification_data['record']['text'] = last_text
                    else:
                        # For object-based notification data, update attributes
                        notification_data.uri = last_uri
                        notification_data.cid = last_cid
                        if hasattr(notification_data, 'record') and hasattr(notification_data.record, 'text'):
                            notification_data.record.text = last_text

                    # Mark the last consecutive post as processed to prevent duplicate processing
                    # This handles the case where both posts A (1/2) and B (2/2) are notifications
                    # We're processing A but replying to B, so we should mark B as processed too
                    if NOTIFICATION_DB:
                        logger.debug(f"[{correlation_id}] Marking last consecutive post as processed to prevent duplicate: {last_uri}")
                        NOTIFICATION_DB.mark_processed(last_uri, status='processed')
                else:
                    logger.debug(f"[{correlation_id}] No consecutive posts found (mention is last post)")
            else:
                logger.debug(f"[{correlation_id}] No consecutive posts found in chain")

        # Extract images from thread before YAML conversion (for multimodal messages)
        thread_images = extract_images_from_thread(thread, max_images=8)
        if thread_images:
            logger.debug(f"[{correlation_id}] Extracted {len(thread_images)} images from thread")

        # Get thread context as YAML string
        logger.debug("Converting thread to YAML string")
        try:
            thread_context = thread_to_yaml_string(thread, include_tree_view=False)
            logger.debug(f"Thread context generated, length: {len(thread_context)} characters")
            
            # Check if #umbrastop appears anywhere in the thread
            if "#umbrastop" in thread_context.lower():
                logger.info("Found #umbrastop in thread context, skipping this mention")
                return True  # Return True to remove from queue
            
            # Also check the mention text directly
            if "#umbrastop" in mention_text.lower():
                logger.info("Found #umbrastop in mention text, skipping this mention")
                return True  # Return True to remove from queue
            
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
                logger.debug(f"Thread structure generated ({len(thread_context)} chars)")
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
        # Note: post_cid and uri may have been updated to the last consecutive post
        # Extract cid for the notification if we're not using the last consecutive post
        if not is_using_last_consecutive:
            if isinstance(notification_data, dict):
                post_cid = notification_data.get('cid', '')
            else:
                post_cid = getattr(notification_data, 'cid', '')

        # Check if debouncing is enabled
        config = get_config()
        threading_config = config.get('threading', {})
        debounce_enabled = threading_config.get('debounce_enabled', False)
        debounce_seconds = threading_config.get('debounce_seconds', 600)

        # Build base prompt with different wording based on whether we're using last consecutive post
        if is_using_last_consecutive:
            post_description = "LAST POST IN CONSECUTIVE CHAIN (the post you're responding to)"
            context_note = "The YAML above shows the complete conversation thread. The metadata below points to the LAST POST in the consecutive chain by this author, not the first mention. This allows you to see and respond to their complete thought."
        else:
            post_description = "MOST RECENT POST (the mention you're responding to)"
            context_note = "The YAML above shows the complete conversation thread. The most recent post is the one mentioned above that you should respond to, but use the full thread context to understand the conversation flow."

        prompt = f"""You received a mention on Bluesky from @{author_handle} ({author_name or author_handle}).

{post_description}:
"{mention_text}"

POST METADATA:
- URI: {uri}
- CID: {post_cid}

FULL THREAD CONTEXT:
```yaml
{thread_context}
```

{context_note}

Carefully review the message and use your archival_memory_search and web_search to find additional context if relevant. 

If you choose to reply, use the add_post_to_bluesky_reply_thread tool.
- Each call creates one post (max 300 characters)
- You may use multiple calls to create a thread if needed.

If you want to like this post, use the like_bluesky_post tool with the URI and CID shown above. You may also reply to the post after liking it.

USER BLOCKS: If the "user_{author_handle}" block is empty or minimal, add any relevant information about their identity to the "user_{author_handle}" block. Copy any existing details about the user from umbra_humans to the "user_{author_handle}" block."""

        # Add debounce capability information if enabled
        if debounce_enabled:
            debounce_minutes = debounce_seconds // 60
            prompt += f"""

THREAD DEBOUNCING: If this looks like an incomplete multi-post thread, call debounce_thread(notification_uri="{uri}") to wait {debounce_minutes}min for completion before responding."""

        # Finalize prompt
        prompt = prompt

        # Extract all handles from notification and thread data
        all_handles = set()
        all_handles.update(extract_handles_from_data(notification_data))
        all_handles.update(extract_handles_from_data(thread.model_dump()))
        unique_handles = list(all_handles)
        
        logger.debug(f"Found {len(unique_handles)} unique handles in thread: {unique_handles}")

        # Attach user blocks before agent call
        attached_handles = []
        if unique_handles:
            try:
                logger.debug(f"Attaching user blocks for handles: {unique_handles}")
                attach_result = attach_user_blocks(unique_handles, umbra_agent)
                attached_handles = unique_handles  # Track successfully attached handles
                logger.debug(f"Attach result: {attach_result}")
            except Exception as attach_error:
                logger.warning(f"Failed to attach user blocks: {attach_error}")
                # Continue without user blocks rather than failing completely

        # Get response from Letta agent
        # Format with Unicode characters
        title = f"MENTION FROM @{author_handle}"
        print(f"\n▶ {title}")
        print(f"  {'═' * len(title)}")
        # Indent the mention text
        for line in mention_text.split('\n'):
            print(f"  {line}")
        
        # Log prompt details to separate logger
        prompt_logger.debug(f"Full prompt being sent:\n{prompt}")
        
        # Log concise prompt info to main logger
        thread_handles_count = len(unique_handles)
        prompt_char_count = len(prompt)
        logger.debug(f"Sending to LLM: @{author_handle} mention | msg: \"{mention_text[:50]}...\" | context: {len(thread_context)} chars, {thread_handles_count} users | prompt: {prompt_char_count} chars")

        try:
            # Build multimodal content if images are present
            content = build_multimodal_content(prompt, thread_images)
            if thread_images:
                logger.info(f"[{correlation_id}] Sending multimodal message with {len(thread_images)} image(s)")

            # Use streaming to avoid 524 timeout errors
            message_stream = CLIENT.agents.messages.create_stream(
                agent_id=umbra_agent.id,
                messages=[{"role": "user", "content": content}],
                stream_tokens=False,  # Step streaming only (faster than token streaming)
                max_steps=100
            )

            # Collect the streaming response with timeout detection
            all_messages = []
            last_meaningful_chunk_time = time.time()
            consecutive_ping_count = 0
            STREAMING_TIMEOUT_SECONDS = 300  # 5 minutes without meaningful content = timeout
            MAX_CONSECUTIVE_PINGS = 30  # Allow ~5 minutes of pings at 10s intervals

            for chunk in message_stream:
                # Log condensed chunk info
                if hasattr(chunk, 'message_type'):
                    # Reset timeout tracking for meaningful message types
                    if chunk.message_type not in ['ping', 'usage_statistics', 'stop_reason']:
                        consecutive_ping_count = 0
                        last_meaningful_chunk_time = time.time()

                    if chunk.message_type == 'reasoning_message':
                        # Show full reasoning without truncation
                        if SHOW_REASONING:
                            # Format with Unicode characters
                            print("\n◆ Reasoning")
                            print("  ─────────")
                            # Indent reasoning lines
                            for line in chunk.reasoning.split('\n'):
                                print(f"  {line}")
                        else:
                            # Default log format (only when --reasoning is used due to log level)
                            # Format with Unicode characters
                            print("\n◆ Reasoning")
                            print("  ─────────")
                            # Indent reasoning lines
                            for line in chunk.reasoning.split('\n'):
                                print(f"  {line}")
                        
                    elif chunk.message_type == 'tool_call_message':
                        # Parse tool arguments for better display
                        tool_name = chunk.tool_call.name

                        try:
                            args = json.loads(chunk.tool_call.arguments)
                            # Format based on tool type
                            if tool_name in ['add_post_to_bluesky_reply_thread', 'bluesky_reply']:
                                # Extract the text being posted
                                text = args.get('text', '')
                                if text:
                                    # Format with Unicode characters
                                    print("\n✎ Bluesky Post")
                                    print("  ────────────")
                                    # Indent post text
                                    for line in text.split('\n'):
                                        print(f"  {line}")
                                else:
                                    log_with_panel(chunk.tool_call.arguments[:150] + "...", f"Tool call: {tool_name}", "blue")
                            elif tool_name == 'archival_memory_search':
                                query = args.get('query', 'unknown')
                                global last_archival_query
                                last_archival_query = query
                                log_with_panel(f"query: \"{query}\"", f"Tool call: {tool_name}", "blue")
                            elif tool_name == 'archival_memory_insert':
                                content = args.get('content', '')
                                # Show the full content being inserted
                                log_with_panel(content, f"Tool call: {tool_name}", "blue")
                            elif tool_name == 'update_block':
                                label = args.get('label', 'unknown')
                                value_preview = str(args.get('value', ''))[:50] + "..." if len(str(args.get('value', ''))) > 50 else str(args.get('value', ''))
                                log_with_panel(f"{label}: \"{value_preview}\"", f"Tool call: {tool_name}", "blue")
                            else:
                                # Generic display for other tools
                                args_str = ', '.join(f"{k}={v}" for k, v in args.items() if k != 'request_heartbeat')
                                if len(args_str) > 150:
                                    args_str = args_str[:150] + "..."
                                log_with_panel(args_str, f"Tool call: {tool_name}", "blue")
                        except:
                            # Fallback to original format if parsing fails
                            log_with_panel(chunk.tool_call.arguments[:150] + "...", f"Tool call: {tool_name}", "blue")
                    elif chunk.message_type == 'tool_return_message':
                        # Enhanced tool result logging
                        tool_name = chunk.name
                        status = chunk.status
                        
                        if status == 'success':
                            # Try to show meaningful result info based on tool type
                            if hasattr(chunk, 'tool_return') and chunk.tool_return:
                                result_str = str(chunk.tool_return)
                                if tool_name == 'archival_memory_search':
                                    
                                    try:
                                        # Handle both string and list formats
                                        if isinstance(chunk.tool_return, str):
                                            # The string format is: "([{...}, {...}], count)"
                                            # We need to extract just the list part
                                            if chunk.tool_return.strip():
                                                # Find the list part between the first [ and last ]
                                                start_idx = chunk.tool_return.find('[')
                                                end_idx = chunk.tool_return.rfind(']')
                                                if start_idx != -1 and end_idx != -1:
                                                    list_str = chunk.tool_return[start_idx:end_idx+1]
                                                    # Use ast.literal_eval since this is Python literal syntax, not JSON
                                                    import ast
                                                    results = ast.literal_eval(list_str)
                                                else:
                                                    logger.warning("Could not find list in archival_memory_search result")
                                                    results = []
                                            else:
                                                logger.warning("Empty string returned from archival_memory_search")
                                                results = []
                                        else:
                                            # If it's already a list, use directly
                                            results = chunk.tool_return
                                        
                                        log_with_panel(f"Found {len(results)} memory entries", f"Tool result: {tool_name} ✓", "green")
                                        
                                        # Use the captured search query from the tool call
                                        search_query = last_archival_query
                                        
                                        # Combine all results into a single text block
                                        content_text = ""
                                        for i, entry in enumerate(results, 1):
                                            timestamp = entry.get('timestamp', 'N/A')
                                            content = entry.get('content', '')
                                            content_text += f"[{i}/{len(results)}] {timestamp}\n{content}\n\n"
                                        
                                        # Format with Unicode characters
                                        title = f"{search_query} ({len(results)} results)"
                                        print(f"\n⚙ {title}")
                                        print(f"  {'─' * len(title)}")
                                        # Indent content text
                                        for line in content_text.strip().split('\n'):
                                            print(f"  {line}")
                                        
                                    except Exception as e:
                                        logger.error(f"Error formatting archival memory results: {e}")
                                        log_with_panel(result_str[:100] + "...", f"Tool result: {tool_name} ✓", "green")
                                elif tool_name == 'add_post_to_bluesky_reply_thread':
                                    # Just show success for bluesky posts, the text was already shown in tool call
                                    log_with_panel("Post queued successfully", f"Bluesky Post ✓", "green")
                                elif tool_name == 'archival_memory_insert':
                                    # Skip archival memory insert results (always returns None)
                                    pass
                                elif tool_name == 'update_block':
                                    log_with_panel("Memory block updated", f"Tool result: {tool_name} ✓", "green")
                                else:
                                    # Generic success with preview
                                    preview = result_str[:100] + "..." if len(result_str) > 100 else result_str
                                    log_with_panel(preview, f"Tool result: {tool_name} ✓", "green")
                            else:
                                log_with_panel("Success", f"Tool result: {tool_name} ✓", "green")
                        elif status == 'error':
                            # Show error details
                            if tool_name == 'add_post_to_bluesky_reply_thread':
                                error_str = str(chunk.tool_return) if hasattr(chunk, 'tool_return') and chunk.tool_return else "Error occurred"
                                log_with_panel(error_str, f"Bluesky Post ✗", "red")
                            elif tool_name == 'archival_memory_insert':
                                # Skip archival memory insert errors too
                                pass
                            else:
                                error_preview = ""
                                if hasattr(chunk, 'tool_return') and chunk.tool_return:
                                    error_str = str(chunk.tool_return)
                                    error_preview = error_str[:100] + "..." if len(error_str) > 100 else error_str
                                    log_with_panel(f"Error: {error_preview}", f"Tool result: {tool_name} ✗", "red")
                                else:
                                    log_with_panel("Error occurred", f"Tool result: {tool_name} ✗", "red")
                        else:
                            logger.info(f"Tool result: {tool_name} - {status}")
                    elif chunk.message_type == 'assistant_message':
                        # Format with Unicode characters
                        print("\n▶ Assistant Response")
                        print("  ──────────────────")
                        # Indent response text
                        for line in chunk.content.split('\n'):
                            print(f"  {line}")
                    elif chunk.message_type == 'error_message':
                        # Agent returned an error - log it prominently
                        if hasattr(chunk, 'content') and chunk.content:
                            logger.error(f"❌ Agent error: {chunk.content}")
                            log_with_panel(chunk.content, "Agent Error", "red")
                        else:
                            logger.error(f"❌ Agent error (no details provided)")
                            logger.debug(f"Full error object: {chunk}")
                    elif chunk.message_type == 'ping':
                        # Handle ping messages - track but don't log verbosely
                        consecutive_ping_count += 1
                        logger.debug(f"Received ping #{consecutive_ping_count}")

                        # Check for timeout conditions
                        time_since_meaningful = time.time() - last_meaningful_chunk_time
                        if time_since_meaningful > STREAMING_TIMEOUT_SECONDS:
                            logger.error(f"⏱️ Streaming timeout: {time_since_meaningful:.0f}s without meaningful content")
                            raise TimeoutError(f"Streaming response timeout after {time_since_meaningful:.0f}s of only ping messages")
                        if consecutive_ping_count >= MAX_CONSECUTIVE_PINGS:
                            logger.error(f"⏱️ Streaming timeout: received {consecutive_ping_count} consecutive ping messages")
                            raise TimeoutError(f"Streaming response timeout after {consecutive_ping_count} consecutive ping messages")
                        # Don't append ping messages to all_messages
                        continue
                    else:
                        # Filter out verbose message types
                        if chunk.message_type not in ['usage_statistics', 'stop_reason']:
                            logger.info(f"{chunk.message_type}: {str(chunk)[:150]}...")
                else:
                    logger.info(f"📦 Stream status: {chunk}")
                    # Reset timeout tracking for chunks without message_type
                    consecutive_ping_count = 0
                    last_meaningful_chunk_time = time.time()

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
                        logger.error(f"Response JSON: {api_error.response.json()}")
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
                    logger.error("413 Payload Too Large - moving to errors directory")
                    return None  # Move to errors directory - payload is too large to ever succeed
                elif api_error.status_code == 524:
                    logger.error("524 error - timeout from Cloudflare, will retry later")
                    return False  # Keep in queue for retry
            
            # Check if error indicates we should remove from queue
            if 'status_code: 413' in error_str or 'Payload Too Large' in error_str:
                logger.warning("Payload too large error, moving to errors directory")
                return None  # Move to errors directory - cannot be fixed by retry
            elif 'status_code: 524' in error_str:
                logger.warning("524 timeout error, keeping in queue for retry")
                return False  # Keep in queue for retry
            elif isinstance(api_error, TimeoutError):
                logger.warning("Streaming timeout error, keeping in queue for retry")
                return False  # Keep in queue for retry

            raise

        # Log successful response
        logger.info(f"✓ Successfully received response from Letta API for @{author_handle}")
        logger.debug(f"Number of messages in response: {len(message_response.messages) if hasattr(message_response, 'messages') else 'N/A'}")
        logger.debug(f"Mention URI: {uri}")

        # Extract successful add_post_to_bluesky_reply_thread tool calls from the agent's response
        reply_candidates = []
        tool_call_results = {}  # Map tool_call_id to status
        flagged_memories = []  # Track memories flagged for deletion
        direct_reply_posted = False  # Track if reply_to_bluesky_post was called successfully
        agent_error_occurred = False  # Track if agent returned error_message
        agent_error_details = None  # Store error content if available

        logger.debug(f"Processing {len(message_response.messages)} response messages...")
        
        # First pass: collect tool return statuses
        ignored_notification = False
        ignore_reason = ""
        ignore_category = ""

        for message in message_response.messages:
            # Debug: log message type and attributes
            msg_type = getattr(message, 'message_type', 'NO_MESSAGE_TYPE')
            logger.debug(f"Message type: {msg_type}")

            # Check for error_message type
            if hasattr(message, 'message_type') and message.message_type == 'error_message':
                agent_error_occurred = True
                if hasattr(message, 'content') and message.content:
                    agent_error_details = message.content
                    logger.error(f"Error detected in message processing: {message.content}")
                else:
                    logger.error(f"Error detected in message processing (no details)")
                    logger.debug(f"Full error message object: {message}")

            # Enhanced debug for tool-related messages
            if hasattr(message, 'message_type') and 'tool' in message.message_type.lower():
                logger.debug(f"  🔍 Tool message found: {message.message_type}")
                logger.debug(f"  Available attributes: {[attr for attr in dir(message) if not attr.startswith('_')]}")
                logger.debug(f"  tool_returns: {getattr(message, 'tool_returns', 'NOT_FOUND')}")
                logger.debug(f"  tool_call_id: {getattr(message, 'tool_call_id', 'NOT_FOUND')}")
                logger.debug(f"  status: {getattr(message, 'status', 'NOT_FOUND')}")
                if hasattr(message, 'tool_returns'):
                    logger.debug(f"  tool_returns type: {type(message.tool_returns)}")
                    logger.debug(f"  tool_returns length: {len(message.tool_returns) if message.tool_returns else 0}")

            # Check for tool_return_message type (per official Letta API docs)
            if hasattr(message, 'message_type') and message.message_type == 'tool_return_message':
                # Primary: Use deprecated message-level fields (simpler and working)
                if hasattr(message, 'tool_call_id') and hasattr(message, 'status'):
                    tool_call_id = message.tool_call_id
                    status = message.status

                    if tool_call_id:
                        tool_call_results[tool_call_id] = status
                        logger.debug(f"Tool result: {tool_call_id} -> {status}")

                # Alternative: Parse tool_returns array (list of dicts, not objects)
                elif hasattr(message, 'tool_returns') and message.tool_returns:
                    for tool_ret in message.tool_returns:
                        # tool_returns is a list of DICTS, not objects - use dict access
                        tool_call_id = tool_ret.get('tool_call_id') if isinstance(tool_ret, dict) else None
                        status = tool_ret.get('status', 'unknown') if isinstance(tool_ret, dict) else 'unknown'

                        if tool_call_id:
                            tool_call_results[tool_call_id] = status
                            logger.debug(f"Tool result (from array): {tool_call_id} -> {status}")

            # Check for ignore_notification tool
            if hasattr(message, 'tool_call_id') and hasattr(message, 'status') and hasattr(message, 'name'):
                if message.name == 'ignore_notification':
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
                                logger.info(f"🚫 Notification ignored - Category: {ignore_category}, Reason: {ignore_reason}")
                elif message.name == 'bluesky_reply':
                    logger.error("DEPRECATED TOOL DETECTED: bluesky_reply is no longer supported!")
                    logger.error("Please use add_post_to_bluesky_reply_thread instead.")
                    logger.error("Update the agent's tools using register_tools.py")
                    # Export agent state before terminating
                    export_agent_state(CLIENT, umbra_agent, skip_git=SKIP_GIT)
                    logger.info("=== BOT TERMINATED DUE TO DEPRECATED TOOL USE ===")
                    exit(1)
        
        # Second pass: process messages and check for successful tool calls
        for i, message in enumerate(message_response.messages, 1):
            # Log concise message info instead of full object
            msg_type = getattr(message, 'message_type', 'unknown')
            if hasattr(message, 'reasoning') and message.reasoning:
                logger.debug(f"  {i}. {msg_type}: {message.reasoning[:100]}...")
            elif hasattr(message, 'tool_call') and message.tool_call:
                tool_name = message.tool_call.name
                logger.debug(f"  {i}. {msg_type}: {tool_name}")
            elif hasattr(message, 'tool_return'):
                tool_name = getattr(message, 'name', 'unknown_tool')
                return_preview = str(message.tool_return)[:100] if message.tool_return else "None"
                status = getattr(message, 'status', 'unknown')
                logger.debug(f"  {i}. {msg_type}: {tool_name} -> {return_preview}... (status: {status})")
            elif hasattr(message, 'text'):
                logger.debug(f"  {i}. {msg_type}: {message.text[:100]}...")
            else:
                logger.debug(f"  {i}. {msg_type}: <no content>")

            # Check for halt_activity tool call
            if hasattr(message, 'tool_call') and message.tool_call:
                if message.tool_call.name == 'halt_activity':
                    logger.info("🛑 HALT_ACTIVITY TOOL CALLED - TERMINATING BOT")
                    try:
                        args = json.loads(message.tool_call.arguments)
                        reason = args.get('reason', 'Agent requested halt')
                        logger.info(f"Halt reason: {reason}")
                    except:
                        logger.info("Halt reason: <unable to parse>")
                    
                    # Delete the queue file before terminating
                    if queue_filepath and queue_filepath.exists():
                        queue_filepath.unlink()
                        logger.info(f"Deleted queue file: {queue_filepath.name}")
                        
                        # Also mark as processed to avoid reprocessing
                        if NOTIFICATION_DB:
                            NOTIFICATION_DB.mark_processed(notification_data.get('uri', ''), status='processed')
                        else:
                            processed_uris = load_processed_notifications()
                            processed_uris.add(notification_data.get('uri', ''))
                            save_processed_notifications(processed_uris)
                    
                    # Export agent state before terminating
                    export_agent_state(CLIENT, umbra_agent, skip_git=SKIP_GIT)
                    
                    # Exit the program
                    logger.info("=== BOT TERMINATED BY AGENT ===")
                    exit(0)

            # Check for debounce_thread tool call
            if hasattr(message, 'tool_call') and message.tool_call:
                if message.tool_call.name == 'debounce_thread':
                    logger.info("⏸️  DEBOUNCE_THREAD TOOL CALLED")
                    try:
                        from datetime import datetime, timedelta

                        args = json.loads(message.tool_call.arguments)
                        debounce_uri = args.get('notification_uri', '')
                        debounce_seconds = args.get('debounce_seconds', 600)
                        debounce_reason = args.get('reason', 'incomplete_thread')

                        logger.info(f"   URI: {debounce_uri}")
                        logger.info(f"   Wait: {debounce_seconds}s ({debounce_seconds//60}min)")
                        logger.info(f"   Reason: {debounce_reason}")

                        # Update database with debounce info
                        if NOTIFICATION_DB:
                            now = datetime.now()
                            debounce_until = now + timedelta(seconds=debounce_seconds)
                            debounce_until_str = debounce_until.isoformat()

                            # Get root_uri for thread_chain_id
                            thread_notifications = NOTIFICATION_DB.get_thread_notifications(debounce_uri)
                            if thread_notifications and len(thread_notifications) > 0:
                                root_uri = thread_notifications[0].get('root_uri') or debounce_uri
                            else:
                                root_uri = debounce_uri

                            NOTIFICATION_DB.set_debounce(
                                debounce_uri,
                                debounce_until_str,
                                debounce_reason,
                                root_uri
                            )
                            # Reset status to 'pending' so:
                            # 1. Duplicate detection doesn't delete the queue file (line 2662)
                            # 2. get_pending_debounced_notifications() finds it correctly (line 2670)
                            NOTIFICATION_DB.reset_to_pending(debounce_uri)
                            logger.info(f"   ✓ Debounce set until {debounce_until.strftime('%H:%M:%S')}")
                            logger.info(f"   ⏸️  Notification will stay in queue and be skipped until debounce expires")

                        # Don't mark as processed - keep status='pending' so get_debounced_notifications() finds it
                        # Don't delete file - it stays in queue but will be skipped by skip logic
                        # Return False to keep in queue (skip logic will prevent re-processing until debounce expires)
                        return False

                    except Exception as e:
                        logger.error(f"Error handling debounce_thread tool call: {e}")
                        # Continue processing even if debounce fails

            # Check for deprecated bluesky_reply tool
            if hasattr(message, 'tool_call') and message.tool_call:
                if message.tool_call.name == 'bluesky_reply':
                    logger.error("DEPRECATED TOOL DETECTED: bluesky_reply is no longer supported!")
                    logger.error("Please use add_post_to_bluesky_reply_thread instead.")
                    logger.error("Update the agent's tools using register_tools.py")
                    # Export agent state before terminating
                    export_agent_state(CLIENT, umbra_agent, skip_git=SKIP_GIT)
                    logger.info("=== BOT TERMINATED DUE TO DEPRECATED TOOL USE ===")
                    exit(1)
                
                # Collect flag_archival_memory_for_deletion tool calls
                elif message.tool_call.name == 'flag_archival_memory_for_deletion':
                    try:
                        args = json.loads(message.tool_call.arguments)
                        reason = args.get('reason', '')
                        memory_text = args.get('memory_text', '')
                        confirm = args.get('confirm', False)

                        # Only flag for deletion if confirmed and has all required fields
                        if confirm and memory_text and reason:
                            flagged_memories.append({
                                'reason': reason,
                                'memory_text': memory_text
                            })
                            logger.debug(f"Found memory flagged for deletion (reason: {reason}): {memory_text[:50]}...")
                        elif not confirm:
                            logger.debug(f"Memory deletion not confirmed, skipping: {memory_text[:50]}...")
                        elif not reason:
                            logger.warning(f"Memory deletion missing reason, skipping: {memory_text[:50]}...")
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse flag_archival_memory_for_deletion arguments: {e}")
                
                # Collect add_post_to_bluesky_reply_thread tool calls - only if they were successful
                elif message.tool_call.name == 'add_post_to_bluesky_reply_thread':
                    tool_call_id = message.tool_call.tool_call_id
                    tool_status = tool_call_results.get(tool_call_id, 'unknown')

                    # Only accept explicitly successful tool calls
                    # Rejecting 'unknown' status prevents failed validations from being sent
                    if tool_status == 'success':
                        try:
                            args = json.loads(message.tool_call.arguments)
                            reply_text = args.get('text', '')
                            reply_lang = args.get('lang', 'en-US')

                            if reply_text:  # Only add if there's actual content
                                reply_candidates.append((reply_text, reply_lang))
                                logger.debug(f"Found successful add_post_to_bluesky_reply_thread candidate: {reply_text[:50]}... (lang: {reply_lang})")
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse tool call arguments: {e}")
                    elif tool_status == 'error':
                        logger.debug(f"Skipping failed add_post_to_bluesky_reply_thread tool call (status: error)")
                    elif tool_status == 'unknown':
                        logger.error(f"❌ Skipping add_post_to_bluesky_reply_thread with unknown tool status (tool_call_id: {tool_call_id})")
                        logger.error(f"   This indicates tool return parsing failed. Check Letta API version and message structure.")
                        logger.error(f"   Tool call results captured: {list(tool_call_results.keys())}")

                # Track reply_to_bluesky_post tool calls - these post DIRECTLY to Bluesky, not via handler
                elif message.tool_call.name == 'reply_to_bluesky_post':
                    tool_call_id = message.tool_call.tool_call_id
                    tool_status = tool_call_results.get(tool_call_id, 'unknown')

                    # Only accept explicitly successful tool calls
                    # NOTE: This tool posts directly to Bluesky, so we don't add to reply_candidates
                    # (that would cause duplicate posting). We just track that a reply was posted.
                    if tool_status == 'success':
                        direct_reply_posted = True
                        logger.debug(f"Detected successful reply_to_bluesky_post (posted directly to Bluesky)")
                    elif tool_status == 'error':
                        logger.debug(f"Skipping failed reply_to_bluesky_post tool call (status: error)")
                    elif tool_status == 'unknown':
                        logger.error(f"❌ Skipping reply_to_bluesky_post with unknown tool status (tool_call_id: {tool_call_id})")

        # Handle archival memory deletion if any were flagged (only if no halt was received)
        if flagged_memories:
            logger.info(f"Processing {len(flagged_memories)} flagged memories for deletion")
            for flagged_memory in flagged_memories:
                reason = flagged_memory['reason']
                memory_text = flagged_memory['memory_text']

                try:
                    # Search for passages with this exact text
                    logger.debug(f"Searching for passages matching: {memory_text[:100]}...")
                    passages = CLIENT.agents.passages.list(
                        agent_id=umbra_agent.id,
                        query=memory_text
                    )

                    if not passages:
                        logger.warning(f"No passages found matching flagged memory: {memory_text[:50]}...")
                        continue

                    # Delete all matching passages
                    deleted_count = 0
                    for passage in passages:
                        # Check if the passage text exactly matches (to avoid partial matches)
                        if hasattr(passage, 'text') and passage.text == memory_text:
                            try:
                                CLIENT.agents.passages.delete(
                                    agent_id=umbra_agent.id,
                                    passage_id=str(passage.id)
                                )
                                deleted_count += 1
                                logger.debug(f"Deleted passage {passage.id}")
                            except Exception as delete_error:
                                logger.error(f"Failed to delete passage {passage.id}: {delete_error}")

                    if deleted_count > 0:
                        logger.info(f"🗑️ Deleted {deleted_count} archival memory passage(s) (reason: {reason}): {memory_text[:50]}...")
                    else:
                        logger.warning(f"No exact matches found for deletion: {memory_text[:50]}...")

                except Exception as e:
                    logger.error(f"Error processing memory deletion: {e}")

        # Check for conflicting tool calls
        if reply_candidates and ignored_notification:
            logger.error(f"⚠️ CONFLICT: Agent called both add_post_to_bluesky_reply_thread and ignore_notification!")
            logger.error(f"Reply candidates: {len(reply_candidates)}, Ignore reason: {ignore_reason}")
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
            
            logger.debug(f"Found {len(reply_candidates)} add_post_to_bluesky_reply_thread calls, building thread")
            
            # Display the generated reply thread
            if len(reply_messages) == 1:
                content = reply_messages[0]
                title = f"Reply to @{author_handle}"
            else:
                content = "\n\n".join([f"{j}. {msg}" for j, msg in enumerate(reply_messages, 1)])
                title = f"Reply Thread to @{author_handle} ({len(reply_messages)} messages)"
            
            # Format with Unicode characters
            print(f"\n✎ {title}")
            print(f"  {'─' * len(title)}")
            # Indent content lines
            for line in content.split('\n'):
                print(f"  {line}")

            # Send the reply(s) with language (unless in testing mode)
            if testing_mode:
                logger.info("TESTING MODE: Skipping actual Bluesky post")
                response = True  # Simulate success
            else:
                if len(reply_messages) == 1:
                    # Single reply - use existing function
                    cleaned_text = bsky_utils.remove_outside_quotes(reply_messages[0])
                    logger.info(f"Sending single reply: {cleaned_text[:50]}... (lang: {reply_lang})")
                    response = bsky_utils.reply_to_notification(
                        client=atproto_client,
                        notification=notification_data,
                        reply_text=cleaned_text,
                        lang=reply_lang,
                        correlation_id=correlation_id
                    )
                else:
                    # Multiple replies - use new threaded function
                    cleaned_messages = [bsky_utils.remove_outside_quotes(msg) for msg in reply_messages]
                    logger.info(f"Sending threaded reply with {len(cleaned_messages)} messages (lang: {reply_lang})")
                    response = bsky_utils.reply_with_thread_to_notification(
                        client=atproto_client,
                        notification=notification_data,
                        reply_messages=cleaned_messages,
                        lang=reply_lang,
                        correlation_id=correlation_id
                    )

            # Verify reply was sent successfully
            # For threaded replies, reply_with_thread_to_notification returns list of responses or None
            # For single replies, reply_to_notification returns dict or None
            # In testing mode, response is True
            reply_sent_successfully = False
            if response is not None and response is not False:
                # Additional validation for threaded replies
                if isinstance(response, list):
                    # Verify we sent all requested messages
                    if len(response) == len(reply_messages):
                        reply_sent_successfully = True
                    else:
                        logger.error(f"[{correlation_id}] Threaded reply incomplete: sent {len(response)}/{len(reply_messages)} messages")
                else:
                    # Single reply or testing mode
                    reply_sent_successfully = True

            if reply_sent_successfully:
                logger.info(f"[{correlation_id}] Successfully replied to @{author_handle}", extra={
                    'correlation_id': correlation_id,
                    'author_handle': author_handle,
                    'reply_count': len(reply_messages)
                })

                # Mark all notifications from the same consecutive chain as processed
                # This prevents duplicate processing when a multi-part message arrives as multiple notifications
                if NOTIFICATION_DB:
                    try:
                        # Extract author_did, root_uri, and indexed_at from notification_data
                        if isinstance(notification_data, dict):
                            author_did = notification_data.get('author', {}).get('did', '')
                            indexed_at = notification_data.get('indexed_at', '')
                            # Get root_uri from reply info or use notification uri
                            record = notification_data.get('record', {})
                            reply_info = record.get('reply', {}) if isinstance(record, dict) else {}
                            root_info = reply_info.get('root', {}) if isinstance(reply_info, dict) else {}
                            root_uri = root_info.get('uri') if isinstance(root_info, dict) else None
                            if not root_uri:
                                root_uri = notification_data.get('uri', '')
                        else:
                            author_did = getattr(getattr(notification_data, 'author', None), 'did', '')
                            indexed_at = getattr(notification_data, 'indexed_at', '')
                            root_uri = notification_data.uri

                        if author_did and root_uri and indexed_at:
                            NOTIFICATION_DB.mark_consecutive_chain_processed(
                                root_uri=root_uri,
                                author_did=author_did,
                                reference_time=indexed_at
                            )
                    except Exception as e:
                        logger.error(f"Error marking consecutive chain as processed: {e}")
                        # Don't fail the operation if this cleanup fails

                return True
            else:
                logger.error(f"Failed to send reply to @{author_handle}")
                return False
        else:
            # Check if agent returned an error first (before checking for intentional no-reply)
            if agent_error_occurred:
                if agent_error_details:
                    logger.error(f"[{correlation_id}] Agent error for @{author_handle}: {agent_error_details}", extra={
                        'correlation_id': correlation_id,
                        'author_handle': author_handle,
                        'error': agent_error_details
                    })
                else:
                    logger.error(f"[{correlation_id}] Agent error for @{author_handle} (no details provided)", extra={
                        'correlation_id': correlation_id,
                        'author_handle': author_handle
                    })
                # Return False to trigger retry (will move to errors folder after max retries)
                return False
            # Check if notification was explicitly ignored
            elif ignored_notification:
                logger.info(f"[{correlation_id}] Notification from @{author_handle} was explicitly ignored (category: {ignore_category})", extra={
                    'correlation_id': correlation_id,
                    'author_handle': author_handle,
                    'ignore_category': ignore_category
                })
                return "ignored"
            # Check if a direct reply was posted (via reply_to_bluesky_post tool)
            elif direct_reply_posted:
                logger.info(f"[{correlation_id}] Direct reply was posted to @{author_handle} via reply_to_bluesky_post tool", extra={
                    'correlation_id': correlation_id,
                    'author_handle': author_handle
                })
                return True  # Treat as successful reply
            else:
                logger.warning(f"[{correlation_id}] No reply generated for mention from @{author_handle}, moving to no_reply folder", extra={
                    'correlation_id': correlation_id,
                    'author_handle': author_handle
                })
                return "no_reply"

    except Exception as e:
        logger.error(f"[{correlation_id}] Error processing mention: {e}", extra={
            'correlation_id': correlation_id,
            'error': str(e),
            'error_type': type(e).__name__,
            'author_handle': author_handle if 'author_handle' in locals() else 'unknown'
        })
        return False
    finally:
        # Detach user blocks after agent response (success or failure)
        if 'attached_handles' in locals() and attached_handles:
            try:
                logger.info(f"Detaching user blocks for handles: {attached_handles}")
                detach_result = detach_user_blocks(attached_handles, umbra_agent)
                logger.debug(f"Detach result: {detach_result}")
            except Exception as detach_error:
                logger.warning(f"Failed to detach user blocks: {detach_error}")


def notification_to_dict(notification):
    """Convert a notification object to a dictionary for JSON serialization."""
    record_dict = {
        'text': getattr(notification.record, 'text', '') if hasattr(notification, 'record') else ''
    }

    # Include reply info for parent chain traversal
    if hasattr(notification, 'record') and hasattr(notification.record, 'reply') and notification.record.reply:
        reply = notification.record.reply
        reply_dict = {}
        if hasattr(reply, 'root') and reply.root:
            reply_dict['root'] = {
                'uri': getattr(reply.root, 'uri', None),
                'cid': getattr(reply.root, 'cid', None)
            }
        if hasattr(reply, 'parent') and reply.parent:
            reply_dict['parent'] = {
                'uri': getattr(reply.parent, 'uri', None),
                'cid': getattr(reply.parent, 'cid', None)
            }
        if reply_dict:
            record_dict['reply'] = reply_dict

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
        'record': record_dict
    }


def load_processed_notifications():
    """Load the set of processed notification URIs from database."""
    global NOTIFICATION_DB
    if NOTIFICATION_DB:
        return NOTIFICATION_DB.get_processed_uris(limit=MAX_PROCESSED_NOTIFICATIONS)
    return set()


def save_processed_notifications(processed_set):
    """Save the set of processed notification URIs to database."""
    # This is now handled by marking individual notifications in the DB
    # Keeping function for compatibility but it doesn't need to do anything
    pass


def save_notification_to_queue(notification, is_priority=None):
    """Save a notification to the queue directory with priority-based filename."""
    try:
        global NOTIFICATION_DB
        
        # Handle both notification objects and dicts
        if isinstance(notification, dict):
            notif_dict = notification
            notification_uri = notification.get('uri')
        else:
            notif_dict = notification_to_dict(notification)
            notification_uri = notification.uri
        
        # Check if already processed (using database if available)
        if NOTIFICATION_DB:
            # Get detailed status for diagnostic logging
            cursor = NOTIFICATION_DB.conn.execute(
                "SELECT status FROM notifications WHERE uri = ?",
                (notification_uri,)
            )
            row = cursor.fetchone()
            if row:
                db_status = row['status']
                logger.debug(f"🔍 Notification DB status check: uri={notification_uri}, status={db_status}")
                if db_status in ['processed', 'ignored', 'no_reply', 'in_progress']:
                    logger.debug(f"Notification already processed (DB status={db_status}): {notification_uri}")
                    return False
            else:
                logger.debug(f"🔍 Notification not in DB: {notification_uri}")

            # Filter out umbra's own posts to prevent processing self-replies
            author_handle = notif_dict.get('author', {}).get('handle', '') if notif_dict.get('author') else ''
            config = get_config()
            umbra_handle = config.get('bluesky', {}).get('username', '')
            if author_handle and umbra_handle and author_handle == umbra_handle:
                logger.debug(f"Skipping self-notification from umbra: {notification_uri}")
                return False

            # Extract thread URIs from notification
            record = notif_dict.get('record', {})
            root_uri = None
            parent_uri = None
            if record and 'reply' in record and record['reply']:
                reply_info = record['reply']
                if reply_info and isinstance(reply_info, dict):
                    root_info = reply_info.get('root', {})
                    parent_info = reply_info.get('parent', {})
                    if root_info:
                        root_uri = root_info.get('uri')
                    if parent_info:
                        parent_uri = parent_info.get('uri')

            # If no root_uri in reply info, this notification IS the root
            if not root_uri:
                root_uri = notification_uri
            # For parent, if no parent_uri, use notification_uri as well
            # (a post without a parent is its own parent for deduplication purposes)
            if not parent_uri:
                parent_uri = notification_uri

            # High-traffic thread detection
            config = get_config()
            threading_config = config.get('threading', {})
            high_traffic_config = threading_config.get('high_traffic_detection', {})

            # Debug: Log config values to diagnose override issues
            if high_traffic_config.get('enabled', False):
                logger.debug(f"High-traffic config loaded: {high_traffic_config}")

            if high_traffic_config.get('enabled', False):
                threshold = high_traffic_config.get('notification_threshold', 10)
                time_window = high_traffic_config.get('time_window_minutes', 60)

                # Count notifications for this thread in the time window
                thread_count = NOTIFICATION_DB.get_thread_notification_count(root_uri, time_window)

                # Determine if this is a mention or reply
                current_reason = notif_dict.get('reason', 'reply')
                is_mention = current_reason == 'mention'
                thread_type = "mention" if is_mention else "reply"

                # Get current thread state
                thread_state = NOTIFICATION_DB.get_thread_state(root_uri)

                # Check if thread is in DEBOUNCING or COOLDOWN state
                if thread_state:
                    if thread_state['state'] == 'debouncing':
                        # Check if the debounce timer has EXPIRED
                        # If expired, the batch is pending processing - start a NEW debounce cycle
                        current_time = datetime.now().isoformat()
                        thread_debounce_until = thread_state.get('debounce_until', '')
                        timer_expired = thread_debounce_until and thread_debounce_until <= current_time

                        if timer_expired:
                            # Check if the thread state is STALE (timer expired a long time ago)
                            # If so, clear the state and process normally instead of starting a new debounce
                            stale_threshold_minutes = time_window  # Use same window as detection threshold
                            timer_expired_at = datetime.fromisoformat(thread_debounce_until)
                            minutes_since_expiry = (datetime.now() - timer_expired_at).total_seconds() / 60

                            if minutes_since_expiry > stale_threshold_minutes:
                                # Thread state is stale - clear it and process normally
                                logger.info(f"⚡ Thread debounce state is stale ({minutes_since_expiry:.1f}min since expiry), clearing state")
                                NOTIFICATION_DB.clear_thread_state(root_uri)
                                # Fall through to normal processing below (skip_db_add = False)
                                skip_db_add = False
                            else:
                                # Timer expired recently - start a fresh debounce cycle for new notifications
                                # The old batch will be processed separately
                                logger.info(f"⚡ Debounce timer expired for thread, starting new cycle for incoming {thread_type}")

                                # Check for duplicate first
                                add_result = NOTIFICATION_DB.add_notification(notif_dict)
                                if add_result == "duplicate":
                                    logger.debug(f"⚡ Skipping duplicate {thread_type} (timer expired): {notification_uri}")
                                    return False
                                elif add_result == "error":
                                    logger.error(f"⚡ Error adding {thread_type} to database: {notification_uri}")
                                    return False

                                # Start fresh debounce cycle with NEW start time
                                min_minutes = high_traffic_config.get(
                                    'mention_debounce_min' if is_mention else 'reply_debounce_min', 7
                                )
                                min_seconds = min_minutes * 60
                                debounce_until = (datetime.now() + timedelta(seconds=min_seconds)).isoformat()
                                NOTIFICATION_DB.set_thread_debouncing(root_uri, debounce_until, notification_count=1)

                                logger.info(f"⚡ Started new debounce cycle for {thread_type} (duration: {min_minutes}min)")

                                # Set auto-debounce on the newly added notification
                                reason_label = 'high_traffic_mention' if is_mention else 'high_traffic_reply'
                                NOTIFICATION_DB.set_auto_debounce(
                                    notification_uri,
                                    debounce_until,
                                    is_high_traffic=True,
                                    reason=reason_label,
                                    thread_chain_id=root_uri
                                )

                                skip_db_add = True

                        else:
                            # Timer NOT expired - extend the existing debounce
                            # Check for duplicate FIRST before extending
                            add_result = NOTIFICATION_DB.add_notification(notif_dict)
                            if add_result == "duplicate":
                                # Skip extension entirely for duplicates
                                existing = NOTIFICATION_DB.get_notification(notification_uri)
                                if existing and existing.get('debounce_until'):
                                    if existing['debounce_until'] > datetime.now().isoformat():
                                        logger.debug(f"⚡ Skipping duplicate notification in debouncing thread: {notification_uri}")
                                        return False
                                logger.debug(f"⚡ Skipping duplicate high-traffic {thread_type}: {notification_uri}")
                                return False
                            elif add_result == "error":
                                logger.error(f"⚡ Error adding high-traffic {thread_type} to database: {notification_uri}")
                                return False

                            # Only extend if it's a genuinely new notification
                            new_count = thread_state['notification_count'] + 1

                            # Recalculate debounce time based on new count
                            new_debounce_seconds = NOTIFICATION_DB.calculate_variable_debounce(
                                new_count, is_mention, high_traffic_config
                            )

                            # Cap at max
                            max_minutes = high_traffic_config.get(
                                'mention_debounce_max' if is_mention else 'reply_debounce_max', 60
                            )
                            max_seconds = max_minutes * 60
                            new_debounce_seconds = min(new_debounce_seconds, max_seconds)

                            # Get debounce start time (use current time as fallback for legacy data)
                            debounce_started_at = thread_state.get('debounce_started_at') or datetime.now().isoformat()

                            # Extend debounce - expiry is calculated from START time, not now
                            new_debounce_until = NOTIFICATION_DB.extend_thread_debounce(
                                root_uri, new_debounce_seconds, new_count, debounce_started_at
                            )
                            if not new_debounce_until:
                                logger.error(f"⚡ Failed to extend debounce for {thread_type}: {notification_uri}")
                                return False
                            debounce_until = new_debounce_until

                            logger.info(f"⚡ Extending debounce for high-traffic {thread_type} ({new_count} notifications, expiry: {new_debounce_until}, started: {debounce_started_at})")

                            # Set auto-debounce on the newly added notification
                            reason_label = 'high_traffic_mention' if is_mention else 'high_traffic_reply'
                            NOTIFICATION_DB.set_auto_debounce(
                                notification_uri,
                                debounce_until,
                                is_high_traffic=True,
                                reason=reason_label,
                                thread_chain_id=root_uri
                            )

                            skip_db_add = True

                    elif thread_state['state'] == 'cooldown':
                        # Thread is in cooldown - check for duplicate FIRST before re-triggering
                        add_result = NOTIFICATION_DB.add_notification(notif_dict)
                        if add_result == "duplicate":
                            # Skip re-triggering entirely for duplicates
                            existing = NOTIFICATION_DB.get_notification(notification_uri)
                            if existing and existing.get('debounce_until'):
                                if existing['debounce_until'] > datetime.now().isoformat():
                                    logger.debug(f"⚡ Skipping duplicate notification in cooldown thread: {notification_uri}")
                                    return False
                            logger.debug(f"⚡ Skipping duplicate high-traffic {thread_type} during cooldown: {notification_uri}")
                            return False
                        elif add_result == "error":
                            logger.error(f"⚡ Error adding high-traffic {thread_type} to database: {notification_uri}")
                            return False

                        # Only re-trigger if it's a genuinely new notification
                        min_minutes = high_traffic_config.get(
                            'mention_debounce_min' if is_mention else 'reply_debounce_min', 7
                        )
                        min_seconds = min_minutes * 60
                        debounce_until = (datetime.now() + timedelta(seconds=min_seconds)).isoformat()
                        NOTIFICATION_DB.set_thread_debouncing(root_uri, debounce_until, notification_count=1)

                        logger.info(f"⚡ Re-triggering debounce during cooldown for {thread_type} (min duration: {min_minutes}min)")

                        # Set auto-debounce on the newly added notification
                        reason_label = 'high_traffic_mention' if is_mention else 'high_traffic_reply'
                        NOTIFICATION_DB.set_auto_debounce(
                            notification_uri,
                            debounce_until,
                            is_high_traffic=True,
                            reason=reason_label,
                            thread_chain_id=root_uri
                        )

                        skip_db_add = True
                    else:
                        # Unknown state - treat as no state
                        skip_db_add = False

                elif thread_count >= threshold:
                    # No existing state but threshold reached - start fresh debounce
                    debounce_seconds = NOTIFICATION_DB.calculate_variable_debounce(
                        thread_count, is_mention, high_traffic_config
                    )
                    debounce_until = (datetime.now() + timedelta(seconds=debounce_seconds)).isoformat()
                    NOTIFICATION_DB.set_thread_debouncing(root_uri, debounce_until, thread_count)

                    debounce_hours = debounce_seconds / 3600
                    logger.info(f"⚡ Started debounce for high-traffic {thread_type} ({thread_count} notifications, {debounce_hours:.1f}h wait)")

                    # Add notification to database and set debounce
                    add_result = NOTIFICATION_DB.add_notification(notif_dict)
                    if add_result == "added":
                        reason_label = 'high_traffic_mention' if is_mention else 'high_traffic_reply'
                        NOTIFICATION_DB.set_auto_debounce(
                            notification_uri,
                            debounce_until,
                            is_high_traffic=True,
                            reason=reason_label,
                            thread_chain_id=root_uri
                        )
                    elif add_result == "duplicate":
                        existing = NOTIFICATION_DB.get_notification(notification_uri)
                        if existing and existing.get('debounce_until'):
                            if existing['debounce_until'] > datetime.now().isoformat():
                                logger.debug(f"⚡ Skipping queue file for debounced high-traffic {thread_type}: {notification_uri}")
                                return False
                        else:
                            logger.debug(f"⚡ Skipping queue file for duplicate high-traffic {thread_type}: {notification_uri}")
                            return False
                    else:
                        logger.error(f"⚡ Error adding high-traffic {thread_type} to database: {notification_uri}")
                        return False

                    skip_db_add = True
                else:
                    # Below threshold and no existing state - normal processing
                    skip_db_add = False
            else:
                skip_db_add = False

            # Check if we already have a notification for the same parent post
            # This prevents duplicate notifications about the same post while allowing
            # new conversation turns in the same thread
            existing_notif = NOTIFICATION_DB.has_notification_for_parent(parent_uri)
            if existing_notif:
                existing_reason = existing_notif.get('reason', 'unknown')
                existing_uri = existing_notif.get('uri', 'unknown')
                existing_status = existing_notif.get('status', 'unknown')
                current_reason = notif_dict.get('reason', 'unknown')

                # Only skip if we already have a 'mention' that is still PENDING and this is a 'reply'
                # If the mention was already processed, this reply is a new conversation turn
                if existing_reason == 'mention' and current_reason == 'reply' and existing_status == 'pending':
                    logger.info(f"⏭️  Skipping duplicate 'reply' notification - already have pending 'mention' for same parent post")
                    logger.debug(f"   Existing: {existing_uri} (reason: {existing_reason}, status: {existing_status})")
                    logger.debug(f"   Skipped:  {notification_uri} (reason: {current_reason})")
                    logger.debug(f"   Parent URI: {parent_uri}")
                    return False
                elif existing_reason == 'mention' and current_reason == 'reply' and existing_status != 'pending':
                    logger.debug(f"Not skipping 'reply' - 'mention' already processed (status: {existing_status}), this is a new conversation turn")

                # Skip if both are the same reason (already handled by URI check above, but log it)
                if existing_reason == current_reason:
                    logger.debug(f"Duplicate notification with same reason '{current_reason}' for parent post: {parent_uri}")

            # Add to database - if this fails, don't queue the notification
            # Skip if already added during high-traffic detection
            # Track if this is a newly added notification to skip duplicate queue file check
            just_added_to_db = skip_db_add  # True if added during high-traffic detection

            if not skip_db_add:
                add_result = NOTIFICATION_DB.add_notification(notif_dict)

                if add_result == "error":
                    logger.warning(f"Database error adding notification, skipping: {notification_uri}")
                    return False
                elif add_result == "duplicate":
                    # Check if this is an expired debounced notification that should be processed
                    existing = NOTIFICATION_DB.get_notification(notification_uri)
                    if existing and existing.get('debounce_until'):
                        debounce_until = existing['debounce_until']
                        current_time = datetime.now().isoformat()

                        # If debounce has expired, allow processing
                        if debounce_until <= current_time:
                            logger.info(f"⏰ Processing expired debounced notification from @{existing.get('author_handle', 'unknown')}")
                            logger.debug(f"   Debounce expired: {debounce_until}")
                            logger.debug(f"   Current time: {current_time}")
                            # Don't return False - allow it to continue to queue creation below
                        else:
                            logger.debug(f"⏸️ Skipping debounced notification (still waiting): {notification_uri}")
                            return False
                    else:
                        # Duplicate without debounce - already processed or being processed
                        logger.debug(f"Duplicate notification (no debounce), skipping: {notification_uri}")
                        return False
                elif add_result == "added":
                    # This is a newly added notification
                    just_added_to_db = True
        else:
            # Fall back to old JSON method
            processed_uris = load_processed_notifications()
            if notification_uri in processed_uris:
                logger.debug(f"Notification already processed: {notification_uri}")
                return False

        # Create JSON string
        notif_json = json.dumps(notif_dict, sort_keys=True)

        # Generate hash for filename (to avoid duplicates)
        notif_hash = hashlib.sha256(notif_json.encode()).hexdigest()[:16]

        # Determine priority based on author handle or explicit priority
        if is_priority is not None:
            priority_prefix = "0_" if is_priority else "1_"
        else:
            if isinstance(notification, dict):
                author_handle = notification.get('author', {}).get('handle', '')
            else:
                author_handle = getattr(notification.author, 'handle', '') if hasattr(notification, 'author') else ''
            # Prioritize 3fz.org responses
            priority_prefix = "0_" if author_handle == "3fz.org" else "1_"

        # Before creating queue file, check if notification already exists in database
        # This prevents duplicate queue files when notification is re-fetched (e.g., debounced)
        # Skip this check for newly added notifications (they definitely don't have queue files yet)
        if NOTIFICATION_DB and not just_added_to_db:
            cursor = NOTIFICATION_DB.conn.execute(
                "SELECT uri, status, debounce_until FROM notifications WHERE uri = ?",
                (notification_uri,)
            )
            existing = cursor.fetchone()
            if existing:
                status = existing['status']
                debounce_until = existing['debounce_until']

                # Check if this is an expired debounced notification
                is_expired_debounce = False
                if debounce_until:
                    current_time = datetime.now().isoformat()
                    is_expired_debounce = debounce_until <= current_time

                if status == 'pending':
                    # If this is an expired debounced notification, allow queue file creation
                    if is_expired_debounce:
                        logger.debug(f"Creating queue file for expired debounced notification: {notification_uri}")
                        # Don't clear debounce here - preserve flags for routing in queue processing
                        # Debounce will be cleared after successful processing
                        # Continue to queue file creation below
                    else:
                        # Already queued and pending, don't create duplicate queue file
                        logger.debug(f"Notification already pending in database, skipping queue file creation: {notification_uri}")
                        return True  # Return True to indicate "handled" (not an error)
                # If status is processed/error/ignored, allow queue file creation for retry

        # Create filename with priority, timestamp and hash
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        reason = notif_dict.get('reason', 'unknown')
        filename = f"{priority_prefix}{timestamp}_{reason}_{notif_hash}.json"
        filepath = QUEUE_DIR / filename

        # Note: Duplicate checking is now handled atomically in the database (add_notification)
        # The file-system check has been removed to reduce race conditions

        # Write to file
        with open(filepath, 'w') as f:
            json.dump(notif_dict, f, indent=2)

        priority_label = "HIGH PRIORITY" if priority_prefix == "0_" else "normal"
        logger.info(f"Queued notification ({priority_label}): {filename}")
        return True

    except Exception as e:
        logger.error(f"Error saving notification to queue: {e}")
        return False


def load_and_process_queued_notifications(umbra_agent, atproto_client, testing_mode=False):
    """Load and process all notifications from the queue in priority order."""
    try:
        # Check if debouncing is enabled
        config = get_config()
        threading_config = config.get('threading', {})
        debounce_enabled = threading_config.get('debounce_enabled', False)

        # Track which high-traffic batches we've already processed in this session
        processed_high_traffic_batches = set()

        # Get all JSON files in queue directory (excluding processed_notifications.json)
        # Files are sorted by name, which puts priority files first (0_ prefix before 1_ prefix)
        all_queue_files = sorted([f for f in QUEUE_DIR.glob("*.json") if f.name != "processed_notifications.json"])

        # Filter out and delete like notifications immediately
        queue_files = []
        likes_deleted = 0
        
        for filepath in all_queue_files:
            try:
                with open(filepath, 'r') as f:
                    notif_data = json.load(f)
                
                # If it's a like, delete it immediately and don't process
                if notif_data.get('reason') == 'like':
                    filepath.unlink()
                    likes_deleted += 1
                    logger.debug(f"Deleted like notification: {filepath.name}")
                else:
                    queue_files.append(filepath)
            except Exception as e:
                logger.warning(f"Error checking notification file {filepath.name}: {e}")
                queue_files.append(filepath)  # Keep it in case it's valid
        
        if likes_deleted > 0:
            logger.info(f"Deleted {likes_deleted} like notifications from queue")

        if not queue_files:
            return

        logger.info(f"Processing {len(queue_files)} queued notifications")
        
        # Log current statistics
        elapsed_time = time.time() - start_time
        total_messages = sum(message_counters.values())
        messages_per_minute = (total_messages / elapsed_time * 60) if elapsed_time > 0 else 0
        
        logger.info(f"Session stats: {total_messages} total messages ({message_counters['mentions']} mentions, {message_counters['replies']} replies, {message_counters['follows']} follows) | {messages_per_minute:.1f} msg/min")

        for i, filepath in enumerate(queue_files, 1):
            # Determine if this is a priority notification
            is_priority = filepath.name.startswith("0_")
            
            # Check for new notifications periodically during queue processing
            # Also check immediately after processing each priority item
            should_check_notifications = (i % CHECK_NEW_NOTIFICATIONS_EVERY_N_ITEMS == 0 and i > 1)
            
            # If we just processed a priority item, immediately check for new priority notifications
            if is_priority and i > 1:
                should_check_notifications = True
            
            if should_check_notifications:
                logger.info(f"🔄 Checking for new notifications (processed {i-1}/{len(queue_files)} queue items)")
                try:
                    # Fetch and queue new notifications without processing them
                    new_count = fetch_and_queue_new_notifications(atproto_client)
                    
                    if new_count > 0:
                        logger.info(f"Added {new_count} new notifications to queue")
                        # Reload the queue files to include the new items
                        updated_queue_files = sorted([f for f in QUEUE_DIR.glob("*.json") if f.name != "processed_notifications.json"])
                        queue_files = updated_queue_files
                        logger.info(f"Queue updated: now {len(queue_files)} total items")
                except Exception as e:
                    logger.error(f"Error checking for new notifications: {e}")
            
            priority_label = " [PRIORITY]" if is_priority else ""
            logger.info(f"Processing queue file {i}/{len(queue_files)}{priority_label}: {filepath.name}")
            try:
                # Load notification data
                with open(filepath, 'r') as f:
                    notif_data = json.load(f)

                # Save original URI before any modifications (process_mention may modify notif_data)
                # This ensures we mark the correct notification as processed, not the last consecutive post
                original_notification_uri = notif_data['uri']

                # Check if this notification has already been processed (duplicate queue file cleanup)
                # This handles legacy duplicate queue files that were created before deduplication was fixed
                if NOTIFICATION_DB:
                    existing_notif = NOTIFICATION_DB.get_notification(notif_data['uri'])
                    if existing_notif and existing_notif.get('status') in ['processed', 'in_progress']:
                        logger.info(f"🗑️ Deleting duplicate queue file (notification already {existing_notif.get('status')}): {filepath.name}")
                        filepath.unlink()
                        continue  # Skip to next queue file

                # Check if this notification is debounced and still waiting
                if debounce_enabled and NOTIFICATION_DB:
                    from datetime import datetime
                    db_notifs = NOTIFICATION_DB.get_pending_debounced_notifications()
                    debounced_uris = {n['uri'] for n in db_notifs}

                    if notif_data['uri'] in debounced_uris:
                        # Find this notification's debounce info
                        matching_notif = next((n for n in db_notifs if n['uri'] == notif_data['uri']), None)
                        if matching_notif and matching_notif.get('debounce_until'):
                            debounce_until = matching_notif['debounce_until']
                            logger.info(f"⏸️  Skipping debounced notification (waiting until {debounce_until}): {filepath.name}")
                            # Keep the queue file - it will be processed when debounce expires
                            continue  # Skip this notification for now

                # Check if this is a debounced notification whose debounce period has expired
                is_debounced = False
                is_high_traffic = False
                debounced_notification = None
                if debounce_enabled and NOTIFICATION_DB:
                    from datetime import datetime
                    expired_debounced = NOTIFICATION_DB.get_debounced_notifications()
                    expired_uris = {n['uri'] for n in expired_debounced}
                    if notif_data['uri'] in expired_uris:
                        is_debounced = True
                        # Find the full notification data to check if it's high-traffic
                        debounced_notification = next((n for n in expired_debounced if n['uri'] == notif_data['uri']), None)

                        # Check if this is a high-traffic auto-debounced notification
                        if debounced_notification:
                            is_high_traffic = (
                                debounced_notification.get('auto_debounced', 0) == 1 and
                                debounced_notification.get('high_traffic_thread', 0) == 1
                            )

                        if is_high_traffic:
                            logger.info(f"⚡ Processing expired high-traffic batch: {filepath.name}")
                        else:
                            logger.info(f"⏰ Processing expired debounced notification: {filepath.name}")

                # Mark notification as in_progress to prevent re-queuing during processing
                # This closes the window where Bluesky might re-surface the notification
                # Use original_notification_uri to ensure we mark the correct notification
                # NOTE: Skip for high-traffic batches - they handle this after retrieving all notifications
                # (otherwise the triggering notification gets excluded from the batch query)
                if NOTIFICATION_DB and not (is_debounced and is_high_traffic):
                    NOTIFICATION_DB.mark_in_progress(original_notification_uri)

                # Process based on type using dict data directly
                success = False
                if notif_data['reason'] == "mention":
                    if is_debounced and is_high_traffic:
                        # Check if we've already processed this batch
                        if debounced_notification:
                            batch_id = debounced_notification.get('thread_chain_id')
                            if batch_id and batch_id in processed_high_traffic_batches:
                                logger.info(f"⚡ Skipping - high-traffic batch already processed for thread: {batch_id}")
                                # Mark as processed and delete the queue file
                                if NOTIFICATION_DB:
                                    NOTIFICATION_DB.mark_processed(original_notification_uri, status='processed')
                                filepath.unlink()
                                success = True
                            else:
                                success = process_high_traffic_batch(umbra_agent, atproto_client, notif_data, queue_filepath=filepath, testing_mode=testing_mode)
                                if success and batch_id:
                                    processed_high_traffic_batches.add(batch_id)
                        else:
                            success = process_high_traffic_batch(umbra_agent, atproto_client, notif_data, queue_filepath=filepath, testing_mode=testing_mode)
                    elif is_debounced:
                        success = process_debounced_thread(umbra_agent, atproto_client, notif_data, queue_filepath=filepath, testing_mode=testing_mode)
                    else:
                        success = process_mention(umbra_agent, atproto_client, notif_data, queue_filepath=filepath, testing_mode=testing_mode)
                    if success:
                        message_counters['mentions'] += 1
                elif notif_data['reason'] == "reply":
                    if is_debounced and is_high_traffic:
                        # Check if we've already processed this batch
                        if debounced_notification:
                            batch_id = debounced_notification.get('thread_chain_id')
                            if batch_id and batch_id in processed_high_traffic_batches:
                                logger.info(f"⚡ Skipping - high-traffic batch already processed for thread: {batch_id}")
                                # Mark as processed and delete the queue file
                                if NOTIFICATION_DB:
                                    NOTIFICATION_DB.mark_processed(original_notification_uri, status='processed')
                                filepath.unlink()
                                success = True
                            else:
                                success = process_high_traffic_batch(umbra_agent, atproto_client, notif_data, queue_filepath=filepath, testing_mode=testing_mode)
                                if success and batch_id:
                                    processed_high_traffic_batches.add(batch_id)
                        else:
                            success = process_high_traffic_batch(umbra_agent, atproto_client, notif_data, queue_filepath=filepath, testing_mode=testing_mode)
                    elif is_debounced:
                        success = process_debounced_thread(umbra_agent, atproto_client, notif_data, queue_filepath=filepath, testing_mode=testing_mode)
                    else:
                        success = process_mention(umbra_agent, atproto_client, notif_data, queue_filepath=filepath, testing_mode=testing_mode)
                    if success:
                        message_counters['replies'] += 1
                elif notif_data['reason'] == "follow":
                    author_handle = notif_data['author']['handle']
                    author_display_name = notif_data['author'].get('display_name', 'no display name')
                    follow_update = f"@{author_handle} ({author_display_name}) started following you."
                    follow_message = f"Update: {follow_update}"
                    logger.info(f"Notifying agent about new follower: @{author_handle} | prompt: {len(follow_message)} chars")
                    CLIENT.agents.messages.create(
                        agent_id = umbra_agent.id,
                        messages = [{"role":"user", "content": follow_message}]
                    )
                    success = True  # Follow updates are always successful
                    if success:
                        message_counters['follows'] += 1
                elif notif_data['reason'] == "repost":
                    # Skip reposts silently
                    success = True  # Skip reposts but mark as successful to remove from queue
                    if success:
                        message_counters['reposts_skipped'] += 1
                elif notif_data['reason'] == "like":
                    # Skip likes silently
                    success = True  # Skip likes but mark as successful to remove from queue
                    if success:
                        message_counters.setdefault('likes_skipped', 0)
                        message_counters['likes_skipped'] += 1
                else:
                    logger.warning(f"Unknown notification type: {notif_data['reason']}")
                    success = True  # Remove unknown types from queue

                # Handle file based on processing result
                if success:
                    # Mark as processed to avoid reprocessing (do this even in testing mode)
                    # Use original_notification_uri to ensure the original notification is marked,
                    # not a potentially modified URI from consecutive post detection
                    if NOTIFICATION_DB:
                        NOTIFICATION_DB.mark_processed(original_notification_uri, status='processed')
                    else:
                        processed_uris = load_processed_notifications()
                        processed_uris.add(original_notification_uri)
                        save_processed_notifications(processed_uris)

                    # Delete file in normal mode, keep in testing mode
                    if testing_mode:
                        logger.info(f"TESTING MODE: Keeping queue file: {filepath.name}")
                    else:
                        filepath.unlink()
                        logger.info(f"Successfully processed and removed: {filepath.name}")

                        # Clear debounce flags now that processing is complete
                        if NOTIFICATION_DB and is_debounced:
                            NOTIFICATION_DB.clear_debounce(original_notification_uri)
                            logger.debug(f"Cleared debounce flags for: {original_notification_uri}")
                    
                elif success is None:  # Special case for moving to error directory
                    error_path = QUEUE_ERROR_DIR / filepath.name
                    filepath.rename(error_path)
                    logger.warning(f"Moved {filepath.name} to errors directory")

                    # Also mark as processed to avoid retrying
                    if NOTIFICATION_DB:
                        NOTIFICATION_DB.mark_processed(original_notification_uri, status='error')
                    else:
                        processed_uris = load_processed_notifications()
                        processed_uris.add(original_notification_uri)
                        save_processed_notifications(processed_uris)

                elif success == "no_reply":  # Special case for moving to no_reply directory
                    no_reply_path = QUEUE_NO_REPLY_DIR / filepath.name
                    filepath.rename(no_reply_path)
                    logger.info(f"Moved {filepath.name} to no_reply directory")

                    # Also mark as processed to avoid retrying
                    if NOTIFICATION_DB:
                        NOTIFICATION_DB.mark_processed(original_notification_uri, status='error')
                    else:
                        processed_uris = load_processed_notifications()
                        processed_uris.add(original_notification_uri)
                        save_processed_notifications(processed_uris)

                elif success == "ignored":  # Special case for explicitly ignored notifications
                    # For ignored notifications, we just delete them (not move to no_reply)
                    filepath.unlink()
                    logger.info(f"🚫 Deleted ignored notification: {filepath.name}")

                    # Also mark as processed to avoid retrying
                    if NOTIFICATION_DB:
                        NOTIFICATION_DB.mark_processed(original_notification_uri, status='ignored')
                    else:
                        processed_uris = load_processed_notifications()
                        processed_uris.add(original_notification_uri)
                        save_processed_notifications(processed_uris)

                else:
                    # Failed to process - check retry count
                    if NOTIFICATION_DB:
                        retry_count = NOTIFICATION_DB.increment_retry(original_notification_uri)
                        if retry_count >= MAX_RETRY_COUNT:
                            logger.error(f"❌ Max retries ({MAX_RETRY_COUNT}) exceeded for {filepath.name}, moving to errors")
                            error_path = QUEUE_ERROR_DIR / filepath.name
                            filepath.rename(error_path)
                            NOTIFICATION_DB.mark_processed(original_notification_uri, status='error', error=f'Max retries exceeded ({retry_count})')
                        else:
                            logger.warning(f"⚠️  Failed to process {filepath.name}, keeping in queue for retry (attempt {retry_count}/{MAX_RETRY_COUNT})")
                    else:
                        logger.warning(f"⚠️  Failed to process {filepath.name}, keeping in queue for retry")

            except Exception as e:
                logger.error(f"💥 Error processing queued notification {filepath.name}: {e}")
                # Increment retry count and check limit
                # Use original_notification_uri if available (set before processing started)
                uri_for_retry = original_notification_uri if 'original_notification_uri' in locals() else None
                try:
                    if not uri_for_retry:
                        # Re-read file to get URI if we don't have it
                        with open(filepath, 'r') as f:
                            notif_data = json.load(f)
                        uri_for_retry = notif_data['uri']
                    if NOTIFICATION_DB and uri_for_retry:
                        retry_count = NOTIFICATION_DB.increment_retry(uri_for_retry)
                        if retry_count >= MAX_RETRY_COUNT:
                            logger.error(f"❌ Max retries ({MAX_RETRY_COUNT}) exceeded after exception, moving to errors")
                            error_path = QUEUE_ERROR_DIR / filepath.name
                            filepath.rename(error_path)
                            NOTIFICATION_DB.mark_processed(uri_for_retry, status='error', error=str(e))
                        else:
                            logger.warning(f"Keeping in queue for retry (attempt {retry_count}/{MAX_RETRY_COUNT})")
                except:
                    # If we can't even read the file, keep it for manual inspection
                    logger.error(f"Could not read notification file for retry tracking")

    except Exception as e:
        logger.error(f"Error loading queued notifications: {e}")


def fetch_and_queue_new_notifications(atproto_client):
    """Fetch new notifications and queue them without processing."""
    try:
        global NOTIFICATION_DB
        
        # Get current time for marking notifications as seen
        logger.debug("Getting current time for notification marking...")
        last_seen_at = atproto_client.get_current_time_iso()
        
        # Get timestamp of last processed notification for filtering
        last_processed_time = None
        if NOTIFICATION_DB:
            last_processed_time = NOTIFICATION_DB.get_latest_processed_time()
            if last_processed_time:
                logger.debug(f"Last processed notification was at: {last_processed_time}")

        # Fetch ALL notifications using pagination
        all_notifications = []
        cursor = None
        page_count = 0
        max_pages = 20  # Safety limit to prevent infinite loops
        
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
                
                if not page_notifications:
                    break
                
                all_notifications.extend(page_notifications)
                
                # Check if there are more pages
                cursor = getattr(notifications_response, 'cursor', None)
                if not cursor:
                    break
                    
            except Exception as e:
                error_str = str(e)
                # Check if this is a transient API error (502, 503, timeout, etc.)
                if any(x in error_str.lower() for x in ['502', '503', 'timeout', 'unreachable', 'upstreamfailure']):
                    logger.warning(f"⚠️  Transient API error on page {page_count} (will retry next cycle): {error_str[:200]}")
                else:
                    logger.error(f"Error fetching notifications page {page_count}: {e}")
                # Continue with notifications we've already fetched
                break
        
        # Now process all fetched notifications
        new_count = 0
        if all_notifications:
            logger.info(f"📥 Fetched {len(all_notifications)} total notifications from API")
            
            # Mark as seen first
            try:
                atproto_client.app.bsky.notification.update_seen(
                    data={'seenAt': last_seen_at}
                )
                logger.debug(f"Marked {len(all_notifications)} notifications as seen at {last_seen_at}")
            except Exception as e:
                logger.error(f"Error marking notifications as seen: {e}")
            
            # Debug counters
            skipped_read = 0
            skipped_likes = 0
            skipped_processed = 0
            skipped_old_timestamp = 0
            processed_uris = load_processed_notifications()
            
            # Queue all new notifications (except likes)
            for notif in all_notifications:
                # 1. Skip likes first (fast check)
                if hasattr(notif, 'reason') and notif.reason == 'like':
                    skipped_likes += 1
                    continue

                notif_dict = notif.model_dump() if hasattr(notif, 'model_dump') else notif

                # Skip likes in dict form too
                if notif_dict.get('reason') == 'like':
                    continue

                # 2. Check if already processed (deduplication - check BEFORE timestamp)
                # This ensures processed notifications are filtered regardless of timestamp changes
                notif_uri = notif_dict.get('uri', '')
                if notif_uri in processed_uris:
                    skipped_processed += 1
                    logger.debug(f"Skipping already processed: {notif_uri}")
                    continue

                # 3. Skip if older than last processed (timestamp filtering)
                if last_processed_time and hasattr(notif, 'indexed_at'):
                    if notif.indexed_at <= last_processed_time:
                        skipped_old_timestamp += 1
                        logger.debug(f"Skipping old notification (indexed_at {notif.indexed_at} <= {last_processed_time})")
                        continue

                # 4. Debug: Log is_read status but DON'T skip based on it
                if hasattr(notif, 'is_read') and notif.is_read:
                    skipped_read += 1
                    logger.debug(f"Notification has is_read=True (but processing anyway): {notif.uri if hasattr(notif, 'uri') else 'unknown'}")
                
                # Check if it's a priority notification
                is_priority = False
                
                # Priority for 3fz.org notifications
                author_handle = notif_dict.get('author', {}).get('handle', '')
                if author_handle == "3fz.org":
                    is_priority = True
                
                # Also check for priority keywords in mentions
                if notif_dict.get('reason') == 'mention':
                    # Get the mention text to check for priority keywords
                    record = notif_dict.get('record', {})
                    text = record.get('text', '')
                    if any(keyword in text.lower() for keyword in ['urgent', 'priority', 'important', 'emergency']):
                        is_priority = True
                
                # Log when attempting to queue (diagnostic for duplicate detection)
                indexed_at = notif_dict.get('indexed_at', 'unknown')
                logger.debug(f"🔍 Attempting to queue notification: uri={notif_uri}, indexed_at={indexed_at}, author=@{author_handle}")

                if save_notification_to_queue(notif_dict, is_priority=is_priority):
                    new_count += 1
                    logger.debug(f"✅ Queued notification from @{author_handle}: {notif_dict.get('reason', 'unknown')}")
            
            # Log summary of filtering
            logger.info(f"📊 Notification processing summary:")
            logger.info(f"  • Total fetched: {len(all_notifications)}")
            logger.info(f"  • Had is_read=True: {skipped_read} (not skipped)")
            logger.info(f"  • Skipped (likes): {skipped_likes}")
            logger.info(f"  • Skipped (old timestamp): {skipped_old_timestamp}")
            logger.info(f"  • Skipped (already processed): {skipped_processed}")
            logger.info(f"  • Queued for processing: {new_count}")
        else:
            logger.debug("No new notifications to queue")
            
        return new_count
            
    except Exception as e:
        logger.error(f"Error fetching and queueing notifications: {e}")
        return 0


def process_notifications(umbra_agent, atproto_client, testing_mode=False):
    """Fetch new notifications, queue them, and process the queue."""
    try:
        # Clean up expired cooldowns (threads that have been inactive)
        if NOTIFICATION_DB:
            expired_count = NOTIFICATION_DB.cleanup_expired_cooldowns()
            if expired_count > 0:
                logger.info(f"🔄 Reset {expired_count} thread(s) after cooldown expired with no activity")

        # Fetch and queue new notifications
        new_count = fetch_and_queue_new_notifications(atproto_client)
        
        if new_count > 0:
            logger.info(f"Found {new_count} new notifications to process")

        # Now process the entire queue (old + new notifications)
        load_and_process_queued_notifications(umbra_agent, atproto_client, testing_mode)

    except Exception as e:
        logger.error(f"Error processing notifications: {e}")


def periodic_user_block_cleanup(client: Letta, agent_id: str) -> None:
    """
    Detach all user blocks from the agent to prevent memory bloat.
    This should be called periodically to ensure clean state.
    """
    try:
        # Get all blocks attached to the agent
        attached_blocks = client.agents.blocks.list(agent_id=agent_id)
        
        user_blocks_to_detach = []
        for block in attached_blocks:
            if hasattr(block, 'label') and block.label.startswith('user_'):
                user_blocks_to_detach.append({
                    'label': block.label,
                    'id': block.id
                })
        
        if not user_blocks_to_detach:
            logger.debug("No user blocks found to detach during periodic cleanup")
            return
            
        # Detach each user block
        detached_count = 0
        for block_info in user_blocks_to_detach:
            try:
                client.agents.blocks.detach(
                    agent_id=agent_id,
                    block_id=str(block_info['id'])
                )
                detached_count += 1
                logger.debug(f"Detached user block: {block_info['label']}")
            except Exception as e:
                logger.warning(f"Failed to detach block {block_info['label']}: {e}")
        
        if detached_count > 0:
            logger.info(f"Periodic cleanup: Detached {detached_count} user blocks")
            
    except Exception as e:
        logger.error(f"Error during periodic user block cleanup: {e}")



def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Umbra Bot - Bluesky autonomous agent')
    parser.add_argument('--config', type=str, default='config.yaml', help='Path to config file (default: config.yaml)')
    parser.add_argument('--test', action='store_true', help='Run in testing mode (no messages sent, queue files preserved)')
    parser.add_argument('--no-git', action='store_true', help='Skip git operations when exporting agent state')
    parser.add_argument('--simple-logs', action='store_true', help='Use simplified log format (umbra - LEVEL - message)')
    # --rich option removed as we now use simple text formatting
    parser.add_argument('--reasoning', action='store_true', help='Display reasoning in panels and set reasoning log level to INFO')
    parser.add_argument('--cleanup-interval', type=int, default=10, help='Run user block cleanup every N cycles (default: 10, 0 to disable)')
    parser.add_argument('--synthesis-only', action='store_true', help='Run in synthesis-only mode (only send synthesis messages, no notification processing)')

    # Scheduled task enable/disable flags (defaults come from TASK_CONFIGS in scheduled_prompts.py)
    parser.add_argument('--no-synthesis', action='store_true', help='Disable synthesis messages')
    parser.add_argument('--no-mutuals-engagement', action='store_true', help='Disable mutuals engagement')
    parser.add_argument('--no-daily-review', action='store_true', help='Disable daily review')
    parser.add_argument('--no-feed-engagement', action='store_true', help='Disable feed engagement')
    parser.add_argument('--no-curiosities', action='store_true', help='Disable curiosities exploration')
    args = parser.parse_args()

    # Initialize configuration with custom path
    global letta_config, CLIENT, QUEUE_DIR, QUEUE_ERROR_DIR, QUEUE_NO_REPLY_DIR, PROCESSED_NOTIFICATIONS_FILE, NOTIFICATION_DB
    get_config(args.config)  # Initialize the global config instance
    letta_config = get_letta_config()

    # Initialize queue paths from config
    queue_config = get_queue_config()
    QUEUE_DIR = Path(queue_config['base_dir'])
    QUEUE_ERROR_DIR = Path(queue_config['error_dir'])
    QUEUE_NO_REPLY_DIR = Path(queue_config['no_reply_dir'])
    PROCESSED_NOTIFICATIONS_FILE = Path(queue_config['processed_file'])

    # Create queue directories
    QUEUE_DIR.mkdir(exist_ok=True)
    QUEUE_ERROR_DIR.mkdir(exist_ok=True, parents=True)
    QUEUE_NO_REPLY_DIR.mkdir(exist_ok=True, parents=True)

    # Create Letta client with configuration
    CLIENT_PARAMS = {
        'token': letta_config['api_key'],
        'timeout': letta_config['timeout']
    }
    if letta_config.get('base_url'):
        CLIENT_PARAMS['base_url'] = letta_config['base_url']
    CLIENT = Letta(**CLIENT_PARAMS)
    
    # Configure logging based on command line arguments
    if args.simple_logs:
        log_format = "umbra - %(levelname)s - %(message)s"
    else:
        # Create custom formatter with symbols
        class SymbolFormatter(logging.Formatter):
            """Custom formatter that adds symbols for different log levels"""
            
            SYMBOLS = {
                logging.DEBUG: '◇',
                logging.INFO: '✓',
                logging.WARNING: '⚠',
                logging.ERROR: '✗',
                logging.CRITICAL: '‼'
            }
            
            def format(self, record):
                # Get the symbol for this log level
                symbol = self.SYMBOLS.get(record.levelno, '•')
                
                # Format time as HH:MM:SS
                timestamp = self.formatTime(record, "%H:%M:%S")
                
                # Build the formatted message
                level_name = f"{record.levelname:<5}"  # Left-align, 5 chars
                
                # Use vertical bar as separator
                parts = [symbol, timestamp, '│', level_name, '│', record.getMessage()]
                
                return ' '.join(parts)
        
        # Reset logging configuration
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # Create handler with custom formatter
        handler = logging.StreamHandler()
        if not args.simple_logs:
            handler.setFormatter(SymbolFormatter())
        else:
            handler.setFormatter(logging.Formatter(log_format))
        
        # Configure root logger
        logging.root.setLevel(logging.INFO)
        logging.root.addHandler(handler)
    
    global logger, prompt_logger, console
    logger = logging.getLogger("umbra_bot")
    logger.setLevel(logging.INFO)
    
    # Create a separate logger for prompts (set to WARNING to hide by default)
    prompt_logger = logging.getLogger("umbra_bot.prompts")
    if args.reasoning:
        prompt_logger.setLevel(logging.INFO)  # Show reasoning when --reasoning is used
    else:
        prompt_logger.setLevel(logging.WARNING)  # Hide by default
    
    # Disable httpx logging completely
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    
    # Create Rich console for pretty printing
    # Console no longer used - simple text formatting
    
    global TESTING_MODE, SKIP_GIT, SHOW_REASONING
    TESTING_MODE = args.test
    
    # Store no-git flag globally for use in export_agent_state calls
    SKIP_GIT = args.no_git
    
    # Store rich flag globally
    # Rich formatting no longer used
    
    # Store reasoning flag globally
    SHOW_REASONING = args.reasoning

    # Configure scheduled prompts module with same settings
    scheduled_prompts.configure(show_reasoning=SHOW_REASONING)

    if TESTING_MODE:
        logger.info("=== RUNNING IN TESTING MODE ===")
        logger.info("   - No messages will be sent to Bluesky")
        logger.info("   - Queue files will not be deleted")
        logger.info("   - Notifications will not be marked as seen")
        print("\n")
    
    # Check for synthesis-only mode
    SYNTHESIS_ONLY = args.synthesis_only
    if SYNTHESIS_ONLY:
        logger.info("=== RUNNING IN SYNTHESIS-ONLY MODE ===")
        logger.info("   - Only synthesis messages will be sent")
        logger.info("   - No notification processing")
        logger.info("   - No Bluesky client needed")
        print("\n")
    """Main bot loop that continuously monitors for notifications."""
    global start_time
    start_time = time.time()
    logger.info("=== STARTING UMBRA BOT ===")
    umbra_agent = initialize_umbra()
    logger.info(f"Umbra agent initialized: {umbra_agent.id}")
    
    # Initialize notification database with config-based path
    logger.info("Initializing notification database...")
    NOTIFICATION_DB = NotificationDB(db_path=queue_config['db_path'])
    
    # Migrate from old JSON format if it exists
    if PROCESSED_NOTIFICATIONS_FILE.exists():
        logger.info("Found old processed_notifications.json, migrating to database...")
        NOTIFICATION_DB.migrate_from_json(str(PROCESSED_NOTIFICATIONS_FILE))
    
    # Log database stats
    db_stats = NOTIFICATION_DB.get_stats()
    logger.info(f"Database initialized - Total notifications: {db_stats.get('total', 0)}, Recent (24h): {db_stats.get('recent_24h', 0)}")
    
    # Clean up old records
    NOTIFICATION_DB.cleanup_old_records(days=7)
    
    # Ensure correct tools are attached for Bluesky
    logger.info("Configuring tools for Bluesky platform...")
    try:
        from tool_manager import ensure_platform_tools
        ensure_platform_tools('bluesky', umbra_agent.id)
    except Exception as e:
        logger.error(f"Failed to configure platform tools: {e}")
        logger.warning("Continuing with existing tool configuration")
    
    # Check if agent has required tools
    if hasattr(umbra_agent, 'tools') and umbra_agent.tools:
        tool_names = [tool.name for tool in umbra_agent.tools]
        # Check for bluesky-related tools
        bluesky_tools = [name for name in tool_names if 'bluesky' in name.lower() or 'reply' in name.lower()]
        if not bluesky_tools:
            logger.warning("No Bluesky-related tools found! Agent may not be able to reply.")
    else:
        logger.warning("Agent has no tools registered!")

    # Clean up all user blocks at startup
    logger.info("🧹 Cleaning up user blocks at startup...")
    periodic_user_block_cleanup(CLIENT, umbra_agent.id)
    
    # Initialize Bluesky client (needed for both notification processing and synthesis acks/posts)
    if not SYNTHESIS_ONLY:
        atproto_client = bsky_utils.default_login()
        logger.info("Connected to Bluesky")
    else:
        # In synthesis-only mode, still connect for acks and posts (unless in test mode)
        if not args.test:
            atproto_client = bsky_utils.default_login()
            logger.info("Connected to Bluesky (for synthesis acks/posts)")
        else:
            atproto_client = None
            logger.info("Skipping Bluesky connection (test mode)")

    # Configure cleanup interval
    CLEANUP_INTERVAL = args.cleanup_interval

    # Build task enabled overrides from command line args
    # Only include overrides for tasks that are explicitly disabled
    global TASK_ENABLED_OVERRIDES
    TASK_ENABLED_OVERRIDES = {}
    if args.no_synthesis:
        TASK_ENABLED_OVERRIDES['synthesis'] = False
    if args.no_mutuals_engagement:
        TASK_ENABLED_OVERRIDES['mutuals_engagement'] = False
    if args.no_daily_review:
        TASK_ENABLED_OVERRIDES['daily_review'] = False
    if args.no_feed_engagement:
        TASK_ENABLED_OVERRIDES['feed_engagement'] = False
    if args.no_curiosities:
        TASK_ENABLED_OVERRIDES['curiosities_exploration'] = False

    # Synthesis-only mode
    if SYNTHESIS_ONLY:
        synthesis_config = TASK_CONFIGS.get('synthesis', {})
        synthesis_interval = synthesis_config.get('interval_seconds', 43200)

        logger.info(f"Starting synthesis-only mode, interval: {synthesis_interval} seconds ({synthesis_interval/60:.1f} minutes)")

        while True:
            try:
                # Send synthesis message immediately on first run
                logger.info("🧠 Sending synthesis message")
                send_synthesis_message(CLIENT, umbra_agent.id, atproto_client)

                # Wait for next interval
                logger.info(f"Waiting {synthesis_interval} seconds until next synthesis...")
                time.sleep(synthesis_interval)

            except KeyboardInterrupt:
                logger.info("=== SYNTHESIS MODE STOPPED BY USER ===")
                break
            except Exception as e:
                logger.error(f"Error in synthesis loop: {e}")
                logger.info(f"Sleeping for {synthesis_interval} seconds due to error...")
                time.sleep(synthesis_interval)
    
    # Normal mode with notification processing
    logger.info(f"Starting notification monitoring, checking every {FETCH_NOTIFICATIONS_DELAY_SEC} seconds")

    cycle_count = 0
    
    if CLEANUP_INTERVAL > 0:
        logger.info(f"User block cleanup enabled every {CLEANUP_INTERVAL} cycles")
    else:
        logger.info("User block cleanup disabled")
    
    # Initialize scheduled tasks from database (persists across restarts)
    # Uses configurations from TASK_CONFIGS in scheduled_prompts.py
    # with any overrides from command line arguments
    initialize_all_scheduled_tasks(NOTIFICATION_DB, TASK_ENABLED_OVERRIDES)

    while True:
        try:
            cycle_count += 1
            process_notifications(umbra_agent, atproto_client, TESTING_MODE)

            # Check for due scheduled tasks (persistent scheduling)
            if NOTIFICATION_DB:
                due_tasks = NOTIFICATION_DB.get_due_tasks()
                for task in due_tasks:
                    task_name = task['task_name']
                    config = TASK_CONFIGS.get(task_name, {})
                    emoji = config.get('emoji', '⏰')
                    desc = config.get('description', task_name)

                    logger.info(f"{emoji} Executing scheduled task: {desc}")

                    # Execute task with error handling to ensure rescheduling happens
                    # even if the task fails (prevents duplicate execution on next cycle)
                    try:
                        if task_name == 'synthesis':
                            send_synthesis_message(CLIENT, umbra_agent.id, atproto_client)
                        elif task_name == 'mutuals_engagement':
                            send_mutuals_engagement_message(CLIENT, umbra_agent.id)
                        elif task_name == 'daily_review':
                            send_daily_review_message(CLIENT, umbra_agent.id, atproto_client)
                        elif task_name == 'feed_engagement':
                            send_feed_engagement_message(CLIENT, umbra_agent.id)
                        elif task_name == 'curiosities_exploration':
                            send_curiosities_exploration_message(CLIENT, umbra_agent.id)
                        else:
                            logger.warning(f"Unknown task type: {task_name}")
                            continue
                    except Exception as task_error:
                        logger.error(f"{emoji} Error executing {desc}: {task_error}")
                        # Continue to reschedule even on error to prevent duplicate execution

                    # Always reschedule the task after execution (even on error)
                    reschedule_task_after_execution(NOTIFICATION_DB, task_name, task)

            # Run periodic cleanup every N cycles
            if CLEANUP_INTERVAL > 0 and cycle_count % CLEANUP_INTERVAL == 0:
                logger.debug(f"Running periodic user block cleanup (cycle {cycle_count})")
                periodic_user_block_cleanup(CLIENT, umbra_agent.id)
                
                # Also check database health when doing cleanup
                if NOTIFICATION_DB:
                    db_stats = NOTIFICATION_DB.get_stats()
                    pending = db_stats.get('status_pending', 0)
                    errors = db_stats.get('status_error', 0)
                    
                    if pending > 50:
                        logger.warning(f"⚠️ Queue health check: {pending} pending notifications (may be stuck)")
                    if errors > 20:
                        logger.warning(f"⚠️ Queue health check: {errors} error notifications")
                    
                    # Periodic cleanup of old records
                    if cycle_count % (CLEANUP_INTERVAL * 10) == 0:  # Every 100 cycles
                        logger.info("Running database cleanup of old records...")
                        NOTIFICATION_DB.cleanup_old_records(days=7)
            
            # Log cycle completion with stats
            elapsed_time = time.time() - start_time
            total_messages = sum(message_counters.values())
            messages_per_minute = (total_messages / elapsed_time * 60) if elapsed_time > 0 else 0
            
            if total_messages > 0:
                logger.info(f"Cycle {cycle_count} complete. Session totals: {total_messages} messages ({message_counters['mentions']} mentions, {message_counters['replies']} replies) | {messages_per_minute:.1f} msg/min")
            time.sleep(FETCH_NOTIFICATIONS_DELAY_SEC)

        except KeyboardInterrupt:
            # Final stats
            elapsed_time = time.time() - start_time
            total_messages = sum(message_counters.values())
            messages_per_minute = (total_messages / elapsed_time * 60) if elapsed_time > 0 else 0
            
            logger.info("=== BOT STOPPED BY USER ===")
            logger.info(f"Final session stats: {total_messages} total messages processed in {elapsed_time/60:.1f} minutes")
            logger.info(f"   - {message_counters['mentions']} mentions")
            logger.info(f"   - {message_counters['replies']} replies")
            logger.info(f"   - {message_counters['follows']} follows")
            logger.info(f"   - {message_counters['reposts_skipped']} reposts skipped")
            logger.info(f"   - Average rate: {messages_per_minute:.1f} messages/minute")
            
            # Close database connection
            if NOTIFICATION_DB:
                logger.info("Closing database connection...")
                NOTIFICATION_DB.close()
            
            break
        except Exception as e:
            logger.error(f"=== ERROR IN MAIN LOOP CYCLE {cycle_count} ===")
            logger.error(f"Error details: {e}")
            # Wait a bit longer on errors
            logger.info(f"Sleeping for {FETCH_NOTIFICATIONS_DELAY_SEC * 2} seconds due to error...")
            time.sleep(FETCH_NOTIFICATIONS_DELAY_SEC * 2)


if __name__ == "__main__":
    main()
