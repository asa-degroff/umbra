import os
import logging
import random
import uuid
import time
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


def extract_links_from_facets(record_text: str, facets: list) -> list:
    """
    Extract link URLs from facets with their associated text.

    Args:
        record_text: The post text (needed to extract link text using byte offsets)
        facets: List of facet objects from post record

    Returns:
        List of dicts with 'url' and 'text' keys
    """
    links = []
    text_bytes = record_text.encode('utf-8')

    for facet in facets:
        for feature in facet.features:
            if hasattr(feature, 'uri'):  # Link facet
                byte_start = facet.index.byte_start
                byte_end = facet.index.byte_end
                try:
                    link_text = text_bytes[byte_start:byte_end].decode('utf-8')
                except (UnicodeDecodeError, IndexError):
                    link_text = feature.uri  # Fallback to URL itself
                links.append({
                    'url': feature.uri,
                    'text': link_text
                })
    return links


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
            # Extract post data by accessing properties directly (not __dict__)
            # AT Protocol objects store data in properties, not __dict__
            post = node.post

            # Build post dict with proper property access
            post_dict = {}

            # Extract basic fields
            if hasattr(post, 'uri'):
                post_dict['uri'] = post.uri
            if hasattr(post, 'cid'):
                post_dict['cid'] = post.cid

            # Extract author info
            if hasattr(post, 'author') and post.author:
                author = post.author
                post_dict['author'] = {
                    'handle': getattr(author, 'handle', 'unknown'),
                    'display_name': getattr(author, 'display_name', 'unknown'),
                    'did': getattr(author, 'did', 'unknown')
                }

            # Extract record info (text, created_at, etc.)
            if hasattr(post, 'record') and post.record:
                record = post.record
                record_dict = {
                    'text': getattr(record, 'text', ''),
                    'createdAt': getattr(record, 'created_at', 'unknown')
                }

                # Extract links from facets if present
                if hasattr(record, 'facets') and record.facets:
                    links = extract_links_from_facets(
                        getattr(record, 'text', ''),
                        record.facets
                    )
                    if links:
                        record_dict['links'] = links

                # Extract embed if present
                if hasattr(record, 'embed') and record.embed:
                    record_dict['embed'] = str(record.embed)[:200]  # Summary

                post_dict['record'] = record_dict

            # Extract parent_uri for tree visualization
            parent_uri = None
            if hasattr(post, 'record') and post.record:
                record_obj = post.record
                if hasattr(record_obj, 'reply') and record_obj.reply:
                    reply_ref = record_obj.reply
                    if hasattr(reply_ref, 'parent') and reply_ref.parent:
                        if hasattr(reply_ref.parent, 'uri'):
                            parent_uri = reply_ref.parent.uri
            post_dict['parent_uri'] = parent_uri

            posts.append(post_dict)

        # Then traverse any replies (going DOWN the thread)
        if hasattr(node, 'replies') and node.replies:
            for reply in node.replies:
                traverse_thread(reply)
    
    # Handle the thread structure
    if hasattr(thread_data, 'thread'):
        # Start from the main thread node
        traverse_thread(thread_data.thread)
    elif hasattr(thread_data, '__dict__') and 'thread' in thread_data.__dict__:
        traverse_thread(thread_data.__dict__['thread'])
    
    # Return a simple structure with posts list
    return {'posts': posts}


def compute_tree_prefixes(posts: List[Dict]) -> Dict[str, str]:
    """
    Compute tree-style prefixes based on parent relationships.

    Args:
        posts: List of post dicts, each with 'uri' and 'parent_uri' keys

    Returns:
        Dict mapping uri -> prefix string (e.g., "├─ ", "│  └─ ")
    """
    if not posts:
        return {}

    uri_to_post = {p.get('uri'): p for p in posts if p.get('uri')}
    children_map: Dict[str, List[str]] = {}  # parent_uri -> [child_uris]
    root_uris: List[str] = []

    for post in posts:
        uri = post.get('uri')
        if not uri:
            continue
        parent_uri = post.get('parent_uri')
        if not parent_uri or parent_uri not in uri_to_post:
            root_uris.append(uri)
        else:
            children_map.setdefault(parent_uri, []).append(uri)

    prefixes: Dict[str, str] = {}
    visited: set = set()

    def compute_recursive(uri: str, ancestors_last: List[bool]):
        if uri in visited:
            return
        visited.add(uri)

        prefix_parts = []
        for is_last in ancestors_last[:-1]:
            prefix_parts.append("   " if is_last else "│  ")
        if ancestors_last:
            prefix_parts.append("└─ " if ancestors_last[-1] else "├─ ")
        prefixes[uri] = "".join(prefix_parts)

        children = children_map.get(uri, [])
        for i, child_uri in enumerate(children):
            compute_recursive(child_uri, ancestors_last + [i == len(children) - 1])

    for i, root_uri in enumerate(root_uris):
        if len(root_uris) == 1:
            prefixes[root_uri] = ""
            children = children_map.get(root_uri, [])
            for j, child_uri in enumerate(children):
                compute_recursive(child_uri, [j == len(children) - 1])
        else:
            compute_recursive(root_uri, [i == len(root_uris) - 1])

    return prefixes


