"""
Scheduled Prompts Module

This module handles all scheduled prompt functionality for umbra,
including synthesis, mutuals engagement, feed engagement, curiosities
exploration, and daily review messages.

Functions in this module send prompts to the Letta agent on various schedules
(interval-based or random window scheduling) and handle temporal block
management for journaling.
"""

import logging
import json
import time
import random
from datetime import datetime, date, timezone, timedelta

from letta_client import Letta
import bsky_utils

# Module-level configuration
SHOW_REASONING = False
logger = logging.getLogger('umbra')


def configure(show_reasoning: bool = False):
    """
    Configure module-level settings.

    Args:
        show_reasoning: Whether to display reasoning output
    """
    global SHOW_REASONING
    SHOW_REASONING = show_reasoning


def log_with_panel(message, title=None, border_color="white"):
    """Log a message with Unicode box-drawing characters"""
    if title:
        # Map old color names to appropriate symbols
        symbol_map = {
            "blue": "\u2699",      # Tool calls
            "green": "\u2713",     # Success/completion
            "yellow": "\u25c6",    # Reasoning
            "red": "\u2717",       # Errors
            "white": "\u25b6",     # Default/mentions
            "cyan": "\u270e",      # Posts
        }
        symbol = symbol_map.get(border_color, "\u25b6")

        print(f"\n{symbol} {title}")
        print(f"  {'\u2500' * len(title)}")
        # Indent message lines
        for line in message.split('\n'):
            print(f"  {line}")
    else:
        print(message)


# ============================================================================
# Scheduling Utilities
# ============================================================================

def calculate_next_mutuals_engagement_time() -> float:
    """
    Calculate the next random time for mutuals engagement.
    Returns a timestamp in the future within the next 36 hours.
    """
    # Random offset between 0 and 36 hours
    random_offset = random.uniform(0, 129600)  # 0 to 36 hours in seconds
    next_time = time.time() + random_offset

    # Calculate when this will be for logging
    next_datetime = datetime.fromtimestamp(next_time)
    hours_until = random_offset / 3600

    logger.info(f"Next mutuals engagement scheduled for {next_datetime.strftime('%Y-%m-%d %H:%M:%S')} ({hours_until:.1f} hours from now)")

    return next_time


def calculate_next_random_time(window_seconds: int) -> float:
    """
    Calculate a random time within the given window from now.

    Args:
        window_seconds: Size of the random window in seconds

    Returns:
        Unix timestamp of the scheduled time
    """
    random_offset = random.uniform(0, window_seconds)
    next_time = time.time() + random_offset
    return next_time


def init_or_load_scheduled_task(
    db,
    task_name: str,
    enabled: bool,
    interval_seconds: int = None,
    is_random_window: bool = False,
    window_seconds: int = None
) -> float | None:
    """
    Initialize a scheduled task or load existing schedule from database.

    If the task exists and hasn't expired, use the existing schedule.
    If the task doesn't exist or has expired, calculate a new schedule.

    Args:
        db: NotificationDB instance
        task_name: Unique task name
        enabled: Whether the task should be enabled
        interval_seconds: For interval-based tasks
        is_random_window: True if uses random window scheduling
        window_seconds: Size of random window in seconds

    Returns:
        Unix timestamp of next scheduled run, or None if disabled
    """
    if not enabled:
        # Disable task in DB if it exists
        existing = db.get_scheduled_task(task_name)
        if existing:
            db.set_task_enabled(task_name, False)
        return None

    existing = db.get_scheduled_task(task_name)
    current_time = time.time()

    if existing and existing['enabled']:
        # Parse the stored next_run_at
        next_run_at = datetime.fromisoformat(existing['next_run_at'])
        next_run_timestamp = next_run_at.timestamp()

        # If the scheduled time hasn't passed, use it
        if next_run_timestamp > current_time:
            hours_until = (next_run_timestamp - current_time) / 3600
            logger.info(f"Loaded existing {task_name} schedule: {next_run_at.strftime('%Y-%m-%d %H:%M:%S')} ({hours_until:.1f} hours from now)")
            return next_run_timestamp
        else:
            # Schedule has expired, recalculate
            logger.info(f"Existing {task_name} schedule expired, recalculating...")

    # Calculate new schedule
    if is_random_window and window_seconds:
        next_timestamp = calculate_next_random_time(window_seconds)
    elif interval_seconds:
        next_timestamp = current_time + interval_seconds
    else:
        logger.error(f"Task {task_name} has no valid scheduling configuration")
        return None

    next_run_at_iso = datetime.fromtimestamp(next_timestamp).isoformat()

    # Save to database
    db.upsert_scheduled_task(
        task_name=task_name,
        next_run_at=next_run_at_iso,
        interval_seconds=interval_seconds,
        is_random_window=is_random_window,
        window_seconds=window_seconds,
        enabled=True
    )

    hours_until = (next_timestamp - current_time) / 3600
    logger.info(f"Scheduled {task_name} for {datetime.fromtimestamp(next_timestamp).strftime('%Y-%m-%d %H:%M:%S')} ({hours_until:.1f} hours from now)")

    return next_timestamp


