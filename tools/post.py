"""Post tool for creating Bluesky posts."""
from pydantic import BaseModel, Field


class PostArgs(BaseModel):
    text: str = Field(..., description="The text content to post (max 300 characters)")


def post_to_bluesky(text: str) -> str:
    """Post a message to Bluesky."""
    import os
    import requests
    from datetime import datetime, timezone
    
    try:
        # Validate character limit
        if len(text) > 300:
            raise Exception(f"Post exceeds 300 character limit (current: {len(text)} characters)")
        
        # Get credentials from environment
        username = os.getenv("BSKY_USERNAME")
        password = os.getenv("BSKY_PASSWORD")
        pds_host = os.getenv("PDS_URI", "https://bsky.social")
        
        if not username or not password:
            raise Exception("BSKY_USERNAME and BSKY_PASSWORD environment variables must be set")
        
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
            raise Exception("Failed to get access token or DID from session")
        
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
        raise Exception(f"Error posting to Bluesky: {str(e)}")