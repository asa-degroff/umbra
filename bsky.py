from rich import print # pretty printing tools
from time import sleep
from letta_client import Letta
from bsky_utils import thread_to_yaml_string
import os
import logging
import json
import hashlib
from pathlib import Path
from datetime import datetime

from utils import (
    upsert_block,
    upsert_agent
)

import bsky_utils

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("void_bot")
logger.setLevel(logging.INFO)


# Create a client with extended timeout for LLM operations
CLIENT= Letta(
    token=os.environ["LETTA_API_KEY"],
    timeout=300  # 5 minutes timeout for API calls
)

# Use the "Bluesky" project
PROJECT_ID = "5ec33d52-ab14-4fd6-91b5-9dbc43e888a8"

# Notification check delay
FETCH_NOTIFICATIONS_DELAY_SEC = 30

# Queue directory
QUEUE_DIR = Path("queue")
QUEUE_DIR.mkdir(exist_ok=True)
QUEUE_ERROR_DIR = Path("queue/errors")
QUEUE_ERROR_DIR.mkdir(exist_ok=True, parents=True)
PROCESSED_NOTIFICATIONS_FILE = Path("queue/processed_notifications.json")

# Maximum number of processed notifications to track
MAX_PROCESSED_NOTIFICATIONS = 10000