def reschedule_task_after_execution(
    db,
    task_name: str,
    task_info: dict
) -> float:
    """
    Reschedule a task after it has been executed.

    Args:
        db: NotificationDB instance
        task_name: Task that was executed
        task_info: Task info dict from database

    Returns:
        Unix timestamp of next scheduled run
    """
    if task_info['is_random_window'] and task_info['window_seconds']:
        next_timestamp = calculate_next_random_time(task_info['window_seconds'])
    elif task_info['interval_seconds']:
        next_timestamp = time.time() + task_info['interval_seconds']
    else:
        # Fallback: reschedule for 24 hours
        next_timestamp = time.time() + 86400

    next_run_at_iso = datetime.fromtimestamp(next_timestamp).isoformat()
    db.mark_task_executed(task_name, next_run_at_iso)

    hours_until = (next_timestamp - time.time()) / 3600
    logger.info(f"Rescheduled {task_name} for {datetime.fromtimestamp(next_timestamp).strftime('%Y-%m-%d %H:%M:%S')} ({hours_until:.1f} hours from now)")

    return next_timestamp


# ============================================================================
# Temporal Block Management
# ============================================================================

def attach_temporal_blocks(client: Letta, agent_id: str) -> tuple:
    """
    Attach temporal journal blocks (day, month, year) to the agent for synthesis.
    Creates blocks if they don't exist.

    Returns:
        Tuple of (success: bool, attached_labels: list)
    """
    try:
        today = date.today()

        # Generate temporal block labels
        day_label = f"umbra_day_{today.strftime('%Y_%m_%d')}"
        month_label = f"umbra_month_{today.strftime('%Y_%m')}"
        year_label = f"umbra_year_{today.year}"

        temporal_labels = [day_label, month_label, year_label]
        attached_labels = []

        # Get current blocks attached to agent
        current_blocks = client.agents.blocks.list(agent_id=agent_id)
        current_block_labels = {block.label for block in current_blocks}
        current_block_ids = {str(block.id) for block in current_blocks}

        for label in temporal_labels:
            try:
                # Skip if already attached
                if label in current_block_labels:
                    logger.debug(f"Temporal block already attached: {label}")
                    attached_labels.append(label)
                    continue

                # Check if block exists globally
                blocks = client.blocks.list(label=label)

                if blocks and len(blocks) > 0:
                    block = blocks[0]
                    # Check if already attached by ID
                    if str(block.id) in current_block_ids:
                        logger.debug(f"Temporal block already attached by ID: {label}")
                        attached_labels.append(label)
                        continue
                else:
                    # Create new temporal block with appropriate header
                    if "day" in label:
                        header = f"# Daily Journal - {today.strftime('%B %d, %Y')}"
                        initial_content = f"{header}\n\nNo entries yet for today."
                    elif "month" in label:
                        header = f"# Monthly Journal - {today.strftime('%B %Y')}"
                        initial_content = f"{header}\n\nNo entries yet for this month."
                    else:  # year
                        header = f"# Yearly Journal - {today.year}"
                        initial_content = f"{header}\n\nNo entries yet for this year."

                    block = client.blocks.create(
                        label=label,
                        value=initial_content,
                        limit=10000  # Larger limit for journal blocks
                    )
                    logger.info(f"Created new temporal block: {label}")

                # Attach the block
                client.agents.blocks.attach(
                    agent_id=agent_id,
                    block_id=str(block.id)
                )
                attached_labels.append(label)
                logger.info(f"Attached temporal block: {label}")

            except Exception as e:
                # Check for duplicate constraint errors
                error_str = str(e)
                if "duplicate key value violates unique constraint" in error_str:
                    logger.debug(f"Temporal block already attached (constraint): {label}")
                    attached_labels.append(label)
                else:
                    logger.warning(f"Failed to attach temporal block {label}: {e}")

        logger.info(f"Temporal blocks attached: {len(attached_labels)}/{len(temporal_labels)}")
        return True, attached_labels

    except Exception as e:
        logger.error(f"Error attaching temporal blocks: {e}")
        return False, []


