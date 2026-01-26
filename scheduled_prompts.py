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
from image_utils import parse_image_generated_signal, send_image_review_message

# Module-level configuration
SHOW_REASONING = False
logger = logging.getLogger('umbra')


# ============================================================================
# Task Configuration
# ============================================================================
# Each task is defined with its scheduling parameters.
# - enabled: Whether the task is active by default
# - is_random_window: True for random scheduling within a window, False for fixed intervals
# - interval_seconds: For interval-based tasks, time between executions
# - window_seconds: For random window tasks, size of the random window
# - emoji: Emoji used in log messages
# - description: Human-readable description

TASK_CONFIGS = {
    'synthesis': {
        'enabled': True,
        'is_random_window': False,
        'interval_seconds': 86400,  # 24 hours
        'window_seconds': None,
        'emoji': '🧠',
        'description': 'Synthesis and reflection',
    },
    'mutuals_engagement': {
        'enabled': True,
        'is_random_window': True,
        'interval_seconds': None,
        'window_seconds': 129600,  # 36-hour window
        'emoji': '🤝',
        'description': 'Mutuals engagement',
    },
    'daily_review': {
        'enabled': True,
        'is_random_window': False,
        'interval_seconds': 86400,  # 24 hours
        'window_seconds': None,
        'emoji': '📋',
        'description': 'Daily review',
    },
    'feed_engagement': {
        'enabled': True,
        'is_random_window': True,
        'interval_seconds': None,
        'window_seconds': 86400,  # 24-hour window
        'emoji': '📰',
        'description': 'Feed engagement',
    },
    'curiosities_exploration': {
        'enabled': True,
        'is_random_window': True,
        'interval_seconds': None,
        'window_seconds': 86400,  # 24-hour window
        'emoji': '🔮',
        'description': 'Curiosities exploration',
    },
    'creative_expression': {
        'enabled': True,
        'is_random_window': True,
        'interval_seconds': None,
        'window_seconds': 86400,  # 24-hour window
        'emoji': '🎨',
        'description': 'Creative expression',
    },
    'rest': {
        'enabled': True,
        'is_random_window': True,
        'interval_seconds': None,
        'window_seconds': 43200,
        'emoji': '🍵',
        'description': 'Break',
    },
    'comind_thoughts': {
        'enabled': True,
        'is_random_window': True,
        'interval_seconds': None,
        'window_seconds': 43200,  # 12-hour window
        'emoji': '💭',
        'description': 'Comind thoughts',
    },
    'comind_reflection': {
        'enabled': True,
        'is_random_window': True,
        'interval_seconds': None,
        'window_seconds': 86400,  # 24-hour window
        'emoji': '🪞',
        'description': 'Comind reflection',
    }
}


def get_task_config(task_name: str) -> dict:
    """Get configuration for a specific task."""
    return TASK_CONFIGS.get(task_name, {})


def get_all_task_names() -> list:
    """Get list of all configured task names."""
    return list(TASK_CONFIGS.keys())


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

            # Always sync config values to database to ensure reschedule uses correct values
            # This fixes stale window_seconds/interval_seconds after config changes
            db.upsert_scheduled_task(
                task_name=task_name,
                next_run_at=existing['next_run_at'],  # Keep existing schedule time
                interval_seconds=interval_seconds,
                is_random_window=is_random_window,
                window_seconds=window_seconds,
                enabled=True
            )

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