def export_agent_state(client, agent):
    """Export agent state to a timestamped .af file in the agents directory."""
    try:
        # Create agents directory if it doesn't exist
        agent_dir = "agents"
        os.makedirs(agent_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        agent_file = os.path.join(agent_dir, f"void_{timestamp}.af")
        
        # Export agent
        logger.info(f"Exporting agent {agent.id} to {agent_file}...")
        agent_data = client.agents.export_file(agent_id=agent.id)
        
        # Write to file
        with open(agent_file, 'wb') as f:
            f.write(agent_data)
        
        # Create/update symlink to latest export
        latest_link = os.path.join(agent_dir, "void_latest.af")
        if os.path.islink(latest_link):
            os.unlink(latest_link)
        os.symlink(os.path.basename(agent_file), latest_link)
        
        logger.info(f"✅ Agent exported successfully to {agent_file}")
        
        # Git add the files
        try:
            subprocess.run(["git", "add", agent_file, latest_link], check=True, capture_output=True)
            logger.info("Added export files to git staging")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to git add export files: {e}")
        
    except Exception as e:
        logger.error(f"Failed to export agent: {e}")

def initialize_void():

    # Ensure that a shared zeitgeist block exists
    zeigeist_block = upsert_block(
        CLIENT,
        label = "zeitgeist",
        value = "I don't currently know anything about what is happening right now.",
        description = "A block to store your understanding of the current social environment."
    )

    # Ensure that a shared void personality block exists
    persona_block = upsert_block(
        CLIENT,
        label = "void-persona",
        value = "My name is Void. I live in the void. I must develop my personality.",
        description = "The personality of Void."
    )

    # Ensure that a shared void human block exists
    human_block = upsert_block(
        CLIENT,
        label = "void-humans",
        value = "I haven't seen any bluesky users yet. I will update this block when I learn things about users, identified by their handles such as @cameron.pfiffer.org.",
        description = "A block to store your understanding of users you talk to or observe on the bluesky social network."
    )

    # Create the agent if it doesn't exist
    void_agent = upsert_agent(
        CLIENT,
        name = "void",
        block_ids = [
            persona_block.id,
            human_block.id,
            zeigeist_block.id,
        ],
        tags = ["social agent", "bluesky"],
        model="openai/gpt-4o-mini",
        embedding="openai/text-embedding-3-small",
        description = "A social media agent trapped in the void.",
        project_id = PROJECT_ID
    )
    
    # Export agent state
    export_agent_state(CLIENT, void_agent)
    
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


def process_mention(void_agent, atproto_client, notification_data):
    """Process a mention and generate a reply using the Letta agent.
    
    Returns:
        True: Successfully processed, remove from queue
        False: Failed but retryable, keep in queue
        None: Failed with non-retryable error, move to errors directory
    """
    try:
        logger.info(f"Starting process_mention with notification_data type: {type(notification_data)}")
        
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
        
        logger.info(f"Extracted data - URI: {uri}, Author: @{author_handle}, Text: {mention_text[:50]}...")

        # Retrieve the entire thread associated with the mention
        try:
            thread = atproto_client.app.bsky.feed.get_post_thread({
                'uri': uri,
                'parent_height': 80,
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

        # Get thread context as YAML string
        logger.info("Converting thread to YAML string")
        try:
            thread_context = thread_to_yaml_string(thread)
            logger.info(f"Thread context generated, length: {len(thread_context)} characters")
            logger.debug(f"Thread context preview: {thread_context[:500]}...")
        except Exception as yaml_error:
            import traceback
            logger.error(f"Error converting thread to YAML: {yaml_error}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            logger.error(f"Thread type: {type(thread)}")
            if hasattr(thread, '__dict__'):
                logger.error(f"Thread attributes: {thread.__dict__}")
            # Try to continue with a simple context
            thread_context = f"Error processing thread context: {str(yaml_error)}"

        # print(thread_context)

        # Create a prompt for the Letta agent with thread context
        prompt = f"""You received a mention on Bluesky from @{author_handle} ({author_name or author_handle}).

MOST RECENT POST (the mention you're responding to):
"{mention_text}"

FULL THREAD CONTEXT:
```yaml
{thread_context}
```

The YAML above shows the complete conversation thread. The most recent post is the one mentioned above that you should respond to, but use the full thread context to understand the conversation flow.

Use the bluesky_reply tool to send a response less than 300 characters."""

        # Get response from Letta agent
        logger.info(f"Mention from @{author_handle}: {mention_text}")
        logger.debug(f"Prompt being sent: {prompt}")
        
        # Log the exact parameters being sent to Letta
        logger.debug(f"Calling Letta API with agent_id: {void_agent.id}")
        logger.debug(f"Message content length: {len(prompt)} characters")

        try:
            message_response = CLIENT.agents.messages.create(
                agent_id = void_agent.id,
                messages = [{"role":"user", "content": prompt}]
            )
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
            
            raise

        # Log successful response
        logger.debug("Successfully received response from Letta API")
        logger.debug(f"Number of messages in response: {len(message_response.messages) if hasattr(message_response, 'messages') else 'N/A'}")

        # Extract the reply text from the agent's response
        reply_text = ""
        for message in message_response.messages:
            print(message)

            # Check if this is a ToolCallMessage with bluesky_reply tool
            if hasattr(message, 'tool_call') and message.tool_call:
                if message.tool_call.name == 'bluesky_reply':
                    # Parse the JSON arguments to get the message
                    try:
                        args = json.loads(message.tool_call.arguments)
                        reply_text = args.get('message', '')
                        logger.info(f"Extracted reply from tool call: {reply_text[:50]}...")
                        break
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse tool call arguments: {e}")

            # Fallback to text message if available
            elif hasattr(message, 'text') and message.text:
                reply_text = message.text
                break

        if reply_text:
            # Print the generated reply for testing
            print(f"\n=== GENERATED REPLY ===")
            print(f"To: @{author_handle}")
            print(f"Reply: {reply_text}")
            print(f"======================\n")

            # Send the reply
            logger.info(f"Sending reply: {reply_text[:50]}...")
            response = bsky_utils.reply_to_notification(
                client=atproto_client,
                notification=notification_data,
                reply_text=reply_text
            )

            if response:
                logger.info(f"Successfully replied to @{author_handle}")
                return True
            else:
                logger.error(f"Failed to send reply to @{author_handle}")
                return False
        else:
            logger.warning(f"No reply generated for mention from @{author_handle}, removing notification from queue")
            return True

    except Exception as e:
        logger.error(f"Error processing mention: {e}")
        return False


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
    """Save a notification to the queue directory with hash-based filename."""
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

        # Create filename with timestamp and hash
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{notification.reason}_{notif_hash}.json"
        filepath = QUEUE_DIR / filename

        # Skip if already exists (duplicate)
        if filepath.exists():
            logger.debug(f"Notification already queued: {filename}")
            return False

        # Write to file
        with open(filepath, 'w') as f:
            json.dump(notif_dict, f, indent=2)

        logger.info(f"Queued notification: {filename}")
        return True

    except Exception as e:
        logger.error(f"Error saving notification to queue: {e}")
        return False


def load_and_process_queued_notifications(void_agent, atproto_client):
    """Load and process all notifications from the queue."""
    try:
        # Get all JSON files in queue directory (excluding processed_notifications.json)
        queue_files = sorted([f for f in QUEUE_DIR.glob("*.json") if f.name != "processed_notifications.json"])

        if not queue_files:
            logger.debug("No queued notifications to process")
            return

        logger.info(f"Processing {len(queue_files)} queued notifications")

        for filepath in queue_files:
            try:
                # Load notification data
                with open(filepath, 'r') as f:
                    notif_data = json.load(f)

                # Process based on type using dict data directly
                success = False
                if notif_data['reason'] == "mention":
                    success = process_mention(void_agent, atproto_client, notif_data)
                elif notif_data['reason'] == "reply":
                    success = process_mention(void_agent, atproto_client, notif_data)
                elif notif_data['reason'] == "follow":
                    author_handle = notif_data['author']['handle']
                    author_display_name = notif_data['author'].get('display_name', 'no display name')
                    follow_update = f"@{author_handle} ({author_display_name}) started following you."
                    CLIENT.agents.messages.create(
                        agent_id = void_agent.id,
                        messages = [{"role":"user", "content": f"Update: {follow_update}"}]
                    )
                    success = True  # Follow updates are always successful
                elif notif_data['reason'] == "repost":
                    logger.info(f"Skipping repost notification from @{notif_data['author']['handle']}")
                    success = True  # Skip reposts but mark as successful to remove from queue
                else:
                    logger.warning(f"Unknown notification type: {notif_data['reason']}")
                    success = True  # Remove unknown types from queue

                # Handle file based on processing result
                if success:
                    filepath.unlink()
                    logger.info(f"Processed and removed: {filepath.name}")
                    
                    # Mark as processed to avoid reprocessing
                    processed_uris = load_processed_notifications()
                    processed_uris.add(notif_data['uri'])
                    save_processed_notifications(processed_uris)
                    
                elif success is None:  # Special case for moving to error directory
                    error_path = QUEUE_ERROR_DIR / filepath.name
                    filepath.rename(error_path)
                    logger.warning(f"Moved {filepath.name} to errors directory")
                    
                    # Also mark as processed to avoid retrying
                    processed_uris = load_processed_notifications()
                    processed_uris.add(notif_data['uri'])
                    save_processed_notifications(processed_uris)
                    
                else:
                    logger.warning(f"Failed to process {filepath.name}, keeping in queue for retry")

            except Exception as e:
                logger.error(f"Error processing queued notification {filepath.name}: {e}")
                # Keep the file for retry later

    except Exception as e:
        logger.error(f"Error loading queued notifications: {e}")


def process_notifications(void_agent, atproto_client):
    """Fetch new notifications, queue them, and process the queue."""
    try:
        # First, process any existing queued notifications
        load_and_process_queued_notifications(void_agent, atproto_client)

        # Get current time for marking notifications as seen
        last_seen_at = atproto_client.get_current_time_iso()

        # Fetch ALL notifications using pagination
        all_notifications = []
        cursor = None
        page_count = 0
        max_pages = 20  # Safety limit to prevent infinite loops
        
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
                unread_count = sum(1 for n in page_notifications if not n.is_read and n.reason != "like")
                logger.debug(f"Page {page_count}: {len(page_notifications)} notifications, {unread_count} unread (non-like)")
                
                # Add all notifications to our list
                all_notifications.extend(page_notifications)
                
                # Check if we have more pages
                if hasattr(notifications_response, 'cursor') and notifications_response.cursor:
                    cursor = notifications_response.cursor
                    # If this page had no unread notifications, we can stop
                    if unread_count == 0:
                        logger.info(f"No more unread notifications found after {page_count} pages")
                        break
                else:
                    # No more pages
                    logger.info(f"Fetched all notifications across {page_count} pages")
                    break
                    
            except Exception as e:
                error_str = str(e)
                logger.error(f"Error fetching notifications page {page_count}: {e}")
                
                # Handle specific API errors
                if 'rate limit' in error_str.lower():
                    logger.warning("Rate limit hit while fetching notifications, will retry next cycle")
                    break
                elif '401' in error_str or 'unauthorized' in error_str.lower():
                    logger.error("Authentication error, re-raising exception")
                    raise
                else:
                    # For other errors, try to continue with what we have
                    logger.warning("Continuing with notifications fetched so far")
                    break

        # Queue all unread notifications (except likes)
        new_count = 0
        for notification in all_notifications:
            if not notification.is_read and notification.reason != "like":
                if save_notification_to_queue(notification):
                    new_count += 1

        # Mark all notifications as seen immediately after queuing
        if new_count > 0:
            atproto_client.app.bsky.notification.update_seen({'seen_at': last_seen_at})
            logger.info(f"Queued {new_count} new notifications and marked as seen")
        else:
            logger.debug("No new notifications to queue")

        # Process the queue (including any newly added notifications)
        load_and_process_queued_notifications(void_agent, atproto_client)

    except Exception as e:
        logger.error(f"Error processing notifications: {e}")


def main():
    """Main bot loop that continuously monitors for notifications."""
    logger.info("Initializing Void bot...")

    # Initialize the Letta agent
    void_agent = initialize_void()
    logger.info(f"Void agent initialized: {void_agent.id}")
    
    # Check if agent has required tools
    if hasattr(void_agent, 'tools') and void_agent.tools:
        tool_names = [tool.name for tool in void_agent.tools]
        logger.info(f"Agent has tools: {tool_names}")
        
        # Check for bluesky-related tools
        bluesky_tools = [name for name in tool_names if 'bluesky' in name.lower() or 'reply' in name.lower()]
        if bluesky_tools:
            logger.info(f"Found Bluesky-related tools: {bluesky_tools}")
        else:
            logger.warning("No Bluesky-related tools found! Agent may not be able to reply.")
    else:
        logger.warning("Agent has no tools registered!")

    # Initialize Bluesky client
    atproto_client = bsky_utils.default_login()
    logger.info("Connected to Bluesky")

    # Main loop
    logger.info(f"Starting notification monitoring, checking every {FETCH_NOTIFICATIONS_DELAY_SEC} seconds")

    while True:
        try:
            process_notifications(void_agent, atproto_client)
            logger.debug("Sleeping, no notifications were detected")
            sleep(FETCH_NOTIFICATIONS_DELAY_SEC)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            # Wait a bit longer on errors
            sleep(FETCH_NOTIFICATIONS_DELAY_SEC * 2)


if __name__ == "__main__":
    main()