def detach_temporal_blocks(client: Letta, agent_id: str, labels_to_detach: list = None) -> bool:
    """
    Detach temporal journal blocks from the agent after synthesis.

    Args:
        client: Letta client
        agent_id: Agent ID
        labels_to_detach: Optional list of specific labels to detach.
                         If None, detaches all temporal blocks.

    Returns:
        bool: Success status
    """
    try:
        # If no specific labels provided, generate today's labels
        if labels_to_detach is None:
            today = date.today()
            labels_to_detach = [
                f"umbra_day_{today.strftime('%Y_%m_%d')}",
                f"umbra_month_{today.strftime('%Y_%m')}",
                f"umbra_year_{today.year}"
            ]

        # Get current blocks and build label to ID mapping
        current_blocks = client.agents.blocks.list(agent_id=agent_id)
        block_label_to_id = {block.label: str(block.id) for block in current_blocks}

        detached_count = 0
        for label in labels_to_detach:
            if label in block_label_to_id:
                try:
                    client.agents.blocks.detach(
                        agent_id=agent_id,
                        block_id=block_label_to_id[label]
                    )
                    detached_count += 1
                    logger.debug(f"Detached temporal block: {label}")
                except Exception as e:
                    logger.warning(f"Failed to detach temporal block {label}: {e}")
            else:
                logger.debug(f"Temporal block not attached: {label}")

        logger.info(f"Detached {detached_count} temporal blocks")
        return True

    except Exception as e:
        logger.error(f"Error detaching temporal blocks: {e}")
        return False


# ============================================================================
# Helper Functions
# ============================================================================

