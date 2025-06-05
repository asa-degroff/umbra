import os
import logging
from typing import Optional, Dict, Any
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
    "image",
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
    "embed",
    "entities",
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


def thread_to_yaml_string(thread, strip_metadata=True):
    """
    Convert thread data to a YAML-formatted string for LLM parsing.
    
    Args:
        thread: The thread data from get_post_thread
        strip_metadata: Whether to strip metadata fields for cleaner output
    
    Returns:
        YAML-formatted string representation of the thread
    """
    # First convert complex objects to basic types
    basic_thread = convert_to_basic_types(thread)
    
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
    logger.info(f"Session changed: {event} {repr(session)}")
    if event in (SessionEvent.CREATE, SessionEvent.REFRESH):
        logger.info(f"Saving changed session for {username}")
        save_session(username, session.export())

def init_client(username: str, password: str) -> Client:
    pds_uri = os.getenv("PDS_URI")
    if pds_uri is None:
        logger.warning(
            "No PDS URI provided. Falling back to bsky.social. Note! If you are on a non-Bluesky PDS, this can cause logins to fail. Please provide a PDS URI using the PDS_URI environment variable."
        )
        pds_uri = "https://bsky.social"

    # Print the PDS URI
    logger.info(f"Using PDS URI: {pds_uri}")

    client = Client(pds_uri)
    client.on_session_change(
        lambda event, session: on_session_change(username, event, session)
    )

    session_string = get_session(username)
    if session_string:
        logger.info(f"Reusing existing session for {username}")
        client.login(session_string=session_string)
    else:
        logger.info(f"Creating new session for {username}")
        client.login(username, password)

    return client


def default_login() -> Client:
    username = os.getenv("BSKY_USERNAME")
    password = os.getenv("BSKY_PASSWORD")

    if username is None:
        logger.error(
            "No username provided. Please provide a username using the BSKY_USERNAME environment variable."
        )
        exit()

    if password is None:
        logger.error(
            "No password provided. Please provide a password using the BSKY_PASSWORD environment variable."
        )
        exit()

    return init_client(username, password)

def reply_to_post(client: Client, text: str, reply_to_uri: str, reply_to_cid: str, root_uri: Optional[str] = None, root_cid: Optional[str] = None) -> Dict[str, Any]:
    """
    Reply to a post on Bluesky.

    Args:
        client: Authenticated Bluesky client
        text: The reply text
        reply_to_uri: The URI of the post being replied to (parent)
        reply_to_cid: The CID of the post being replied to (parent)
        root_uri: The URI of the root post (if replying to a reply). If None, uses reply_to_uri
        root_cid: The CID of the root post (if replying to a reply). If None, uses reply_to_cid

    Returns:
        The response from sending the post
    """
    # If root is not provided, this is a reply to the root post
    if root_uri is None:
        root_uri = reply_to_uri
        root_cid = reply_to_cid

    # Create references for the reply
    parent_ref = models.create_strong_ref(models.ComAtprotoRepoStrongRef.Main(uri=reply_to_uri, cid=reply_to_cid))
    root_ref = models.create_strong_ref(models.ComAtprotoRepoStrongRef.Main(uri=root_uri, cid=root_cid))

    # Send the reply
    response = client.send_post(
        text=text,
        reply_to=models.AppBskyFeedPost.ReplyRef(parent=parent_ref, root=root_ref)
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
        thread = client.app.bsky.feed.get_post_thread({'uri': uri, 'parent_height': 80, 'depth': 10})
        return thread
    except Exception as e:
        logger.error(f"Error fetching post thread: {e}")
        return None


def reply_to_notification(client: Client, notification: Any, reply_text: str) -> Optional[Dict[str, Any]]:
    """
    Reply to a notification (mention or reply).

    Args:
        client: Authenticated Bluesky client
        notification: The notification object from list_notifications
        reply_text: The text to reply with

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
                root_cid=root_cid
            )
        else:
            # If we can't get thread data, just reply directly
            return reply_to_post(
                client=client,
                text=reply_text,
                reply_to_uri=post_uri,
                reply_to_cid=post_cid
            )

    except Exception as e:
        logger.error(f"Error replying to notification: {e}")
        return None


if __name__ == "__main__":
    client = default_login()
    # do something with the client
    logger.info("Client is ready to use!")