def build_tree_view(posts: List[Dict], max_text_length: int = 200) -> str:
    """
    Build a tree-style text visualization of a thread.

    Args:
        posts: List of post dicts with uri, parent_uri, author, record fields
        max_text_length: Maximum text length before truncation

    Returns:
        Multi-line string showing thread structure with tree prefixes
    """
    if not posts:
        return "(empty thread)"

    prefixes = compute_tree_prefixes(posts)
    lines = []

    for post in posts:
        uri = post.get('uri', '')
        prefix = prefixes.get(uri, '')

        author = post.get('author', {})
        handle = author.get('handle', 'unknown')
        record = post.get('record', {})
        text = record.get('text', '').replace('\n', ' | ')
        if len(text) > max_text_length:
            text = text[:max_text_length - 3] + "..."

        lines.append(f"{prefix}@{handle}: {text}")

    return "\n".join(lines)


def thread_to_yaml_string(thread, strip_metadata=True, include_tree_view=True):
    """
    Convert thread data to a YAML-formatted string for LLM parsing.

    Args:
        thread: The thread data from get_post_thread
        strip_metadata: Whether to strip metadata fields for cleaner output
        include_tree_view: Whether to prepend a tree visualization of the thread

    Returns:
        String representation of the thread with optional tree view and YAML data
    """
    # First flatten the thread structure to avoid deep nesting
    flattened = flatten_thread_structure(thread)
    posts = flattened.get('posts', [])

    output_parts = []

    # Build tree visualization if requested
    if include_tree_view and posts:
        tree_view = build_tree_view(posts)
        output_parts.append("THREAD STRUCTURE:")
        output_parts.append(tree_view)
        output_parts.append("")
        output_parts.append("FULL POST DATA:")

    # Convert complex objects to basic types
    basic_thread = convert_to_basic_types(flattened)

    if strip_metadata:
        # Create a copy and strip unwanted fields
        cleaned_thread = strip_fields(basic_thread, STRIP_FIELDS)
    else:
        cleaned_thread = basic_thread

    yaml_output = yaml.dump(cleaned_thread, indent=2, allow_unicode=True, default_flow_style=False)
    output_parts.append(yaml_output)

    return "\n".join(output_parts)







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

def init_client(username: str, password: str) -> Client:
    pds_uri = os.getenv("PDS_URI")
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
    """Login using configuration from config.yaml or environment variables."""
    try:
        from config_loader import get_bluesky_config
        bluesky_config = get_bluesky_config()
        
        username = bluesky_config['username']
        password = bluesky_config['password']
        pds_uri = bluesky_config.get('pds_uri', 'https://bsky.social')
        
        logger.info(f"Logging into Bluesky as {username} via {pds_uri}")
        
        # Use pds_uri from config
        client = Client(base_url=pds_uri)
        client.login(username, password)
        return client
        
    except Exception as e:
        logger.error(f"Failed to load Bluesky configuration: {e}")
        logger.error("Please check your config.yaml file or environment variables")
        exit(1)

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

def apply_response_delay(correlation_id: Optional[str] = None) -> float:
    """
    Apply a randomized delay before sending a response to avoid spam detection.

    Returns the delay applied in seconds (0 if disabled).
    """
    try:
        from config_loader import get_config
        config = get_config()

        enabled = config.get('response_delay.enabled', True)
        if not enabled:
            return 0.0

        min_sec = config.get('response_delay.min_seconds', 15)
        max_sec = config.get('response_delay.max_seconds', 45)

        delay = random.uniform(min_sec, max_sec)

        log_prefix = f"[{correlation_id}] " if correlation_id else ""
        logger.info(f"{log_prefix}⏳ Applying response delay of {delay:.1f}s...")

        time.sleep(delay)
        return delay

    except Exception as e:
        logger.warning(f"Failed to load response delay config: {e}")
        delay = random.uniform(15, 45)
        time.sleep(delay)
        return delay