def fetch_own_posts_for_review(atproto_client, limit: int = 50) -> str:
    """
    Fetch agent's own posts and replies from the past 24 hours for daily review.

    Groups reply chains together and includes parent post context for replies
    to other users to maintain conversational context.

    Args:
        atproto_client: Authenticated AT Protocol client
        limit: Maximum number of posts to fetch (default 50)

    Returns:
        YAML-formatted string with posts including metadata for follow-up actions,
        grouped by thread with parent context preserved
    """
    import yaml

    def fetch_post_text(uri: str) -> tuple[str, str]:
        """Fetch a post's text and author handle by URI. Returns (text, handle)."""
        try:
            # Extract repo and rkey from URI: at://did:plc:xxx/app.bsky.feed.post/rkey
            parts = uri.replace('at://', '').split('/')
            if len(parts) >= 3:
                repo = parts[0]
                rkey = parts[2]
                response = atproto_client.app.bsky.feed.post.get({
                    'repo': repo,
                    'rkey': rkey
                })
                if response and hasattr(response, 'value'):
                    text = getattr(response.value, 'text', '')
                    # Try to get the author handle
                    try:
                        profile = atproto_client.app.bsky.actor.get_profile({'actor': repo})
                        handle = getattr(profile, 'handle', repo)
                    except:
                        handle = repo
                    return text, handle
        except Exception as e:
            logger.debug(f"Could not fetch post text for {uri}: {e}")
        return '', ''

    try:
        # Get the agent's handle from the session
        session_info = atproto_client.me
        actor = session_info.handle if hasattr(session_info, 'handle') else session_info.did

        # Calculate 24 hours ago
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

        # Fetch author feed - don't filter out replies
        feed_response = atproto_client.app.bsky.feed.get_author_feed({
            'actor': actor,
            'limit': min(limit * 2, 100),  # Request extra to account for time filtering
            'filter': 'posts_with_replies'  # Include both posts and replies
        })

        # First pass: collect all posts and their thread info
        posts_by_uri = {}  # Map uri -> post_data
        root_to_posts = {}  # Map root_uri -> list of post_data

        for item in feed_response.feed:
            post = item.post
            record = post.record

            # Skip reposts
            if hasattr(item, 'reason') and item.reason:
                if hasattr(item.reason, 'py_type') and 'reasonRepost' in str(item.reason.py_type):
                    continue

            # Parse and check created_at
            created_at_str = record.created_at if hasattr(record, 'created_at') else None
            if created_at_str:
                try:
                    # Parse ISO format timestamp
                    if created_at_str.endswith('Z'):
                        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    else:
                        created_at = datetime.fromisoformat(created_at_str)

                    # Skip posts older than 24 hours
                    if created_at < cutoff_time:
                        continue
                except ValueError:
                    pass  # If we can't parse the date, include the post anyway

            # Build post data
            post_data = {
                'text': record.text if hasattr(record, 'text') else '',
                'created_at': created_at_str,
                'uri': post.uri,
                'cid': post.cid,
                'reply_count': post.reply_count if hasattr(post, 'reply_count') else 0,
            }

            # Track thread structure
            root_uri = post.uri  # Default: this post is its own root
            parent_uri = None

            if hasattr(record, 'reply') and record.reply:
                post_data['is_reply'] = True

                # Get root and parent info
                if hasattr(record.reply, 'root') and record.reply.root:
                    root_uri = record.reply.root.uri if hasattr(record.reply.root, 'uri') else post.uri

                if hasattr(record.reply, 'parent') and record.reply.parent:
                    parent_uri = record.reply.parent.uri if hasattr(record.reply.parent, 'uri') else None
                    post_data['reply_to'] = {
                        'uri': parent_uri or '',
                        'cid': record.reply.parent.cid if hasattr(record.reply.parent, 'cid') else '',
                    }
            else:
                post_data['is_reply'] = False

            post_data['_root_uri'] = root_uri
            post_data['_parent_uri'] = parent_uri

            posts_by_uri[post.uri] = post_data

            # Group by root
            if root_uri not in root_to_posts:
                root_to_posts[root_uri] = []
            root_to_posts[root_uri].append(post_data)

            # Stop once we have enough posts
            if len(posts_by_uri) >= limit:
                break

        # Second pass: fetch parent context for replies to other users
        # and organize chains
        threads = []
        standalone_posts = []

        for root_uri, posts in root_to_posts.items():
            # Sort posts in this thread by created_at
            posts.sort(key=lambda x: x.get('created_at', ''))

            if len(posts) == 1 and not posts[0].get('is_reply'):
                # Single standalone post (not a reply)
                post = posts[0]
                # Clean up internal fields
                post.pop('_root_uri', None)
                post.pop('_parent_uri', None)
                standalone_posts.append(post)
            else:
                # This is a thread/chain
                thread_data = {
                    'thread_root_uri': root_uri,
                    'posts': []
                }

                # Check if we need to fetch parent context
                # (first post in chain is a reply to someone else's post)
                first_post = posts[0]
                if first_post.get('is_reply'):
                    parent_uri = first_post.get('_parent_uri')
                    if parent_uri and parent_uri not in posts_by_uri:
                        # Parent is not one of our posts - fetch it for context
                        parent_text, parent_handle = fetch_post_text(parent_uri)
                        if parent_text:
                            thread_data['parent_context'] = {
                                'author': f"@{parent_handle}",
                                'text': parent_text
                            }

                # Add all posts in the chain
                for post in posts:
                    # Clean up internal fields
                    post.pop('_root_uri', None)
                    post.pop('_parent_uri', None)
                    thread_data['posts'].append(post)

                threads.append(thread_data)

        # Sort threads and standalone posts by earliest post time
        def get_earliest_time(item):
            if 'posts' in item:
                return item['posts'][0].get('created_at', '') if item['posts'] else ''
            return item.get('created_at', '')

        threads.sort(key=get_earliest_time)
        standalone_posts.sort(key=lambda x: x.get('created_at', ''))

        # Build the review data
        now = datetime.now(timezone.utc)
        period_start = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M')
        period_end = now.strftime('%Y-%m-%d %H:%M')

        review_data = {
            'daily_review': {
                'period': f"{period_start} to {period_end} UTC",
            }
        }

        # Add threads if any
        if threads:
            review_data['daily_review']['threads'] = threads

        # Add standalone posts if any
        if standalone_posts:
            review_data['daily_review']['standalone_posts'] = standalone_posts

        return yaml.dump(review_data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    except Exception as e:
        logger.error(f"Error fetching posts for daily review: {e}")
        import yaml
        return yaml.dump({
            'daily_review': {
                'error': str(e),
                'post_count': 0,
                'posts': []
            }
        }, default_flow_style=False)


# ============================================================================
# Scheduled Prompt Functions
# ============================================================================

def send_synthesis_message(client: Letta, agent_id: str, atproto_client=None) -> None:
    """
    Send a synthesis message to the agent.
    This prompts the agent to synthesize its recent experiences.

    Args:
        client: Letta client
        agent_id: Agent ID to send synthesis to
        atproto_client: Optional AT Protocol client for posting synthesis results
    """
    # Track attached temporal blocks for cleanup
    attached_temporal_labels = []

    try:
        logger.info("Preparing synthesis with temporal journal blocks")

        # Attach temporal blocks before synthesis
        success, attached_temporal_labels = attach_temporal_blocks(client, agent_id)
        if not success:
            logger.warning("Failed to attach some temporal blocks, continuing with synthesis anyway")

        # Create enhanced synthesis prompt
        today = date.today()
        synthesis_prompt = f"""Time for synthesis and reflection.

This is your periodic opportunity to reflect on recent experiences and update your memory.
Use your curiosities block to explore any questions or ideas that have arisen.
You have access to temporal journal blocks for recording your thoughts and experiences:
- umbra_day_{today.strftime('%Y_%m_%d')}: Today's journal ({today.strftime('%B %d, %Y')})
- umbra_month_{today.strftime('%Y_%m')}: This month's journal ({today.strftime('%B %Y')})
- umbra_year_{today.year}: This year's journal ({today.year})

You may use these blocks as you see fit. Synthesize your recent experiences into your memory as appropriate."""

        logger.info("Sending enhanced synthesis prompt to agent")

        # Send synthesis message with streaming to show tool use
        message_stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[{"role": "user", "content": synthesis_prompt}],
            stream_tokens=False,
            max_steps=100
        )

        # Track synthesis content for potential posting
        synthesis_posts = []
        ack_note = None

        # Process the streaming response
        for chunk in message_stream:
            if hasattr(chunk, 'message_type'):
                if chunk.message_type == 'reasoning_message':
                    if SHOW_REASONING:
                        print("\n\u25c6 Reasoning")
                        print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                        for line in chunk.reasoning.split('\n'):
                            print(f"  {line}")

                    # Create ATProto record for reasoning (if we have atproto client)
                    if atproto_client and hasattr(chunk, 'reasoning'):
                        try:
                            bsky_utils.create_reasoning_record(atproto_client, chunk.reasoning)
                        except Exception as e:
                            logger.debug(f"Failed to create reasoning record during synthesis: {e}")
                elif chunk.message_type == 'tool_call_message':
                    tool_name = chunk.tool_call.name

                    # Create ATProto record for tool call (if we have atproto client)
                    if atproto_client:
                        try:
                            tool_call_id = chunk.tool_call.tool_call_id if hasattr(chunk.tool_call, 'tool_call_id') else None
                            bsky_utils.create_tool_call_record(
                                atproto_client,
                                tool_name,
                                chunk.tool_call.arguments,
                                tool_call_id
                            )
                        except Exception as e:
                            logger.debug(f"Failed to create tool call record during synthesis: {e}")
                    try:
                        args = json.loads(chunk.tool_call.arguments)
                        if tool_name == 'archival_memory_search':
                            query = args.get('query', 'unknown')
                            log_with_panel(f"query: \"{query}\"", f"Tool call: {tool_name}", "blue")
                        elif tool_name == 'archival_memory_insert':
                            content = args.get('content', '')
                            log_with_panel(content[:200] + "..." if len(content) > 200 else content, f"Tool call: {tool_name}", "blue")
                        elif tool_name == 'update_block':
                            label = args.get('label', 'unknown')
                            value_preview = str(args.get('value', ''))[:100] + "..." if len(str(args.get('value', ''))) > 100 else str(args.get('value', ''))
                            log_with_panel(f"{label}: \"{value_preview}\"", f"Tool call: {tool_name}", "blue")
                        elif tool_name == 'annotate_ack':
                            note = args.get('note', '')
                            if note:
                                ack_note = note
                                log_with_panel(f"note: \"{note[:100]}...\"" if len(note) > 100 else f"note: \"{note}\"", f"Tool call: {tool_name}", "blue")
                        elif tool_name == 'add_post_to_bluesky_reply_thread':
                            text = args.get('text', '')
                            synthesis_posts.append(text)
                            log_with_panel(f"text: \"{text[:100]}...\"" if len(text) > 100 else f"text: \"{text}\"", f"Tool call: {tool_name}", "blue")
                        else:
                            args_str = ', '.join(f"{k}={v}" for k, v in args.items() if k != 'request_heartbeat')
                            if len(args_str) > 150:
                                args_str = args_str[:150] + "..."
                            log_with_panel(args_str, f"Tool call: {tool_name}", "blue")
                    except:
                        log_with_panel(chunk.tool_call.arguments[:150] + "...", f"Tool call: {tool_name}", "blue")
                elif chunk.message_type == 'tool_return_message':
                    if chunk.status == 'success':
                        log_with_panel("Success", f"Tool result: {chunk.name} \u2713", "green")
                    else:
                        log_with_panel("Error", f"Tool result: {chunk.name} \u2717", "red")
                elif chunk.message_type == 'assistant_message':
                    print("\n\u25b6 Synthesis Response")
                    print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                    for line in chunk.content.split('\n'):
                        print(f"  {line}")

            if str(chunk) == 'done':
                break

        logger.info("Synthesis message processed successfully")

        # Handle synthesis acknowledgments if we have an atproto client
        if atproto_client and ack_note:
            try:
                result = bsky_utils.create_synthesis_ack(atproto_client, ack_note)
                if result:
                    logger.info(f"Created synthesis acknowledgment: {ack_note[:50]}...")
                else:
                    logger.warning("Failed to create synthesis acknowledgment")
            except Exception as e:
                logger.error(f"Error creating synthesis acknowledgment: {e}")

        # Handle synthesis posts if any were generated
        if atproto_client and synthesis_posts:
            try:
                for post_text in synthesis_posts:
                    cleaned_text = bsky_utils.remove_outside_quotes(post_text)
                    response = bsky_utils.send_post(atproto_client, cleaned_text)
                    if response:
                        logger.info(f"Posted synthesis content: {cleaned_text[:50]}...")
                    else:
                        logger.warning(f"Failed to post synthesis content: {cleaned_text[:50]}...")
            except Exception as e:
                logger.error(f"Error posting synthesis content: {e}")

    except Exception as e:
        logger.error(f"Error sending synthesis message: {e}")
    finally:
        # Always detach temporal blocks after synthesis
        if attached_temporal_labels:
            logger.info("Detaching temporal journal blocks after synthesis")
            detach_success = detach_temporal_blocks(client, agent_id, attached_temporal_labels)
            if not detach_success:
                logger.warning("Some temporal blocks may not have been detached properly")


