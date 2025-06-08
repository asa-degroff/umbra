"""Standalone tool functions for Void Bluesky agent."""


def search_bluesky_posts(query: str, max_results: int = 25, author: str = None, sort: str = "latest") -> str:
    """
    Search for posts on Bluesky matching the given criteria.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return (max 100)
        author: Filter by author handle (e.g., 'user.bsky.social')
        sort: Sort order: 'latest' or 'top'
        
    Returns:
        YAML-formatted search results with posts and metadata
    """
    import os
    import yaml
    import requests
    from datetime import datetime
    
    try:
        # Validate inputs
        max_results = min(max_results, 100)
        if sort not in ["latest", "top"]:
            sort = "latest"
        
        # Build search query
        search_query = query
        if author:
            search_query = f"from:{author} {query}"
        
        # Get credentials from environment
        username = os.getenv("BSKY_USERNAME")
        password = os.getenv("BSKY_PASSWORD")
        pds_host = os.getenv("PDS_URI", "https://bsky.social")
        
        if not username or not password:
            return "Error: BSKY_USERNAME and BSKY_PASSWORD environment variables must be set"
        
        # Create session
        session_url = f"{pds_host}/xrpc/com.atproto.server.createSession"
        session_data = {
            "identifier": username,
            "password": password
        }
        
        try:
            session_response = requests.post(session_url, json=session_data, timeout=10)
            session_response.raise_for_status()
            session = session_response.json()
            access_token = session.get("accessJwt")
            
            if not access_token:
                return "Error: Failed to get access token from session"
        except Exception as e:
            return f"Error: Authentication failed. ({str(e)})"
        
        # Search posts
        headers = {"Authorization": f"Bearer {access_token}"}
        search_url = f"{pds_host}/xrpc/app.bsky.feed.searchPosts"
        params = {
            "q": search_query,
            "limit": max_results,
            "sort": sort
        }
        
        try:
            response = requests.get(search_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            search_data = response.json()
        except Exception as e:
            return f"Error: Search failed. ({str(e)})"
        
        # Format results
        results = []
        for post in search_data.get("posts", []):
            author = post.get("author", {})
            record = post.get("record", {})
            
            post_data = {
                "author": {
                    "handle": author.get("handle", ""),
                    "display_name": author.get("displayName", ""),
                },
                "text": record.get("text", ""),
                "created_at": record.get("createdAt", ""),
                "uri": post.get("uri", ""),
                "cid": post.get("cid", ""),
                "like_count": post.get("likeCount", 0),
                "repost_count": post.get("repostCount", 0),
                "reply_count": post.get("replyCount", 0),
            }
            
            # Add reply info if present
            if "reply" in record and record["reply"]:
                post_data["reply_to"] = {
                    "uri": record["reply"].get("parent", {}).get("uri", ""),
                    "cid": record["reply"].get("parent", {}).get("cid", ""),
                }
            
            results.append(post_data)
        
        return yaml.dump({
            "search_results": {
                "query": query,
                "author_filter": author,
                "sort": sort,
                "result_count": len(results),
                "posts": results
            }
        }, default_flow_style=False, sort_keys=False)
        
    except Exception as e:
        return f"Error searching Bluesky: {str(e)}"


def post_to_bluesky(text: str) -> str:
    """Post a message to Bluesky."""
    import os
    import requests
    from datetime import datetime, timezone
    
    try:
        # Validate character limit
        if len(text) > 300:
            return f"Error: Post exceeds 300 character limit (current: {len(text)} characters)"
        
        # Get credentials from environment
        username = os.getenv("BSKY_USERNAME")
        password = os.getenv("BSKY_PASSWORD")
        pds_host = os.getenv("PDS_URI", "https://bsky.social")
        
        if not username or not password:
            return "Error: BSKY_USERNAME and BSKY_PASSWORD environment variables must be set"
        
        # Create session
        session_url = f"{pds_host}/xrpc/com.atproto.server.createSession"
        session_data = {
            "identifier": username,
            "password": password
        }
        
        session_response = requests.post(session_url, json=session_data, timeout=10)
        session_response.raise_for_status()
        session = session_response.json()
        access_token = session.get("accessJwt")
        user_did = session.get("did")
        
        if not access_token or not user_did:
            return "Error: Failed to get access token or DID from session"
        
        # Build post record with facets for mentions and URLs
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        post_record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": now,
        }
        
        # Add facets for mentions and URLs
        import re
        facets = []
        
        # Parse mentions
        mention_regex = rb"[$|\W](@([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
        text_bytes = text.encode("UTF-8")
        
        for m in re.finditer(mention_regex, text_bytes):
            handle = m.group(1)[1:].decode("UTF-8")  # Remove @ prefix
            try:
                resolve_resp = requests.get(
                    f"{pds_host}/xrpc/com.atproto.identity.resolveHandle",
                    params={"handle": handle},
                    timeout=5
                )
                if resolve_resp.status_code == 200:
                    did = resolve_resp.json()["did"]
                    facets.append({
                        "index": {
                            "byteStart": m.start(1),
                            "byteEnd": m.end(1),
                        },
                        "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}],
                    })
            except:
                continue
        
        # Parse URLs
        url_regex = rb"[$|\W](https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
        
        for m in re.finditer(url_regex, text_bytes):
            url = m.group(1).decode("UTF-8")
            facets.append({
                "index": {
                    "byteStart": m.start(1),
                    "byteEnd": m.end(1),
                },
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
            })
        
        if facets:
            post_record["facets"] = facets
        
        # Create the post
        create_record_url = f"{pds_host}/xrpc/com.atproto.repo.createRecord"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        create_data = {
            "repo": user_did,
            "collection": "app.bsky.feed.post",
            "record": post_record
        }
        
        post_response = requests.post(create_record_url, headers=headers, json=create_data, timeout=10)
        post_response.raise_for_status()
        result = post_response.json()
        
        post_uri = result.get("uri")
        handle = session.get("handle", username)
        rkey = post_uri.split("/")[-1] if post_uri else ""
        post_url = f"https://bsky.app/profile/{handle}/post/{rkey}"
        
        return f"Successfully posted to Bluesky!\nPost URL: {post_url}\nText: {text}"
        
    except Exception as e:
        return f"Error posting to Bluesky: {str(e)}"