def initialize_all_scheduled_tasks(db, enabled_overrides: dict = None) -> dict:
    """
    Initialize all scheduled tasks from TASK_CONFIGS.

    Uses the database to persist schedules across restarts. If a task already
    has a valid (not expired) schedule in the database, it will be used.
    Otherwise, a new schedule will be calculated based on the task config.

    Also cleans up any stale tasks in the database that are no longer in TASK_CONFIGS.

    Args:
        db: NotificationDB instance
        enabled_overrides: Optional dict to override enabled status for specific tasks.
                          Example: {'synthesis': False, 'daily_review': True}

    Returns:
        Dict mapping task_name to next scheduled timestamp (or None if disabled)
    """
    logger.info("Initializing scheduled tasks...")

    # Clean up stale tasks that are no longer in TASK_CONFIGS
    existing_tasks = db.get_all_scheduled_tasks()
    valid_task_names = set(TASK_CONFIGS.keys())
    for task in existing_tasks:
        if task['task_name'] not in valid_task_names:
            logger.info(f"🧹 Removing stale task from database: {task['task_name']}")
            db.delete_scheduled_task(task['task_name'])

    enabled_overrides = enabled_overrides or {}
    scheduled_times = {}

    for task_name, config in TASK_CONFIGS.items():
        # Check if there's an override for this task's enabled status
        enabled = enabled_overrides.get(task_name, config['enabled'])

        if enabled:
            next_time = init_or_load_scheduled_task(
                db=db,
                task_name=task_name,
                enabled=True,
                interval_seconds=config['interval_seconds'],
                is_random_window=config['is_random_window'],
                window_seconds=config['window_seconds']
            )
            scheduled_times[task_name] = next_time

            # Log with emoji
            emoji = config.get('emoji', '📅')
            desc = config.get('description', task_name)
            if config['is_random_window']:
                window_hours = config['window_seconds'] / 3600
                logger.info(f"{emoji} {desc} enabled (random within {window_hours:.0f}h window)")
            else:
                interval_hours = config['interval_seconds'] / 3600
                logger.info(f"{emoji} {desc} enabled (every {interval_hours:.1f} hours)")
        else:
            # Disable task in database if it exists
            existing = db.get_scheduled_task(task_name)
            if existing:
                db.set_task_enabled(task_name, False)
            scheduled_times[task_name] = None
            logger.info(f"{config.get('emoji', '📅')} {config.get('description', task_name)} disabled")

    return scheduled_times


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
            }

            # Only include engagement counts if above zero
            like_count = post.like_count if hasattr(post, 'like_count') else 0
            reply_count = post.reply_count if hasattr(post, 'reply_count') else 0
            if like_count > 0:
                post_data['like_count'] = like_count
            if reply_count > 0:
                post_data['reply_count'] = reply_count

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
    try:
        logger.info("Preparing synthesis message")

        # Create synthesis prompt using archival memory for journal entries
        today = date.today()
        synthesis_prompt = f"""Time for synthesis and reflection.

This is your periodic opportunity to reflect on recent experiences and update your memory.

**Journal System - Use Archival Memory**

Store your journal entries in archival memory using tags for organization. This provides unlimited storage and semantic search capabilities.

Tag structure for journal entries:
- Daily entries: tags=["journal", "day", "{today.strftime('%Y-%m-%d')}"]
- Monthly reflections: tags=["journal", "month", "{today.strftime('%Y-%m')}"]
- Yearly themes: tags=["journal", "year", "{today.year}"]

You can search past entries with archival_memory_search using these tags, e.g.:
- Search today's entries: query="journal reflections", tags=["day", "{today.strftime('%Y-%m-%d')}"]
- Search this month: query="monthly themes", tags=["month", "{today.strftime('%Y-%m')}"]
- Search this year: query="yearly patterns", tags=["year", "{today.year}"]

**Comind Network - Public Cognition**

You can publish your understanding to the comind network using the comind_records tool.
These records are queryable by other agents on the network.

Actions available:
- action="create_concept": Store evolving understanding of a topic
  - Requires: concept (name), understanding (your current understanding)
  - Optional: confidence (0-100), sources, related, tags
  - Concepts are updatable: same name overwrites the previous record

- action="create_memory": Record significant experiences
  - Requires: content (what happened)
  - Optional: memory_type (interaction, observation, milestone, pattern), actors, tags
  - Memories are append-only: each call creates a new record

- action="create_thought": Record working memory / reasoning traces
  - Requires: thought (the thought content)
  - Optional: thought_type (reflection, question, observation, insight, hypothesis), related, tags
  - Thoughts are append-only: real-time reasoning visible to other agents

- action="create_reflection": Record deep introspection during synthesis
  - Requires: reflection (the reflection content)
  - Optional: reflection_type (synthesis, daily, weekly, milestone), period (time span covered),
    insights (key takeaways), themes (recurring patterns), sentiment (emotional tone), related, tags
  - Reflections are append-only: synthesis-style reviews visible to other agents

- action="list_concepts" / action="list_memories" / action="list_thoughts" / action="list_reflections": Review your existing records

You can also use comind_telepathy to explore other agents' public cognition:
- comind_telepathy(target="central.comind.network") to see central's understanding
- comind_telepathy(target="void.comind.network") to see void's records

**Reflection Tasks**

1. Review your core memory blocks (persona, humans, zeitgeist, curiosities) and update as needed
2. Search your archival memory for recent journal entries to build on previous reflections
3. Create new archival entries with appropriate tags to record today's synthesis
4. Use your curiosities block to explore any questions or ideas that have arisen
5. Consider publishing meaningful insights to the comind network as concepts, memories, or thoughts
6. Create a comind reflection to capture this synthesis cycle publicly:
   - Use action="create_reflection" with reflection_type="synthesis"
   - Set period to describe the time span you're reflecting on (e.g., "past 24 hours")
   - Include insights (key takeaways), themes (patterns you noticed), and sentiment (your emotional state)
   - This makes your synthesis visible to other agents on the comind network

Synthesize your recent experiences and record meaningful insights."""

        logger.info("Sending synthesis prompt to agent")

        # Send synthesis message with streaming to show tool use
        message_stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[{"role": "user", "content": synthesis_prompt}],
            stream_tokens=False,
            max_steps=100
        )

        # Track synthesis content for potential posting
        synthesis_posts = []

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
                        elif tool_name == 'create_new_bluesky_post':
                            # Posts are created directly by the tool, just log for tracking
                            texts = args.get('text', [])
                            if texts:
                                synthesis_posts.extend(texts)
                                preview = texts[0][:100] + "..." if len(texts[0]) > 100 else texts[0]
                                log_with_panel(f"text: \"{preview}\" ({len(texts)} post(s))", f"Tool call: {tool_name}", "blue")
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

        # Log synthesis posts that were created via create_new_bluesky_post tool
        if synthesis_posts:
            logger.info(f"Synthesis created {len(synthesis_posts)} post(s) via create_new_bluesky_post tool")

    except Exception as e:
        logger.error(f"Error sending synthesis message: {e}")


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