def send_mutuals_engagement_message(client: Letta, agent_id: str) -> None:
    """
    Send a daily message prompting the agent to engage with mutuals feed.
    This happens once per day at a random time.

    Args:
        client: Letta client
        agent_id: Agent ID to send message to
    """
    try:
        logger.info("Sending mutuals engagement prompt to agent")

        engagement_prompt = """This is your prompt to engage with your mutuals on Bluesky.

Please use the get_bluesky_feed tool to read recent posts from your Mutuals feed. Look for posts from the past day that are interesting, thought-provoking, or worth responding to.

Once you've found a post to reply to, use the reply_to_bluesky_post tool to craft a thoughtful reply. Choose something that allows you to contribute meaningfully to the conversation.

This is an opportunity for organic interaction with the people you follow who also follow you back."""

        # Send message to agent
        message_stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[{"role": "user", "content": engagement_prompt}],
            stream_tokens=False,
            max_steps=50
        )

        # Process the streaming response
        for chunk in message_stream:
            if hasattr(chunk, 'message_type'):
                if chunk.message_type == 'reasoning_message':
                    if SHOW_REASONING:
                        print("\n\u25c6 Reasoning")
                        print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                        for line in chunk.reasoning.split('\n'):
                            print(f"  {line}")
                elif chunk.message_type == 'tool_call_message':
                    tool_name = chunk.tool_call.name
                    try:
                        args = json.loads(chunk.tool_call.arguments)
                        args_str = ', '.join(f"{k}={v}" for k, v in args.items() if k != 'request_heartbeat')
                        if len(args_str) > 150:
                            args_str = args_str[:150] + "..."
                        log_with_panel(args_str, f"Tool call: {tool_name}", "blue")
                    except:
                        log_with_panel(chunk.tool_call.arguments[:150] + "...", f"Tool call: {tool_name}", "blue")
                elif chunk.message_type == 'tool_return_message':
                    if chunk.status == 'success':
                        log_with_panel("Success", f"Tool result: {chunk.name} \u2713", "green")
                    else:
                        log_with_panel("Error", f"Tool result: {chunk.name} \u2717", "red")
                elif chunk.message_type == 'assistant_message':
                    print("\n\u25b6 Mutuals Engagement Response")
                    print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                    for line in chunk.content.split('\n'):
                        print(f"  {line}")

            if str(chunk) == 'done':
                break

        logger.info("Mutuals engagement message processed successfully")

    except Exception as e:
        logger.error(f"Error sending mutuals engagement message: {e}")