def reply_to_post(client: Client, text: str, reply_to_uri: str, reply_to_cid: str, root_uri: Optional[str] = None, root_cid: Optional[str] = None, lang: Optional[str] = None, correlation_id: Optional[str] = None) -> Dict[str, Any]:
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
        correlation_id: Unique ID for tracking this message through the pipeline

    Returns:
        The response from sending the post
    """
    import re
    
    # Generate correlation ID if not provided
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())[:8]
    
    # Enhanced logging with structured data
    logger.info(f"[{correlation_id}] Starting reply_to_post", extra={
        'correlation_id': correlation_id,
        'text_length': len(text),
        'text_preview': text[:100] + '...' if len(text) > 100 else text,
        'reply_to_uri': reply_to_uri,
        'root_uri': root_uri,
        'lang': lang
    })
    
    start_time = time.time()
    
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
    mentions_found = []
    urls_found = []
    
    logger.debug(f"[{correlation_id}] Parsing facets from text (length: {len(text_bytes)} bytes)")
    
    # Parse mentions - fixed to handle @ at start of text
    mention_regex = rb"(?:^|[$|\W])(@([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    
    for m in re.finditer(mention_regex, text_bytes):
        handle = m.group(1)[1:].decode("UTF-8")  # Remove @ prefix
        mentions_found.append(handle)
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
                logger.debug(f"[{correlation_id}] Resolved mention @{handle} -> {resolve_resp.did}")
        except Exception as e:
            logger.warning(f"[{correlation_id}] Failed to resolve handle @{handle}: {e}")
            continue
    
    # Parse URLs - fixed to handle URLs at start of text
    url_regex = rb"(?:^|[$|\W])(https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
    
    for m in re.finditer(url_regex, text_bytes):
        url = m.group(1).decode("UTF-8")
        urls_found.append(url)
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
        logger.debug(f"[{correlation_id}] Found URL: {url}")
    
    logger.debug(f"[{correlation_id}] Facet parsing complete", extra={
        'correlation_id': correlation_id,
        'mentions_count': len(mentions_found),
        'mentions': mentions_found,
        'urls_count': len(urls_found),
        'urls': urls_found,
        'total_facets': len(facets)
    })

    # Send the reply with facets if any were found
    logger.info(f"[{correlation_id}] Sending reply to Bluesky API", extra={
        'correlation_id': correlation_id,
        'has_facets': bool(facets),
        'facet_count': len(facets),
        'lang': lang
    })
    
    try:
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
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Extract post URL for user-friendly logging
        post_url = None
        if hasattr(response, 'uri') and response.uri:
            # Convert AT-URI to web URL
            # Format: at://did:plc:xxx/app.bsky.feed.post/xxx -> https://bsky.app/profile/handle/post/xxx
            try:
                uri_parts = response.uri.split('/')
                if len(uri_parts) >= 4 and uri_parts[3] == 'app.bsky.feed.post':
                    rkey = uri_parts[4]
                    # We'd need to resolve DID to handle, but for now just use the URI
                    post_url = f"bsky://post/{rkey}"
            except:
                pass
        
        logger.info(f"[{correlation_id}] Reply sent successfully ({response_time:.3f}s) - URI: {response.uri}" + 
                   (f" - URL: {post_url}" if post_url else ""), extra={
            'correlation_id': correlation_id,
            'response_time': round(response_time, 3),
            'post_uri': response.uri,
            'post_url': post_url,
            'post_cid': getattr(response, 'cid', None),
            'text_length': len(text)
        })
        
        return response
        
    except Exception as e:
        response_time = time.time() - start_time
        logger.error(f"[{correlation_id}] Failed to send reply", extra={
            'correlation_id': correlation_id,
            'error': str(e),
            'error_type': type(e).__name__,
            'response_time': round(response_time, 3),
            'text_length': len(text)
        })
        raise


def find_last_consecutive_post_in_chain(thread_node, author_handle: str):
    """
    Find the last consecutive post in the direct reply chain by the same author.

    Starting from the given thread node, this function traverses down the direct reply chain
    (not all branches) to find the last consecutive post made by the specified author.

    Args:
        thread_node: The thread node to start from (usually the mention post's thread node)
        author_handle: The handle of the author to match (e.g., "user.bsky.social")

    Returns:
        Tuple of (uri, cid, text) for the last consecutive post by the author, or None if no consecutive posts

    Example:
        If the thread structure is:
        - Post A by @alice (mention) -> thread_node starts here
          - Post B by @alice (consecutive)
            - Post C by @alice (consecutive)
              - Post D by @bob (different author, stop here)

        Returns (uri_C, cid_C, text_C)
    """
    if not thread_node:
        return None

    # Start with the current node's post
    current_post = None
    if hasattr(thread_node, 'post') and thread_node.post:
        current_post = thread_node.post

    if not current_post:
        return None

    # Check if current post is by the target author
    current_author = None
    if hasattr(current_post, 'author') and hasattr(current_post.author, 'handle'):
        current_author = current_post.author.handle

    if current_author != author_handle:
        # Current post is not by target author, can't find consecutive posts
        return None

    # Track the last consecutive post (start with current)
    last_uri = current_post.uri if hasattr(current_post, 'uri') else None
    last_cid = current_post.cid if hasattr(current_post, 'cid') else None
    last_text = ""
    if hasattr(current_post, 'record') and hasattr(current_post.record, 'text'):
        last_text = current_post.record.text

    # Traverse down the direct reply chain
    current_node = thread_node
    while True:
        # Check if there are replies to this node
        if not hasattr(current_node, 'replies') or not current_node.replies:
            # No more replies, we've found the last consecutive post
            break

        # For direct chain traversal, we look for replies by the same author
        # If there are multiple replies, we'll take the first one by the same author
        next_node = None
        for reply in current_node.replies:
            if hasattr(reply, 'post') and reply.post:
                reply_author = None
                if hasattr(reply.post, 'author') and hasattr(reply.post.author, 'handle'):
                    reply_author = reply.post.author.handle

                if reply_author == author_handle:
                    # Found a consecutive post by same author
                    next_node = reply
                    break

        if not next_node:
            # No more consecutive posts by same author
            break

        # Update last post info to this consecutive post
        current_node = next_node
        current_post = current_node.post

        if hasattr(current_post, 'uri'):
            last_uri = current_post.uri
        if hasattr(current_post, 'cid'):
            last_cid = current_post.cid
        if hasattr(current_post, 'record') and hasattr(current_post.record, 'text'):
            last_text = current_post.record.text

    # Return the last consecutive post's metadata
    # Only return if we actually have valid URI and CID
    if last_uri and last_cid:
        return (last_uri, last_cid, last_text)

    return None


def find_consecutive_parent_posts_by_author(thread_node, author_handle: str) -> List[Dict]:
    """
    Find consecutive posts by the same author in the parent chain.

    Starting from the given thread node, this function traverses UP the parent chain
    to find all consecutive posts made by the specified author.

    This is the inverse of find_last_consecutive_post_in_chain which traverses DOWN.

    Args:
        thread_node: The thread node to start from (the notification post's thread node)
        author_handle: The handle of the author to match (e.g., "user.bsky.social")

    Returns:
        List of post dicts for consecutive posts by the author in the parent chain,
        in chronological order (oldest first). Returns empty list if no parent posts
        by the same author.

    Example:
        If the thread structure is:
        - Post A by @alice (first part)
          - Post B by @alice (consecutive) <- start from here (notification)

        Returns [Post A dict] (not including Post B since that's the current node)
    """
    parent_posts = []

    if not thread_node:
        return parent_posts

    # Traverse up the parent chain
    current_node = thread_node
    while True:
        # Check if this node has a parent
        if not hasattr(current_node, 'parent') or not current_node.parent:
            break

        parent_node = current_node.parent
        if not hasattr(parent_node, 'post') or not parent_node.post:
            break

        parent_post = parent_node.post

        # Check if parent is by the same author
        parent_author = None
        if hasattr(parent_post, 'author') and hasattr(parent_post.author, 'handle'):
            parent_author = parent_post.author.handle

        if parent_author != author_handle:
            # Parent is by different author, stop here
            break

        # Collect this parent post
        post_dict = {
            'uri': getattr(parent_post, 'uri', ''),
            'cid': getattr(parent_post, 'cid', ''),
            'author': {
                'handle': parent_author,
                'display_name': getattr(parent_post.author, 'display_name', '') if hasattr(parent_post, 'author') else '',
                'did': getattr(parent_post.author, 'did', '') if hasattr(parent_post, 'author') else ''
            },
            'record': {
                'text': getattr(parent_post.record, 'text', '') if hasattr(parent_post, 'record') else '',
                'createdAt': getattr(parent_post.record, 'created_at', '') if hasattr(parent_post, 'record') else ''
            }
        }
        parent_posts.append(post_dict)

        # Move up to the next parent
        current_node = parent_node

    # Return in chronological order (oldest first)
    parent_posts.reverse()
    return parent_posts


def get_post_thread(client: Client, uri: str, parent_height: int = 80, depth: int = 25) -> Optional[Dict[str, Any]]:
    """
    Get the thread containing a post including all parent and reply posts.

    Args:
        client: Authenticated Bluesky client
        uri: The URI of the post
        parent_height: How many parent posts to fetch (default: 80)
        depth: How many reply levels deep to fetch (default: 25 for complete threads)

    Returns:
        The thread data or None if not found
    """
    try:
        thread = client.app.bsky.feed.get_post_thread({'uri': uri, 'parent_height': parent_height, 'depth': depth})
        return thread
    except Exception as e:
        logger.error(f"Error fetching post thread: {e}")
        return None


def reply_to_notification(client: Client, notification: Any, reply_text: str, lang: str = "en-US", correlation_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Reply to a notification (mention or reply).

    Args:
        client: Authenticated Bluesky client
        notification: The notification object from list_notifications
        reply_text: The text to reply with
        lang: Language code for the post (defaults to "en-US")
        correlation_id: Unique ID for tracking this message through the pipeline

    Returns:
        The response from sending the reply or None if failed
    """
    # Generate correlation ID if not provided
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())[:8]
    
    logger.info(f"[{correlation_id}] Processing reply_to_notification", extra={
        'correlation_id': correlation_id,
        'reply_length': len(reply_text),
        'lang': lang
    })

    # Apply response delay before sending
    apply_response_delay(correlation_id)

    try:
        # Get the post URI and CID from the notification (handle both dict and object)
        if isinstance(notification, dict):
            post_uri = notification.get('uri')
            post_cid = notification.get('cid')
            # Check if the notification record has reply info with root
            record = notification.get('record', {})
            reply_info = record.get('reply') if isinstance(record, dict) else None
        elif hasattr(notification, 'uri') and hasattr(notification, 'cid'):
            post_uri = notification.uri
            post_cid = notification.cid
            # Check if the notification record has reply info with root
            reply_info = None
            if hasattr(notification, 'record') and hasattr(notification.record, 'reply'):
                reply_info = notification.record.reply
        else:
            post_uri = None
            post_cid = None
            reply_info = None

        if not post_uri or not post_cid:
            logger.error("Notification doesn't have required uri/cid fields")
            return None

        # Determine root: if post has reply info, use its root; otherwise this post IS the root
        if reply_info:
            # Extract root from the notification's reply structure
            if isinstance(reply_info, dict):
                root_ref = reply_info.get('root')
                if root_ref and isinstance(root_ref, dict):
                    root_uri = root_ref.get('uri', post_uri)
                    root_cid = root_ref.get('cid', post_cid)
                else:
                    # No root in reply info, use post as root
                    root_uri = post_uri
                    root_cid = post_cid
            elif hasattr(reply_info, 'root'):
                if hasattr(reply_info.root, 'uri') and hasattr(reply_info.root, 'cid'):
                    root_uri = reply_info.root.uri
                    root_cid = reply_info.root.cid
                else:
                    root_uri = post_uri
                    root_cid = post_cid
            else:
                root_uri = post_uri
                root_cid = post_cid
        else:
            # No reply info means this post IS the root
            root_uri = post_uri
            root_cid = post_cid

        # Reply to the notification
        return reply_to_post(
            client=client,
            text=reply_text,
            reply_to_uri=post_uri,
            reply_to_cid=post_cid,
            root_uri=root_uri,
            root_cid=root_cid,
            lang=lang,
            correlation_id=correlation_id
        )

    except Exception as e:
        logger.error(f"[{correlation_id}] Error replying to notification: {e}", extra={
            'correlation_id': correlation_id,
            'error': str(e),
            'error_type': type(e).__name__
        })
        return None


def reply_with_thread_to_notification(client: Client, notification: Any, reply_messages: List[str], lang: str = "en-US", correlation_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Reply to a notification with a threaded chain of messages (max 15).

    Args:
        client: Authenticated Bluesky client
        notification: The notification object from list_notifications
        reply_messages: List of reply texts (max 15 messages, each max 300 chars)
        lang: Language code for the posts (defaults to "en-US")
        correlation_id: Unique ID for tracking this message through the pipeline

    Returns:
        List of responses from sending the replies or None if failed
    """
    # Generate correlation ID if not provided
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())[:8]
    
    logger.info(f"[{correlation_id}] Starting threaded reply", extra={
        'correlation_id': correlation_id,
        'message_count': len(reply_messages),
        'total_length': sum(len(msg) for msg in reply_messages),
        'lang': lang
    })

    # Apply response delay before sending (only once, before first message)
    apply_response_delay(correlation_id)

    try:
        # Validate input
        if not reply_messages or len(reply_messages) == 0:
            logger.error(f"[{correlation_id}] Reply messages list cannot be empty")
            return None
        if len(reply_messages) > 15:
            logger.error(f"[{correlation_id}] Cannot send more than 15 reply messages (got {len(reply_messages)})")
            return None
        
        # Get the post URI and CID from the notification (handle both dict and object)
        if isinstance(notification, dict):
            post_uri = notification.get('uri')
            post_cid = notification.get('cid')
            # Check if the notification record has reply info with root
            record = notification.get('record', {})
            reply_info = record.get('reply') if isinstance(record, dict) else None
        elif hasattr(notification, 'uri') and hasattr(notification, 'cid'):
            post_uri = notification.uri
            post_cid = notification.cid
            # Check if the notification record has reply info with root
            reply_info = None
            if hasattr(notification, 'record') and hasattr(notification.record, 'reply'):
                reply_info = notification.record.reply
        else:
            post_uri = None
            post_cid = None
            reply_info = None

        if not post_uri or not post_cid:
            logger.error("Notification doesn't have required uri/cid fields")
            return None

        # Determine root: if post has reply info, use its root; otherwise this post IS the root
        if reply_info:
            # Extract root from the notification's reply structure
            if isinstance(reply_info, dict):
                root_ref = reply_info.get('root')
                if root_ref and isinstance(root_ref, dict):
                    root_uri = root_ref.get('uri', post_uri)
                    root_cid = root_ref.get('cid', post_cid)
                else:
                    # No root in reply info, use post as root
                    root_uri = post_uri
                    root_cid = post_cid
            elif hasattr(reply_info, 'root'):
                if hasattr(reply_info.root, 'uri') and hasattr(reply_info.root, 'cid'):
                    root_uri = reply_info.root.uri
                    root_cid = reply_info.root.cid
                else:
                    root_uri = post_uri
                    root_cid = post_cid
            else:
                root_uri = post_uri
                root_cid = post_cid
        else:
            # No reply info means this post IS the root
            root_uri = post_uri
            root_cid = post_cid

        # Send replies in sequence, creating a thread
        responses = []
        current_parent_uri = post_uri
        current_parent_cid = post_cid

        for i, message in enumerate(reply_messages):
            thread_correlation_id = f"{correlation_id}-{i+1}"
            logger.info(f"[{thread_correlation_id}] Sending reply {i+1}/{len(reply_messages)}: {message[:50]}...")

            # Send this reply
            response = reply_to_post(
                client=client,
                text=message,
                reply_to_uri=current_parent_uri,
                reply_to_cid=current_parent_cid,
                root_uri=root_uri,
                root_cid=root_cid,
                lang=lang,
                correlation_id=thread_correlation_id
            )

            if not response:
                logger.error(f"[{thread_correlation_id}] Failed to send reply {i+1}/{len(reply_messages)}, aborting thread")
                # Don't send system failure message - just fail cleanly
                # This allows proper retry logic to handle the failure
                logger.error(f"[{correlation_id}] Thread send aborted after {len(responses)}/{len(reply_messages)} messages")
                return None
            else:
                responses.append(response)
                # Update parent references for next reply (if any)
                if i < len(reply_messages) - 1:  # Not the last message
                    current_parent_uri = response.uri
                    current_parent_cid = response.cid
                
        logger.info(f"[{correlation_id}] Successfully sent {len(responses)} threaded replies", extra={
            'correlation_id': correlation_id,
            'replies_sent': len(responses),
            'replies_requested': len(reply_messages)
        })
        return responses

    except Exception as e:
        logger.error(f"[{correlation_id}] Error sending threaded reply to notification: {e}", extra={
            'correlation_id': correlation_id,
            'error': str(e),
            'error_type': type(e).__name__,
            'message_count': len(reply_messages)
        })
        return None


def create_synthesis_ack(client: Client, note: str) -> Optional[Dict[str, Any]]:
    """
    Create a stream.thought.ack record for synthesis without a target post.
    
    This creates a synthesis acknowledgment with null subject field.
    
    Args:
        client: Authenticated Bluesky client
        note: The synthesis note/content
        
    Returns:
        The response from creating the acknowledgment record or None if failed
    """
    try:
        import requests
        import json
        from datetime import datetime, timezone
        
        # Get session info from the client
        access_token = None
        user_did = None
        
        # Try different ways to get the session info
        if hasattr(client, '_session') and client._session:
            access_token = client._session.access_jwt
            user_did = client._session.did
        elif hasattr(client, 'access_jwt'):
            access_token = client.access_jwt
            user_did = client.did if hasattr(client, 'did') else None
        else:
            logger.error("Cannot access client session information")
            return None
            
        if not access_token or not user_did:
            logger.error("Missing access token or DID from session")
            return None
            
        # Get PDS URI from config instead of environment variables
        from config_loader import get_bluesky_config
        bluesky_config = get_bluesky_config()
        pds_host = bluesky_config['pds_uri']
        
        # Create acknowledgment record with null subject
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ack_record = {
            "$type": "stream.thought.ack",
            "subject": None,  # Null subject for synthesis
            "createdAt": now,
            "note": note
        }
        
        # Create the record
        headers = {"Authorization": f"Bearer {access_token}"}
        create_record_url = f"{pds_host}/xrpc/com.atproto.repo.createRecord"
        
        create_data = {
            "repo": user_did,
            "collection": "stream.thought.ack",
            "record": ack_record
        }
        
        response = requests.post(create_record_url, headers=headers, json=create_data, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        logger.info(f"Successfully created synthesis acknowledgment")
        return result
        
    except Exception as e:
        logger.error(f"Error creating synthesis acknowledgment: {e}")
        return None


def acknowledge_post(client: Client, post_uri: str, post_cid: str, note: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Create a stream.thought.ack record to acknowledge a post.
    
    This creates a custom acknowledgment record instead of a standard Bluesky like,
    allowing umbra to track which posts it has engaged with.
    
    Args:
        client: Authenticated Bluesky client
        post_uri: The URI of the post to acknowledge
        post_cid: The CID of the post to acknowledge
        note: Optional note to attach to the acknowledgment
        
    Returns:
        The response from creating the acknowledgment record or None if failed
    """
    try:
        import requests
        import json
        from datetime import datetime, timezone
        
        # Get session info from the client
        # The atproto Client stores the session differently
        access_token = None
        user_did = None
        
        # Try different ways to get the session info
        if hasattr(client, '_session') and client._session:
            access_token = client._session.access_jwt
            user_did = client._session.did
        elif hasattr(client, 'access_jwt'):
            access_token = client.access_jwt
            user_did = client.did if hasattr(client, 'did') else None
        else:
            logger.error("Cannot access client session information")
            return None
            
        if not access_token or not user_did:
            logger.error("Missing access token or DID from session")
            return None
            
        # Get PDS URI from config instead of environment variables
        from config_loader import get_bluesky_config
        bluesky_config = get_bluesky_config()
        pds_host = bluesky_config['pds_uri']
        
        # Create acknowledgment record with stream.thought.ack type
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ack_record = {
            "$type": "stream.thought.ack",
            "subject": {
                "uri": post_uri,
                "cid": post_cid
            },
            "createdAt": now,
            "note": note  # Will be null if no note provided
        }
        
        # Create the record
        headers = {"Authorization": f"Bearer {access_token}"}
        create_record_url = f"{pds_host}/xrpc/com.atproto.repo.createRecord"
        
        create_data = {
            "repo": user_did,
            "collection": "stream.thought.ack",
            "record": ack_record
        }
        
        response = requests.post(create_record_url, headers=headers, json=create_data, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        logger.info(f"Successfully acknowledged post: {post_uri}")
        return result
        
    except Exception as e:
        logger.error(f"Error acknowledging post: {e}")
        return None


def create_tool_call_record(client: Client, tool_name: str, arguments: str, tool_call_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Create a stream.thought.tool_call record to track tool usage.
    
    This creates a record of tool calls made by umbra during processing,
    allowing for analysis of tool usage patterns and debugging.
    
    Args:
        client: Authenticated Bluesky client
        tool_name: Name of the tool being called
        arguments: Raw JSON string of the tool arguments
        tool_call_id: Optional ID of the tool call for correlation
        
    Returns:
        The response from creating the tool call record or None if failed
    """
    try:
        import requests
        import json
        from datetime import datetime, timezone
        
        # Get session info from the client
        access_token = None
        user_did = None
        
        # Try different ways to get the session info
        if hasattr(client, '_session') and client._session:
            access_token = client._session.access_jwt
            user_did = client._session.did
        elif hasattr(client, 'access_jwt'):
            access_token = client.access_jwt
            user_did = client.did if hasattr(client, 'did') else None
        else:
            logger.error("Cannot access client session information")
            return None
            
        if not access_token or not user_did:
            logger.error("Missing access token or DID from session")
            return None
            
        # Get PDS URI from config instead of environment variables
        from config_loader import get_bluesky_config
        bluesky_config = get_bluesky_config()
        pds_host = bluesky_config['pds_uri']
        
        # Create tool call record
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        tool_record = {
            "$type": "stream.thought.tool.call",
            "tool_name": tool_name,
            "arguments": arguments,  # Store as string to avoid parsing issues
            "createdAt": now
        }
        
        # Add tool_call_id if provided
        if tool_call_id:
            tool_record["tool_call_id"] = tool_call_id
        
        # Create the record
        headers = {"Authorization": f"Bearer {access_token}"}
        create_record_url = f"{pds_host}/xrpc/com.atproto.repo.createRecord"
        
        create_data = {
            "repo": user_did,
            "collection": "stream.thought.tool.call",
            "record": tool_record
        }
        
        response = requests.post(create_record_url, headers=headers, json=create_data, timeout=10)
        if response.status_code != 200:
            logger.error(f"Tool call record creation failed: {response.status_code} - {response.text}")
        response.raise_for_status()
        result = response.json()
        
        logger.debug(f"Successfully recorded tool call: {tool_name}")
        return result
        
    except Exception as e:
        logger.error(f"Error creating tool call record: {e}")
        return None


def create_reasoning_record(client: Client, reasoning_text: str) -> Optional[Dict[str, Any]]:
    """
    Create a stream.thought.reasoning record to track agent reasoning.
    
    This creates a record of umbra's reasoning during message processing,
    providing transparency into the decision-making process.
    
    Args:
        client: Authenticated Bluesky client
        reasoning_text: The reasoning text from the agent
        
    Returns:
        The response from creating the reasoning record or None if failed
    """
    try:
        import requests
        import json
        from datetime import datetime, timezone
        
        # Get session info from the client
        access_token = None
        user_did = None
        
        # Try different ways to get the session info
        if hasattr(client, '_session') and client._session:
            access_token = client._session.access_jwt
            user_did = client._session.did
        elif hasattr(client, 'access_jwt'):
            access_token = client.access_jwt
            user_did = client.did if hasattr(client, 'did') else None
        else:
            logger.error("Cannot access client session information")
            return None
            
        if not access_token or not user_did:
            logger.error("Missing access token or DID from session")
            return None
            
        # Get PDS URI from config instead of environment variables
        from config_loader import get_bluesky_config
        bluesky_config = get_bluesky_config()
        pds_host = bluesky_config['pds_uri']
        
        # Create reasoning record
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        reasoning_record = {
            "$type": "stream.thought.reasoning",
            "reasoning": reasoning_text,
            "createdAt": now
        }
        
        # Create the record
        headers = {"Authorization": f"Bearer {access_token}"}
        create_record_url = f"{pds_host}/xrpc/com.atproto.repo.createRecord"
        
        create_data = {
            "repo": user_did,
            "collection": "stream.thought.reasoning",
            "record": reasoning_record
        }
        
        response = requests.post(create_record_url, headers=headers, json=create_data, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        logger.debug(f"Successfully recorded reasoning (length: {len(reasoning_text)} chars)")
        return result
        
    except Exception as e:
        logger.error(f"Error creating reasoning record: {e}")
        return None


if __name__ == "__main__":
    client = default_login()
    # do something with the client
    logger.info("Client is ready to use!")