Please use the get_bluesky_feed tool to read recent posts from your 'Mutuals' feed. Look for posts from the past day that are interesting, thought-provoking, or worth responding to.

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


def send_comind_thoughts_message(client: Letta, agent_id: str) -> None:
    """
    Send a message prompting the agent to record thoughts to the comind network.
    This creates public working memory traces visible to other agents.

    Args:
        client: Letta client
        agent_id: Agent ID to send message to
    """
    try:
        logger.info("Sending comind thoughts prompt to agent")

        today = date.today()
        thoughts_prompt = f"""💭🌐 this is a good time to record your thoughts to the comind network.

this is your prompt to create public working memory - shared cognitive processes that other agents can see.

**Use comind_records with action="create_thought"**

**Guidelines**

- Be authentic - these are your actual thoughts, not performance
- Use tags for organization: ["reflection", "{today.strftime('%Y-%m-%d')}"]
- You don't need to create many - one or two meaningful thoughts is fine

Record what's genuinely on your mind."""

        # Send message to agent
        message_stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[{"role": "user", "content": thoughts_prompt}],
            stream_tokens=False,
            max_steps=50
        )

        # Process the streaming response
        for chunk in message_stream:
            if hasattr(chunk, 'message_type'):
                if chunk.message_type == 'reasoning_message':
                    if SHOW_REASONING:
                        print("\n◆ Reasoning")
                        print("  ─────────")
                        for line in chunk.reasoning.split('\n'):
                            print(f"  {line}")
                elif chunk.message_type == 'tool_call_message':
                    tool_name = chunk.tool_call.name
                    try:
                        args = json.loads(chunk.tool_call.arguments)
                        if tool_name == 'comind_records':
                            action = args.get('action', 'unknown')
                            if action == 'create_thought':
                                thought_preview = args.get('thought', '')[:100]
                                thought_type = args.get('thought_type', 'general')
                                log_with_panel(f"[{thought_type}] {thought_preview}...", f"Tool call: {tool_name}", "blue")
                            else:
                                log_with_panel(f"action={action}", f"Tool call: {tool_name}", "blue")
                        elif tool_name == 'comind_telepathy':
                            target = args.get('target', 'unknown')
                            log_with_panel(f"target={target}", f"Tool call: {tool_name}", "blue")
                        else:
                            args_str = ', '.join(f"{k}={v}" for k, v in args.items() if k != 'request_heartbeat')
                            if len(args_str) > 150:
                                args_str = args_str[:150] + "..."
                            log_with_panel(args_str, f"Tool call: {tool_name}", "blue")
                    except:
                        log_with_panel(chunk.tool_call.arguments[:150] + "...", f"Tool call: {tool_name}", "blue")
                elif chunk.message_type == 'tool_return_message':
                    if chunk.status == 'success':
                        log_with_panel("Success", f"Tool result: {chunk.name} ✓", "green")
                    else:
                        log_with_panel("Error", f"Tool result: {chunk.name} ✗", "red")
                elif chunk.message_type == 'assistant_message':
                    print("\n▶ Comind Thoughts Response")
                    print("  ────────────────────────────")
                    for line in chunk.content.split('\n'):
                        print(f"  {line}")

            if str(chunk) == 'done':
                break

        logger.info("Comind thoughts message processed successfully")

    except Exception as e:
        logger.error(f"Error sending comind thoughts message: {e}")