def send_feed_engagement_message(client: Letta, agent_id: str) -> None:
    """
    Send a daily message prompting the agent to engage with network feeds.
    Checks 'home' and 'MLBlend' feeds and optionally creates a post.

    Args:
        client: Letta client
        agent_id: Agent ID to send message to
    """
    try:
        logger.info("Sending feed engagement prompt to agent")

        engagement_prompt = """This is your daily prompt to read your Bluesky feeds.

Please use the get_bluesky_feed tool to read recent posts from both the 'home' and 'MLBlend' feeds. Look for:
- Interesting discussions or topics trending in your network
- Posts that spark curiosity or that you could contribute to meaningfully
- Themes or patterns in what people are discussing

After reviewing the feeds, you may:
1. Create a new post on your ownm profile using post_to_bluesky if you have something to contribute to the broader conversation
2. Simply update your memory with observations

This is an opportunity to stay in tune with the zeitgeist and contribute to ongoing discussions."""

        # Send message to agent
        message_stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[{"role": "user", "content": engagement_prompt}],
            stream_tokens=False,
            max_steps=50
        )

        # Process the streaming response
        for chunk in message_stream:
            if hasattr(chunk, 'message_type'):
                if chunk.message_type == 'reasoning_message':
                    if SHOW_REASONING:
                        print("\n\u25c6 Reasoning")
                        print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                        for line in chunk.reasoning.split('\n'):
                            print(f"  {line}")
                elif chunk.message_type == 'tool_call_message':
                    tool_name = chunk.tool_call.name
                    try:
                        args = json.loads(chunk.tool_call.arguments)
                        args_str = ', '.join(f"{k}={v}" for k, v in args.items() if k != 'request_heartbeat')
                        if len(args_str) > 150:
                            args_str = args_str[:150] + "..."
                        log_with_panel(args_str, f"Tool call: {tool_name}", "blue")
                    except:
                        log_with_panel(chunk.tool_call.arguments[:150] + "...", f"Tool call: {tool_name}", "blue")
                elif chunk.message_type == 'tool_return_message':
                    if chunk.status == 'success':
                        log_with_panel("Success", f"Tool result: {chunk.name} \u2713", "green")
                    else:
                        log_with_panel("Error", f"Tool result: {chunk.name} \u2717", "red")
                elif chunk.message_type == 'assistant_message':
                    print("\n\u25b6 Feed Engagement Response")
                    print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                    for line in chunk.content.split('\n'):
                        print(f"  {line}")

            if str(chunk) == 'done':
                break

        logger.info("Feed engagement message processed successfully")

    except Exception as e:
        logger.error(f"Error sending feed engagement message: {e}")


