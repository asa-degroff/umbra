import os
import logging
from typing import Optional, Dict, Any, List
from atproto_client import Client, Session, SessionEvent, models

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("bluesky_session_handler")

# Load the environment variables
import dotenv
dotenv.load_dotenv(override=True)

import yaml
import json

# Strip fields. A list of fields to remove from a JSON object
STRIP_FIELDS = [
    "cid",
    "rev",
    "did",
    "uri",
    "langs",
    "threadgate",
    "py_type",
    "labels",
    "facets",
    "avatar",
    "viewer",
    "indexed_at",
    "tags",
    "associated",
    "thread_context",
    "aspect_ratio",
    "thumb",
    "fullsize",
    "root",
    "created_at",
    "verification",
    "like_count",
    "quote_count",
    "reply_count",
    "repost_count",
    "embedding_disabled",
    "thread_muted",
    "reply_disabled",
    "pinned",
    "like",
    "repost",
    "blocked_by",
    "blocking",
    "blocking_by_list",
    "followed_by",
    "following",
    "known_followers",
    "muted",
    "muted_by_list",
    "root_author_like",
    "entities",
    "ref",
    "mime_type",
    "size",
]
def convert_to_basic_types(obj):
    """Convert complex Python objects to basic types for JSON/YAML serialization."""
    if hasattr(obj, '__dict__'):
        # Convert objects with __dict__ to their dictionary representation
        return convert_to_basic_types(obj.__dict__)
    elif isinstance(obj, dict):
        return {key: convert_to_basic_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_basic_types(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    else:
        # For other types, try to convert to string
        return str(obj)


def strip_fields(obj, strip_field_list):
    """Recursively strip fields from a JSON object."""
    if isinstance(obj, dict):
        keys_flagged_for_removal = []

        # Remove fields from strip list and pydantic metadata
        for field in list(obj.keys()):
            if field in strip_field_list or field.startswith("__"):
                keys_flagged_for_removal.append(field)

        # Remove flagged keys
        for key in keys_flagged_for_removal:
            obj.pop(key, None)

        # Recursively process remaining values
        for key, value in list(obj.items()):
            obj[key] = strip_fields(value, strip_field_list)
            # Remove empty/null values after processing
            if (
                obj[key] is None
                or (isinstance(obj[key], dict) and len(obj[key]) == 0)
                or (isinstance(obj[key], list) and len(obj[key]) == 0)
                or (isinstance(obj[key], str) and obj[key].strip() == "")
            ):
                obj.pop(key, None)

    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            obj[i] = strip_fields(value, strip_field_list)
        # Remove None values from list
        obj[:] = [item for item in obj if item is not None]

    return obj


def flatten_thread_structure(thread_data):
    """
    Flatten a nested thread structure into a list while preserving all data.
    
    Args:
        thread_data: The thread data from get_post_thread
        
    Returns:
        Dict with 'posts' key containing a list of posts in chronological order
    """
    posts = []
    
    def traverse_thread(node):
        """Recursively traverse the thread structure to collect posts."""
        if not node:
            return
            
        # If this node has a parent, traverse it first (to maintain chronological order)
        if hasattr(node, 'parent') and node.parent:
            traverse_thread(node.parent)
        
        # Then add this node's post
        if hasattr(node, 'post') and node.post:
            # Convert to dict if needed to ensure we can process it
            if hasattr(node.post, '__dict__'):
                post_dict = node.post.__dict__.copy()
            elif isinstance(node.post, dict):
                post_dict = node.post.copy()
            else:
                post_dict = {}
            
            posts.append(post_dict)
    
    # Handle the thread structure
    if hasattr(thread_data, 'thread'):
        # Start from the main thread node
        traverse_thread(thread_data.thread)
    elif hasattr(thread_data, '__dict__') and 'thread' in thread_data.__dict__:
        traverse_thread(thread_data.__dict__['thread'])
    
    # Return a simple structure with posts list
    return {'posts': posts}


def thread_to_yaml_string(thread, strip_metadata=True):
    """
    Convert thread data to a YAML-formatted string for LLM parsing.

    Args:
        thread: The thread data from get_post_thread
        strip_metadata: Whether to strip metadata fields for cleaner output

    Returns:
        YAML-formatted string representation of the thread
    """
    # First flatten the thread structure to avoid deep nesting
    flattened = flatten_thread_structure(thread)
    
    # Convert complex objects to basic types
    basic_thread = convert_to_basic_types(flattened)

    if strip_metadata:
        # Create a copy and strip unwanted fields
        cleaned_thread = strip_fields(basic_thread, STRIP_FIELDS)
    else:
        cleaned_thread = basic_thread

    return yaml.dump(cleaned_thread, indent=2, allow_unicode=True, default_flow_style=False)







def get_session(username: str) -> Optional[str]:
    try:
        with open(f"session_{username}.txt", encoding="UTF-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.debug(f"No existing session found for {username}")
        return None

def save_session(username: str, session_string: str) -> None:
    with open(f"session_{username}.txt", "w", encoding="UTF-8") as f:
        f.write(session_string)
    logger.debug(f"Session saved for {username}")

def on_session_change(username: str, event: SessionEvent, session: Session) -> None:
    logger.debug(f"Session changed: {event} {repr(session)}")
    if event in (SessionEvent.CREATE, SessionEvent.REFRESH):
        logger.debug(f"Saving changed session for {username}")
        save_session(username, session.export())

def init_client(username: str, password: str, pds_uri: str = "https://bsky.social") -> Client:
    if pds_uri is None:
        logger.warning(
            "No PDS URI provided. Falling back to bsky.social. Note! If you are on a non-Bluesky PDS, this can cause logins to fail. Please provide a PDS URI using the PDS_URI environment variable."
        )
        pds_uri = "https://bsky.social"

    # Print the PDS URI
    logger.debug(f"Using PDS URI: {pds_uri}")

    client = Client(pds_uri)
    client.on_session_change(
        lambda event, session: on_session_change(username, event, session)
    )

    session_string = get_session(username)
    if session_string:
        logger.debug(f"Reusing existing session for {username}")
        client.login(session_string=session_string)
    else:
        logger.debug(f"Creating new session for {username}")
        client.login(username, password)

    return client


def default_login() -> Client:
    # Try to load from config first, fall back to environment variables
    try:
        from config_loader import get_bluesky_config
        config = get_bluesky_config()
        username = config['username']
        password = config['password']
        pds_uri = config['pds_uri']
    except (ImportError, FileNotFoundError, KeyError) as e:
        logger.warning(f"Could not load from config file ({e}), falling back to environment variables")
        username = os.getenv("BSKY_USERNAME")
        password = os.getenv("BSKY_PASSWORD")
        pds_uri = os.getenv("PDS_URI", "https://bsky.social")

        if username is None:
            logger.error(
                "No username provided. Please provide a username using the BSKY_USERNAME environment variable or config.yaml."
            )
            exit()

        if password is None:
            logger.error(
                "No password provided. Please provide a password using the BSKY_PASSWORD environment variable or config.yaml."
            )
            exit()

    return init_client(username, password, pds_uri)

def remove_outside_quotes(text: str) -> str:
    """
    Remove outside double quotes from response text.
    
    Only handles double quotes to avoid interfering with contractions:
    - Double quotes: "text" → text
    - Preserves single quotes and internal quotes
    
    Args:
        text: The text to process
        
    Returns:
        Text with outside double quotes removed
    """
    if not text or len(text) < 2:
        return text
    
    text = text.strip()
    
    # Only remove double quotes from start and end
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    
    return text

def reply_to_post(client: Client, text: str, reply_to_uri: str, reply_to_cid: str, root_uri: Optional[str] = None, root_cid: Optional[str] = None, lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Reply to a post on Bluesky with rich text support.

    Args:
        client: Authenticated Bluesky client
        text: The reply text
        reply_to_uri: The URI of the post being replied to (parent)
        reply_to_cid: The CID of the post being replied to (parent)
        root_uri: The URI of the root post (if replying to a reply). If None, uses reply_to_uri
        root_cid: The CID of the root post (if replying to a reply). If None, uses reply_to_cid
        lang: Language code for the post (e.g., 'en-US', 'es', 'ja')

    Returns:
        The response from sending the post
    """
    import re
    
    # If root is not provided, this is a reply to the root post
    if root_uri is None:
        root_uri = reply_to_uri
        root_cid = reply_to_cid

    # Create references for the reply
    parent_ref = models.create_strong_ref(models.ComAtprotoRepoStrongRef.Main(uri=reply_to_uri, cid=reply_to_cid))
    root_ref = models.create_strong_ref(models.ComAtprotoRepoStrongRef.Main(uri=root_uri, cid=root_cid))

    # Parse rich text facets (mentions and URLs)
    facets = []
    text_bytes = text.encode("UTF-8")
    
    # Parse mentions - fixed to handle @ at start of text
    mention_regex = rb"(?:^|[$|\W])(@([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    
    for m in re.finditer(mention_regex, text_bytes):
        handle = m.group(1)[1:].decode("UTF-8")  # Remove @ prefix
        # Adjust byte positions to account for the optional prefix
        mention_start = m.start(1)
        mention_end = m.end(1)
        try:
            # Resolve handle to DID using the API
            resolve_resp = client.app.bsky.actor.get_profile({'actor': handle})
            if resolve_resp and hasattr(resolve_resp, 'did'):
                facets.append(
                    models.AppBskyRichtextFacet.Main(
                        index=models.AppBskyRichtextFacet.ByteSlice(
                            byteStart=mention_start,
                            byteEnd=mention_end
                        ),
                        features=[models.AppBskyRichtextFacet.Mention(did=resolve_resp.did)]
                    )
                )
        except Exception as e:
            logger.debug(f"Failed to resolve handle {handle}: {e}")
            continue
    
    # Parse URLs - fixed to handle URLs at start of text
    url_regex = rb"(?:^|[$|\W])(https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
    
    for m in re.finditer(url_regex, text_bytes):
        url = m.group(1).decode("UTF-8")
        # Adjust byte positions to account for the optional prefix
        url_start = m.start(1)
        url_end = m.end(1)
        facets.append(
            models.AppBskyRichtextFacet.Main(
                index=models.AppBskyRichtextFacet.ByteSlice(
                    byteStart=url_start,
                    byteEnd=url_end
                ),
                features=[models.AppBskyRichtextFacet.Link(uri=url)]
            )
        )

    # Send the reply with facets if any were found
    if facets:
        response = client.send_post(
            text=text,
            reply_to=models.AppBskyFeedPost.ReplyRef(parent=parent_ref, root=root_ref),
            facets=facets,
            langs=[lang] if lang else None
        )
    else:
        response = client.send_post(
            text=text,
            reply_to=models.AppBskyFeedPost.ReplyRef(parent=parent_ref, root=root_ref),
            langs=[lang] if lang else None
        )

    logger.info(f"Reply sent successfully: {response.uri}")
    return response


def get_post_thread(client: Client, uri: str) -> Optional[Dict[str, Any]]:
    """
    Get the thread containing a post to find root post information.

    Args:
        client: Authenticated Bluesky client
        uri: The URI of the post

    Returns:
        The thread data or None if not found
    """
    try:
        thread = client.app.bsky.feed.get_post_thread({'uri': uri, 'parent_height': 60, 'depth': 10})
        return thread
    except Exception as e:
        logger.error(f"Error fetching post thread: {e}")
        return None


def reply_to_notification(client: Client, notification: Any, reply_text: str, lang: str = "en-US") -> Optional[Dict[str, Any]]:
    """
    Reply to a notification (mention or reply).

    Args:
        client: Authenticated Bluesky client
        notification: The notification object from list_notifications
        reply_text: The text to reply with
        lang: Language code for the post (defaults to "en-US")

    Returns:
        The response from sending the reply or None if failed
    """
    try:
        # Get the post URI and CID from the notification (handle both dict and object)
        if isinstance(notification, dict):
            post_uri = notification.get('uri')
            post_cid = notification.get('cid')
        elif hasattr(notification, 'uri') and hasattr(notification, 'cid'):
            post_uri = notification.uri
            post_cid = notification.cid
        else:
            post_uri = None
            post_cid = None

        if not post_uri or not post_cid:
            logger.error("Notification doesn't have required uri/cid fields")
            return None

        # Get the thread to find the root post
        thread_data = get_post_thread(client, post_uri)

        if thread_data and hasattr(thread_data, 'thread'):
            thread = thread_data.thread

            # Find root post
            root_uri = post_uri
            root_cid = post_cid

            # If this has a parent, find the root
            if hasattr(thread, 'parent') and thread.parent:
                # Keep going up until we find the root
                current = thread
                while hasattr(current, 'parent') and current.parent:
                    current = current.parent
                    if hasattr(current, 'post') and hasattr(current.post, 'uri') and hasattr(current.post, 'cid'):
                        root_uri = current.post.uri
                        root_cid = current.post.cid

            # Reply to the notification
            return reply_to_post(
                client=client,
                text=reply_text,
                reply_to_uri=post_uri,
                reply_to_cid=post_cid,
                root_uri=root_uri,
                root_cid=root_cid,
                lang=lang
            )
        else:
            # If we can't get thread data, just reply directly
            return reply_to_post(
                client=client,
                text=reply_text,
                reply_to_uri=post_uri,
                reply_to_cid=post_cid,
                lang=lang
            )

    except Exception as e:
        logger.error(f"Error replying to notification: {e}")
        return None


def reply_with_thread_to_notification(client: Client, notification: Any, reply_messages: List[str], lang: str = "en-US") -> Optional[List[Dict[str, Any]]]:
    """
    Reply to a notification with a threaded chain of messages (max 15).

    Args:
        client: Authenticated Bluesky client
        notification: The notification object from list_notifications
        reply_messages: List of reply texts (max 15 messages, each max 300 chars)
        lang: Language code for the posts (defaults to "en-US")

    Returns:
        List of responses from sending the replies or None if failed
    """
    try:
        # Validate input
        if not reply_messages or len(reply_messages) == 0:
            logger.error("Reply messages list cannot be empty")
            return None
        if len(reply_messages) > 15:
            logger.error(f"Cannot send more than 15 reply messages (got {len(reply_messages)})")
            return None
        
        # Get the post URI and CID from the notification (handle both dict and object)
        if isinstance(notification, dict):
            post_uri = notification.get('uri')
            post_cid = notification.get('cid')
        elif hasattr(notification, 'uri') and hasattr(notification, 'cid'):
            post_uri = notification.uri
            post_cid = notification.cid
        else:
            post_uri = None
            post_cid = None

        if not post_uri or not post_cid:
            logger.error("Notification doesn't have required uri/cid fields")
            return None

        # Get the thread to find the root post
        thread_data = get_post_thread(client, post_uri)
        
        root_uri = post_uri
        root_cid = post_cid

        if thread_data and hasattr(thread_data, 'thread'):
            thread = thread_data.thread
            # If this has a parent, find the root
            if hasattr(thread, 'parent') and thread.parent:
                # Keep going up until we find the root
                current = thread
                while hasattr(current, 'parent') and current.parent:
                    current = current.parent
                    if hasattr(current, 'post') and hasattr(current.post, 'uri') and hasattr(current.post, 'cid'):
                        root_uri = current.post.uri
                        root_cid = current.post.cid

        # Send replies in sequence, creating a thread
        responses = []
        current_parent_uri = post_uri
        current_parent_cid = post_cid
        
        for i, message in enumerate(reply_messages):
            logger.info(f"Sending reply {i+1}/{len(reply_messages)}: {message[:50]}...")
            
            # Send this reply
            response = reply_to_post(
                client=client,
                text=message,
                reply_to_uri=current_parent_uri,
                reply_to_cid=current_parent_cid,
                root_uri=root_uri,
                root_cid=root_cid,
                lang=lang
            )
            
            if not response:
                logger.error(f"Failed to send reply {i+1}, posting system failure message")
                # Try to post a system failure message
                failure_response = reply_to_post(
                    client=client,
                    text="[SYSTEM FAILURE: COULD NOT POST MESSAGE, PLEASE TRY AGAIN]",
                    reply_to_uri=current_parent_uri,
                    reply_to_cid=current_parent_cid,
                    root_uri=root_uri,
                    root_cid=root_cid,
                    lang=lang
                )
                if failure_response:
                    responses.append(failure_response)
                    current_parent_uri = failure_response.uri
                    current_parent_cid = failure_response.cid
                else:
                    logger.error("Could not even send system failure message, stopping thread")
                    return responses if responses else None
            else:
                responses.append(response)
                # Update parent references for next reply (if any)
                if i < len(reply_messages) - 1:  # Not the last message
                    current_parent_uri = response.uri
                    current_parent_cid = response.cid
                
        logger.info(f"Successfully sent {len(responses)} threaded replies")
        return responses

    except Exception as e:
        logger.error(f"Error sending threaded reply to notification: {e}")
        return None


if __name__ == "__main__":
    client = default_login()
    # do something with the client
    logger.info("Client is ready to use!")