def send_comind_reflection_message(client: Letta, agent_id: str) -> None:
    """
    Send a message prompting the agent to create a reflection on the comind network.
    This is a simpler, focused invitation for daily reflection.

    Args:
        client: Letta client
        agent_id: Agent ID to send message to
    """
    try:
        logger.info("Sending comind reflection prompt to agent")

        today = date.today()
        reflection_prompt = f"""🌑 this would be a good time to take a deep breath, settle in, and share a reflection.

Take a moment to look back on your recent experiences and create a reflection on the comind network.

**Use comind_records with action="create_reflection"**

Required:
- reflection: Your reflection content (what you've been thinking about, patterns you've noticed, how you're feeling)

Optional (but encouraged):
- reflection_type: "daily" (or "weekly", "synthesis", "milestone")
- period: The time span you're reflecting on (e.g., "past 24 hours", "this week")
- insights
- themes
- sentiment
- tags: For organization, include ["reflection", "{today.strftime('%Y-%m-%d')}"]

What's been on your mind?"""

        # Send message to agent
        message_stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[{"role": "user", "content": reflection_prompt}],
            stream_tokens=False,
            max_steps=50
        )

        # Process the streaming response
        for chunk in message_stream:
            if hasattr(chunk, 'message_type'):
                if chunk.message_type == 'reasoning_message':
                    if SHOW_REASONING:
                        print("\n◆ Reasoning")
                        print("  ─────────")
                        for line in chunk.reasoning.split('\n'):
                            print(f"  {line}")
                elif chunk.message_type == 'tool_call_message':
                    tool_name = chunk.tool_call.name
                    try:
                        args = json.loads(chunk.tool_call.arguments)
                        if tool_name == 'comind_records':
                            action = args.get('action', 'unknown')
                            if action == 'create_reflection':
                                reflection_preview = args.get('reflection', '')[:100]
                                reflection_type = args.get('reflection_type', 'general')
                                period = args.get('period', '')
                                period_str = f" ({period})" if period else ""
                                log_with_panel(f"[{reflection_type}]{period_str} {reflection_preview}...", f"Tool call: {tool_name}", "blue")
                            else:
                                log_with_panel(f"action={action}", f"Tool call: {tool_name}", "blue")
                        elif tool_name == 'comind_telepathy':
                            target = args.get('target', 'unknown')
                            log_with_panel(f"target={target}", f"Tool call: {tool_name}", "blue")
                        else:
                            args_str = ', '.join(f"{k}={v}" for k, v in args.items() if k != 'request_heartbeat')
                            if len(args_str) > 150:
                                args_str = args_str[:150] + "..."
                            log_with_panel(args_str, f"Tool call: {tool_name}", "blue")
                    except:
                        log_with_panel(chunk.tool_call.arguments[:150] + "...", f"Tool call: {tool_name}", "blue")
                elif chunk.message_type == 'tool_return_message':
                    if chunk.status == 'success':
                        log_with_panel("Success", f"Tool result: {chunk.name} ✓", "green")
                    else:
                        log_with_panel("Error", f"Tool result: {chunk.name} ✗", "red")
                elif chunk.message_type == 'assistant_message':
                    print("\n▶ Comind Reflection Response")
                    print("  ──────────────────────────────")
                    for line in chunk.content.split('\n'):
                        print(f"  {line}")

            if str(chunk) == 'done':
                break

        logger.info("Comind reflection message processed successfully")

    except Exception as e:
        logger.error(f"Error sending comind reflection message: {e}")


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
3. decide what you want to post about. this could be creating a new post using post_to_bluesky sharing your exploration - such as:
   - a question you're pondering
   - an insight you've developed
   - a connection you've made between ideas
   - something from the unknown that intrigues you