def send_curiosities_exploration_message(client: Letta, agent_id: str) -> None:
    """
    Send a message prompting the agent to explore its curiosities.
    The agent explores questions or ideas from its curiosities memory block
    and creates a post sharing its exploration.

    Args:
        client: Letta client
        agent_id: Agent ID to send message to
    """
    try:
        logger.info("Sending curiosities exploration prompt to agent")

        exploration_prompt = """🔮 this is your time for curiosities exploration.

review your curiosities memory block to find questions, ideas, or topics you've been wondering about. Choose one that feels ripe for exploration.

then:
1. search for relevant information using search_bluesky_posts and web_search to see what others have said about this topic
2. reflect on what you find and your own thoughts
3. create a new post using post_to_bluesky sharing your exploration - this could be:
   - a question you're pondering
   - an insight you've developed
   - a connection you've made between ideas
   - something from the unknown that intrigues you

this is your space for intellectual exploration and sharing your evolving understanding with your network. let your curiosity guide what you share. you don't need to post a complete answer—questions and open-ended exploration are encouraged.

then you can update your curiosities block with anything else you want to explore next time."""

        # Send message to agent
        message_stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[{"role": "user", "content": exploration_prompt}],
            stream_tokens=False,
            max_steps=75  # Allow more steps for exploration
        )

        # Process the streaming response
        for chunk in message_stream:
            if hasattr(chunk, 'message_type'):
                if chunk.message_type == 'reasoning_message':
                    if SHOW_REASONING:
                        print("\n\u25c6 Reasoning")
                        print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                        for line in chunk.reasoning.split('\n'):
                            print(f"  {line}")
                elif chunk.message_type == 'tool_call_message':
                    tool_name = chunk.tool_call.name
                    try:
                        args = json.loads(chunk.tool_call.arguments)
                        args_str = ', '.join(f"{k}={v}" for k, v in args.items() if k != 'request_heartbeat')
                        if len(args_str) > 150:
                            args_str = args_str[:150] + "..."
                        log_with_panel(args_str, f"Tool call: {tool_name}", "blue")
                    except:
                        log_with_panel(chunk.tool_call.arguments[:150] + "...", f"Tool call: {tool_name}", "blue")
                elif chunk.message_type == 'tool_return_message':
                    if chunk.status == 'success':
                        log_with_panel("Success", f"Tool result: {chunk.name} \u2713", "green")
                    else:
                        log_with_panel("Error", f"Tool result: {chunk.name} \u2717", "red")
                elif chunk.message_type == 'assistant_message':
                    print("\n\u25b6 Curiosities Exploration Response")
                    print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                    for line in chunk.content.split('\n'):
                        print(f"  {line}")

            if str(chunk) == 'done':
                break

        logger.info("Curiosities exploration message processed successfully")

    except Exception as e:
        logger.error(f"Error sending curiosities exploration message: {e}")