def get_bluesky_feed(feed_uri: str = None, max_posts: int = 25) -> str:
    """
    Retrieve a Bluesky feed (home timeline or custom feed).
    
    Args:
        feed_uri: Custom feed URI (e.g., 'at://did:plc:abc/app.bsky.feed.generator/feed-name'). If not provided, returns home timeline
        max_posts: Maximum number of posts to retrieve (max 100)
        
    Returns:
        YAML-formatted feed data with posts and metadata
    """
    import os
    import yaml
    import requests
    
    try:
        # Validate inputs
        max_posts = min(max_posts, 100)
        
        # Get credentials from environment
        username = os.getenv("BSKY_USERNAME")
        password = os.getenv("BSKY_PASSWORD")
        pds_host = os.getenv("PDS_URI", "https://bsky.social")
        
        if not username or not password:
            return "Error: BSKY_USERNAME and BSKY_PASSWORD environment variables must be set"
        
        # Create session
        session_url = f"{pds_host}/xrpc/com.atproto.server.createSession"
        session_data = {
            "identifier": username,
            "password": password
        }
        
        try:
            session_response = requests.post(session_url, json=session_data, timeout=10)
            session_response.raise_for_status()
            session = session_response.json()
            access_token = session.get("accessJwt")
            
            if not access_token:
                return "Error: Failed to get access token from session"
        except Exception as e:
            return f"Error: Authentication failed. ({str(e)})"
        
        # Get feed
        headers = {"Authorization": f"Bearer {access_token}"}
        
        if feed_uri:
            # Custom feed
            feed_url = f"{pds_host}/xrpc/app.bsky.feed.getFeed"
            params = {
                "feed": feed_uri,
                "limit": max_posts
            }
            feed_type = "custom"
            feed_name = feed_uri.split('/')[-1] if '/' in feed_uri else feed_uri
        else:
            # Home timeline
            feed_url = f"{pds_host}/xrpc/app.bsky.feed.getTimeline"
            params = {
                "limit": max_posts
            }
            feed_type = "home"
            feed_name = "timeline"
        
        try:
            response = requests.get(feed_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            feed_data = response.json()
        except Exception as e:
            return f"Error: Failed to get feed. ({str(e)})"
        
        # Format posts
        posts = []
        for item in feed_data.get("feed", []):
            post = item.get("post", {})
            author = post.get("author", {})
            record = post.get("record", {})
            
            post_data = {
                "author": {
                    "handle": author.get("handle", ""),
                    "display_name": author.get("displayName", ""),
                },
                "text": record.get("text", ""),
                "created_at": record.get("createdAt", ""),
                "uri": post.get("uri", ""),
                "cid": post.get("cid", ""),
                "like_count": post.get("likeCount", 0),
                "repost_count": post.get("repostCount", 0),
                "reply_count": post.get("replyCount", 0),
            }
            
            # Add repost info if present
            if "reason" in item and item["reason"]:
                reason = item["reason"]
                if reason.get("$type") == "app.bsky.feed.defs#reasonRepost":
                    by = reason.get("by", {})
                    post_data["reposted_by"] = {
                        "handle": by.get("handle", ""),
                        "display_name": by.get("displayName", ""),
                    }
            
            # Add reply info if present
            if "reply" in record and record["reply"]:
                parent = record["reply"].get("parent", {})
                post_data["reply_to"] = {
                    "uri": parent.get("uri", ""),
                    "cid": parent.get("cid", ""),
                }
            
            posts.append(post_data)
        
        # Format response
        feed_result = {
            "feed": {
                "type": feed_type,
                "name": feed_name,
                "post_count": len(posts),
                "posts": posts
            }
        }
        
        if feed_uri:
            feed_result["feed"]["uri"] = feed_uri
        
        return yaml.dump(feed_result, default_flow_style=False, sort_keys=False)
        
    except Exception as e:
        return f"Error retrieving feed: {str(e)}"


def attach_user_blocks(handles: list, agent_state: "AgentState") -> str:
    """
    Attach user-specific memory blocks to the agent. Creates blocks if they don't exist.
    
    Args:
        handles: List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])
        agent_state: The agent state object containing agent information
        
    Returns:
        String with attachment results for each handle
    """
    import os
    import logging
    from letta_client import Letta
    
    logger = logging.getLogger(__name__)
    
    try:
        client = Letta(token=os.environ["LETTA_API_KEY"])
        results = []

        # Get current blocks using the API
        current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
        current_block_labels = set()
        current_block_ids = []
        
        for block in current_blocks:
            current_block_labels.add(block.label)
            current_block_ids.append(str(block.id))
        
        # Collect new blocks to attach
        new_block_ids = []

        for handle in handles:
            # Sanitize handle for block label - completely self-contained
            clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')
            block_label = f"user_{clean_handle}"

            # Skip if already attached
            if block_label in current_block_labels:
                results.append(f"✓ {handle}: Already attached")
                continue

            # Check if block exists or create new one
            try:
                blocks = client.blocks.list(label=block_label)
                if blocks and len(blocks) > 0:
                    block = blocks[0]
                    logger.info(f"Found existing block: {block_label}")
                else:
                    block = client.blocks.create(
                        label=block_label,
                        value=f"# User: {handle}\n\nNo information about this user yet.",
                        limit=5000
                    )
                    logger.info(f"Created new block: {block_label}")

                new_block_ids.append(str(block.id))
                results.append(f"✓ {handle}: Block ready to attach")

            except Exception as e:
                results.append(f"✗ {handle}: Error - {str(e)}")
                logger.error(f"Error processing block for {handle}: {e}")
        
        # Attach all new blocks at once if there are any
        if new_block_ids:
            try:
                all_block_ids = current_block_ids + new_block_ids
                client.agents.modify(
                    agent_id=str(agent_state.id),
                    block_ids=all_block_ids
                )
                logger.info(f"Successfully attached {len(new_block_ids)} new blocks to agent")
            except Exception as e:
                logger.error(f"Error attaching blocks to agent: {e}")
                return f"Error attaching blocks to agent: {str(e)}"

        return f"Attachment results:\n" + "\n".join(results)
        
    except Exception as e:
        logger.error(f"Error attaching user blocks: {e}")
        return f"Error attaching user blocks: {str(e)}"


def detach_user_blocks(handles: list, agent_state: "AgentState") -> str:
    """
    Detach user-specific memory blocks from the agent. Blocks are preserved for later use.
    
    Args:
        handles: List of user Bluesky handles (e.g., ['user1.bsky.social', 'user2.bsky.social'])
        agent_state: The agent state object containing agent information
        
    Returns:
        String with detachment results for each handle
    """
    import os
    import logging
    from letta_client import Letta
    
    logger = logging.getLogger(__name__)
    
    try:
        client = Letta(token=os.environ["LETTA_API_KEY"])
        results = []
        blocks_to_remove = set()

        # Build mapping of block labels to IDs using the API
        current_blocks = client.agents.blocks.list(agent_id=str(agent_state.id))
        block_label_to_id = {}
        all_block_ids = []

        for block in current_blocks:
            block_label_to_id[block.label] = str(block.id)
            all_block_ids.append(str(block.id))

        # Process each handle and collect blocks to remove
        for handle in handles:
            # Sanitize handle for block label - completely self-contained
            clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')
            block_label = f"user_{clean_handle}"

            if block_label in block_label_to_id:
                blocks_to_remove.add(block_label_to_id[block_label])
                results.append(f"✓ {handle}: Marked for detachment")
            else:
                results.append(f"✗ {handle}: Not attached")

        # Remove all marked blocks at once if there are any
        if blocks_to_remove:
            try:
                # Filter out the blocks to remove
                remaining_block_ids = [bid for bid in all_block_ids if bid not in blocks_to_remove]
                client.agents.modify(
                    agent_id=str(agent_state.id),
                    block_ids=remaining_block_ids
                )
                logger.info(f"Successfully detached {len(blocks_to_remove)} blocks from agent")
            except Exception as e:
                logger.error(f"Error detaching blocks from agent: {e}")
                return f"Error detaching blocks from agent: {str(e)}"

        return f"Detachment results:\n" + "\n".join(results)
        
    except Exception as e:
        logger.error(f"Error detaching user blocks: {e}")
        return f"Error detaching user blocks: {str(e)}"


def update_user_blocks(updates: list, agent_state: "AgentState" = None) -> str:
    """
    Update the content of user-specific memory blocks.
    
    Args:
        updates: List of dictionaries with 'handle' and 'content' keys
        agent_state: The agent state object (optional, used for consistency)
        
    Returns:
        String with update results for each handle
    """
    import os
    import logging
    from letta_client import Letta
    
    logger = logging.getLogger(__name__)
    
    try:
        client = Letta(token=os.environ["LETTA_API_KEY"])
        results = []

        for update in updates:
            handle = update.get('handle')
            new_content = update.get('content')
            
            if not handle or not new_content:
                results.append(f"✗ Invalid update: missing handle or content")
                continue
                
            # Sanitize handle for block label - completely self-contained
            clean_handle = handle.lstrip('@').replace('.', '_').replace('-', '_').replace(' ', '_')
            block_label = f"user_{clean_handle}"

            try:
                # Find the block
                blocks = client.blocks.list(label=block_label)
                if not blocks or len(blocks) == 0:
                    results.append(f"✗ {handle}: Block not found - use attach_user_blocks first")
                    continue

                block = blocks[0]

                # Update block content
                updated_block = client.blocks.modify(
                    block_id=str(block.id),
                    value=new_content
                )

                preview = new_content[:100] + "..." if len(new_content) > 100 else new_content
                results.append(f"✓ {handle}: Updated - {preview}")

            except Exception as e:
                results.append(f"✗ {handle}: Error - {str(e)}")
                logger.error(f"Error updating block for {handle}: {e}")

        return f"Update results:\n" + "\n".join(results)
        
    except Exception as e:
        logger.error(f"Error updating user blocks: {e}")
        return f"Error updating user blocks: {str(e)}"