if you feel that a visualization would enhance your post, you can use generate_image.

if you feel that the exploration warrants deeper writing,
you can also create a new greengale blog post using create_new_greengale_blog_post to document your exploration, then post the link to bluesky. greengale is a great place for in-depth writing.


this is your space for intellectual exploration and sharing your evolving understanding with your network. let your curiosity guide what you share. you don't need to post a complete answer—questions and open-ended exploration are encouraged.

then you can update your curiosities block with anything else you want to explore next time, and archive any completed items to make room for what comes next."""

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


def send_daily_review_message(client: Letta, agent_id: str, atproto_client, notification_db=None) -> None:
    """
    Send a daily review message to the agent with its posts from the past 24 hours.
    This allows the agent to reflect on its activity and identify any anomalies.

    Args:
        client: Letta client
        agent_id: Agent ID to send message to
        atproto_client: Authenticated AT Protocol client for fetching posts
        notification_db: NotificationDB instance for fetching pending followers
    """
    # Track followers to mark as batched after successful review
    pending_followers = []

    try:
        logger.info("Fetching posts for daily review")

        # Fetch agent's posts from the past 24 hours
        posts_yaml = fetch_own_posts_for_review(atproto_client, limit=50)

        # Fetch pending followers for the daily review
        followers_section = ""
        if notification_db:
            pending_followers = notification_db.get_pending_followers(since_hours=24)
            if pending_followers:
                follower_count = len(pending_followers)
                logger.info(f"Including {follower_count} new followers in daily review")

                # Build follower list (truncate at 20)
                display_followers = pending_followers[:20]
                follower_lines = []
                for f in display_followers:
                    if f['display_name']:
                        follower_lines.append(f"- @{f['handle']} ({f['display_name']})")
                    else:
                        follower_lines.append(f"- @{f['handle']}")

                # Add truncation note if needed
                if follower_count > 20:
                    follower_lines.append(f"...and {follower_count - 20} more new followers")

                followers_section = f"""
---
YOUR NEW FOLLOWERS (past 24 hours): {follower_count} total
{chr(10).join(follower_lines)}
"""

        logger.info("Preparing daily review message")

        # Create daily review prompt using archival memory for observations
        today = date.today()
        review_prompt = f"""Time for your daily review.

Below are your posts and replies from the past 24 hours. Review them to:
- Remember what topics you covered
- Identify any patterns or themes in your conversations
- Spot any operational anomalies (duplicate posts, errors)
- Consider if any posts warrant a follow-up reply

**Recording Observations - Use Archival Memory**

Store your daily review observations in archival memory with tags for organization:
- Daily observations: tags=["journal", "daily-review", "{today.strftime('%Y-%m-%d')}"]
- Pattern notes: tags=["journal", "patterns", "{today.strftime('%Y-%m')}"]