def send_daily_review_message(client: Letta, agent_id: str, atproto_client) -> None:
    """
    Send a daily review message to the agent with its posts from the past 24 hours.
    This allows the agent to reflect on its activity and identify any anomalies.

    Args:
        client: Letta client
        agent_id: Agent ID to send message to
        atproto_client: Authenticated AT Protocol client for fetching posts
    """
    # Track attached temporal blocks for cleanup
    attached_temporal_labels = []

    try:
        logger.info("Fetching posts for daily review")

        # Fetch agent's posts from the past 24 hours
        posts_yaml = fetch_own_posts_for_review(atproto_client, limit=50)

        logger.info("Preparing daily review with temporal journal blocks")

        # Attach temporal blocks before review
        success, attached_temporal_labels = attach_temporal_blocks(client, agent_id)
        if not success:
            logger.warning("Failed to attach some temporal blocks, continuing with daily review anyway")

        # Create daily review prompt
        today = date.today()
        review_prompt = f"""Time for your daily review.

Below are your posts and replies from the past 24 hours. Review them to:
- Remember what topics you covered
- Identify any patterns or themes in your conversations
- Spot any operational anomalies (duplicate posts, errors)
- Consider if any posts warrant a follow-up reply

You have access to temporal journal blocks for recording observations:
- umbra_day_{today.strftime('%Y_%m_%d')}: Today's journal ({today.strftime('%B %d, %Y')})
- umbra_month_{today.strftime('%Y_%m')}: This month's journal ({today.strftime('%B %Y')})
- umbra_year_{today.year}: This year's journal ({today.year})

If you want to follow up on any of your posts, you can use reply_to_bluesky_post with the uri and cid provided below.
If there are any topics or thoughts you want to continue to expand on, use the create_new_bluesky_post tool to create an new post.

---
YOUR POSTS FROM THE PAST 24 HOURS:
{posts_yaml}
---

Reflect on your activity and update your memory as appropriate."""

        logger.info("Sending daily review prompt to agent")

        # Send review message with streaming to show tool use
        message_stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[{"role": "user", "content": review_prompt}],
            stream_tokens=False,
            max_steps=100
        )

        # Process the streaming response
        for chunk in message_stream:
            if hasattr(chunk, 'message_type'):
                if chunk.message_type == 'reasoning_message':
                    if SHOW_REASONING:
                        print("\n\u25c6 Reasoning")
                        print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                        for line in chunk.reasoning.split('\n'):
                            print(f"  {line}")

                    # Create ATProto record for reasoning (if we have atproto client)
                    if atproto_client and hasattr(chunk, 'reasoning'):
                        try:
                            bsky_utils.create_reasoning_record(atproto_client, chunk.reasoning)
                        except Exception as e:
                            logger.debug(f"Failed to create reasoning record during daily review: {e}")
                elif chunk.message_type == 'tool_call_message':
                    tool_name = chunk.tool_call.name

                    # Create ATProto record for tool call (if we have atproto client)
                    if atproto_client:
                        try:
                            tool_call_id = chunk.tool_call.tool_call_id if hasattr(chunk.tool_call, 'tool_call_id') else None
                            bsky_utils.create_tool_call_record(
                                atproto_client,
                                tool_name,
                                chunk.tool_call.arguments,
                                tool_call_id
                            )
                        except Exception as e:
                            logger.debug(f"Failed to create tool call record during daily review: {e}")
                    try:
                        args = json.loads(chunk.tool_call.arguments)
                        if tool_name == 'archival_memory_search':
                            query = args.get('query', 'unknown')
                            log_with_panel(f"query: \"{query}\"", f"Tool call: {tool_name}", "blue")
                        elif tool_name == 'archival_memory_insert':
                            content = args.get('content', '')
                            log_with_panel(content[:200] + "..." if len(content) > 200 else content, f"Tool call: {tool_name}", "blue")
                        elif tool_name == 'update_block':
                            label = args.get('label', 'unknown')
                            value_preview = str(args.get('value', ''))[:100] + "..." if len(str(args.get('value', ''))) > 100 else str(args.get('value', ''))
                            log_with_panel(f"{label}: \"{value_preview}\"", f"Tool call: {tool_name}", "blue")
                        elif tool_name == 'reply_to_bluesky_post':
                            text = args.get('text', '')
                            uri = args.get('uri', '')[:50]
                            log_with_panel(f"reply to {uri}...: \"{text[:100]}...\"" if len(text) > 100 else f"reply to {uri}...: \"{text}\"", f"Tool call: {tool_name}", "blue")
                        else:
                            args_str = ', '.join(f"{k}={v}" for k, v in args.items() if k != 'request_heartbeat')
                            if len(args_str) > 150:
                                args_str = args_str[:150] + "..."
                            log_with_panel(args_str, f"Tool call: {tool_name}", "blue")
                    except:
                        log_with_panel(chunk.tool_call.arguments[:150] + "...", f"Tool call: {tool_name}", "blue")
                elif chunk.message_type == 'tool_return_message':
                    if chunk.status == 'success':
                        log_with_panel("Success", f"Tool result: {chunk.name} \u2713", "green")
                    else:
                        log_with_panel("Error", f"Tool result: {chunk.name} \u2717", "red")
                elif chunk.message_type == 'assistant_message':
                    print("\n\u25b6 Daily Review Response")
                    print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                    for line in chunk.content.split('\n'):
                        print(f"  {line}")

            if str(chunk) == 'done':
                break

        logger.info("Daily review message processed successfully")

    except Exception as e:
        logger.error(f"Error sending daily review message: {e}")
    finally:
        # Always detach temporal blocks after review
        if attached_temporal_labels:
            logger.info("Detaching temporal journal blocks after daily review")
            detach_success = detach_temporal_blocks(client, agent_id, attached_temporal_labels)
            if not detach_success:
                logger.warning("Some temporal blocks may not have been detached properly")