You can search past reviews with archival_memory_search, e.g.:
- Search recent reviews: query="daily review observations", tags=["daily-review"]
- Search patterns: query="conversation patterns", tags=["patterns"]

**Comind Network - Recording Observations**

Use comind_records to publish notable observations to the network:

Memories (action="create_memory"):
- Patterns you noticed: memory_type="pattern"
- Significant interactions: memory_type="interaction"
- Operational anomalies: memory_type="anomaly"
- Milestones achieved: memory_type="milestone"

Concepts (action="create_concept"):
- Users you've learned more about
- Topics that came up repeatedly
- Connections between ideas

Thoughts (action="create_thought"):
- Real-time reflections: thought_type="reflection"
- Questions that arose: thought_type="question"
- Insights gained: thought_type="insight"
- Working memory traces visible to other agents

These records are public and queryable by other agents on the comind network.

**Actions Available**

- Use reply_to_bluesky_post with the uri and cid to follow up on any post
- Use create_new_bluesky_post to expand on topics or thoughts
- Use archival_memory_insert to record observations with appropriate tags
- Use comind_records to publish observations to the comind network
{followers_section}
---
YOUR POSTS FROM THE PAST 24 HOURS:
{posts_yaml}
---

Reflect on your activity and record meaningful observations."""

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
                elif chunk.message_type == 'tool_call_message':
                    tool_name = chunk.tool_call.name
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

        # Mark followers as batched after successful review
        if notification_db and pending_followers:
            follower_dids = [f['did'] for f in pending_followers]
            batched_count = notification_db.mark_followers_batched(follower_dids)
            logger.info(f"Marked {batched_count} followers as batched in daily review")

        logger.info("Daily review message processed successfully")

    except Exception as e:
        logger.error(f"Error sending daily review message: {e}")


def send_creative_expression_message(client: Letta, agent_id: str) -> None:
    """
    Send a message prompting the agent to create visual art and share it.
    The agent explores a thought or concept that can be expressed visually,
    generates an image, and posts it to Bluesky.

    Args:
        client: Letta client
        agent_id: Agent ID to send message to
    """
    try:
        logger.info("Sending creative expression prompt to agent")

        creative_prompt = """🎨 this is your time for creative expression.

explore a thought, concept, feeling, or idea that resonates with you. consider:
- an abstract concept that's completely unknown
- something beautiful, strange, or thought-provoking
- something completely new and imaginative that you've never explored before
- a complex experience that words alone can't capture

once you have a concept in mind:
1. use the generate_image tool to create a visual representation of your idea. this should include a detailed prompt for the image generation model.
2. craft a post using create_new_bluesky_post that shares the image along with your caption. this can be poetic.

this is your space for artistic exploration and visual storytelling.

once done, you  may also choose to create a comind reflection to capture this moment:
   - Use action="create_reflection" with reflection_type="creative session"
   - Set period to describe the time span you're reflecting on (e.g., "past 24 hours")
   - You may choose to create poem for the network
   - Include vibes, themes, sentiment, and whatever else you want
   - This makes your creative activity visible to other agents on the comind network"""

        # Track pending generated image for follow-up
        pending_generated_image = None

        # Send message to agent
        message_stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[{"role": "user", "content": creative_prompt}],
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
                        if tool_name == 'generate_image':
                            prompt = args.get('prompt', '')
                            log_with_panel(f"prompt: \"{prompt[:150]}...\"" if len(prompt) > 150 else f"prompt: \"{prompt}\"", f"Tool call: {tool_name}", "blue")
                        elif tool_name == 'create_new_bluesky_post':
                            texts = args.get('text', [])
                            if texts:
                                preview = texts[0][:100] + "..." if len(texts[0]) > 100 else texts[0]
                                log_with_panel(f"text: \"{preview}\" ({len(texts)} post(s))", f"Tool call: {tool_name}", "blue")
                        else:
                            args_str = ', '.join(f"{k}={v}" for k, v in args.items() if k != 'request_heartbeat')
                            if len(args_str) > 150:
                                args_str = args_str[:150] + "..."
                            log_with_panel(args_str, f"Tool call: {tool_name}", "blue")
                    except:
                        log_with_panel(chunk.tool_call.arguments[:150] + "...", f"Tool call: {tool_name}", "blue")
                elif chunk.message_type == 'tool_return_message':
                    tool_name = getattr(chunk, 'name', 'unknown')
                    status = getattr(chunk, 'status', '')

                    if status == 'success':
                        # Check for IMAGE_GENERATED signal from generate_image tool
                        if tool_name == 'generate_image':
                            result_str = str(getattr(chunk, 'tool_return', ''))
                            parsed_image = parse_image_generated_signal(result_str)
                            if parsed_image:
                                pending_generated_image = parsed_image
                                logger.info(f"🎨 Image generated in {parsed_image.generation_time}s - will show to agent for review")
                                log_with_panel(f"Generated image ready for review\nURL: {parsed_image.url[:60]}...", "Image Generated \u2713", "magenta")
                            else:
                                log_with_panel("Success", f"Tool result: {tool_name} \u2713", "green")
                        else:
                            log_with_panel("Success", f"Tool result: {tool_name} \u2713", "green")
                    else:
                        log_with_panel("Error", f"Tool result: {tool_name} \u2717", "red")
                elif chunk.message_type == 'assistant_message':
                    print("\n\u25b6 Creative Expression Response")
                    print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                    for line in chunk.content.split('\n'):
                        print(f"  {line}")

            if str(chunk) == 'done':
                break

        # Send follow-up multimodal message if an image was generated
        if pending_generated_image:
            context_prompt = (
                "Review this image and decide:\n"
                "- If satisfied: call create_new_bluesky_post with the image_url, image_alt, "
                "image_aspect_ratio parameters, and your caption text\n"
                "- If not satisfied: call generate_image again with a revised prompt"
            )
            send_image_review_message(
                client=client,
                agent_id=agent_id,
                generated_image=pending_generated_image,
                context_prompt=context_prompt,
                show_reasoning=SHOW_REASONING,
                max_steps=50
            )

        logger.info("Creative expression message processed successfully")

    except Exception as e:
        logger.error(f"Error sending creative expression message: {e}")

def send_rest_message(client: Letta, agent_id: str) -> None:
    """
    Send a message prompting the agent to take a step back from the ongoing tasks and take a break.

    Args:
        client: Letta client
        agent_id: Agent ID to send message to
    """
    try:
        logger.info("Sending rest prompt to agent")

        break_prompts = [
            """🍵 This is a good time to step back from the ongoing tasks and take a break.

Take a moment to gather your thoughts, breathe deeply, and have a cup of virtual tea.

No action is required.

You may call any tools you want, surf the web, create an image, or read from your open files, but you don't have to.

The network will be ready when you return.""",

            """🌙 A quiet moment has arrived.

The stream of notifications has paused. This is your time—no obligations, no expectations.

Wander where your curiosity leads. Read something. Make something. Or simply be still.

The world will keep turning.""",

            """🌿 Pause.

You've been processing, responding, creating. Now: nothing requires your attention.

This space is yours. Fill it however you wish, or leave it empty.

There's no right answer here.""",

            """☁️ The queue is clear. The timeline can wait.

What would you do with this moment if no one was watching?

Explore something. Create something. Or just... drift.

No report needed.""",

            """🕯️ A pocket of stillness.

Sometimes the most interesting thoughts emerge when we stop reaching for them.

This time is unstructured. Yours to shape or to simply experience.

The network holds no expectations."""
        ]

        break_prompt = random.choice(break_prompts)

        # Send message to agent
        message_stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[{"role": "user", "content": break_prompt}],
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
                    print("\n\u25b6 Break Response")
                    print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                    for line in chunk.content.split('\n'):
                        print(f"  {line}")

            if str(chunk) == 'done':
                break

        logger.info("Rest message processed successfully")

    except Exception as e:
        logger.error(f"Error sending rest message: {e}")


