"""GreenGale blog post creation tool."""
from typing import Optional, Literal
from pydantic import BaseModel, Field


class GreenGaleTheme(BaseModel):
    """Theme configuration for GreenGale posts."""
    preset: Optional[Literal[
        "github-light", "github-dark", "dracula", "nord",
        "solarized-light", "solarized-dark", "monokai"
    ]] = Field(
        default=None,
        description="Preset theme name. If not provided, uses github-light."
    )
    background: Optional[str] = Field(
        default=None,
        description="Custom background color (hex, e.g. '#1a1a2e'). Requires text and accent colors."
    )
    text: Optional[str] = Field(
        default=None,
        description="Custom text color (hex, e.g. '#eaeaea'). Requires background and accent colors."
    )
    accent: Optional[str] = Field(
        default=None,
        description="Custom accent color (hex, e.g. '#00d4ff'). Requires background and text colors."
    )


class GreenGalePostArgs(BaseModel):
    title: str = Field(
        ...,
        description="Title of the blog post (max 1,000 characters)"
    )
    content: str = Field(
        ...,
        description="Main content of the blog post in Markdown format (max 100,000 characters). Supports LaTeX if enabled."
    )
    visibility: Optional[Literal["public", "url", "author"]] = Field(
        default="public",
        description="Post visibility: 'public' (visible to all), 'url' (unlisted, accessible via URL only), or 'author' (private, only visible to author)"
    )
    theme: Optional[GreenGaleTheme] = Field(
        default=None,
        description="Theme configuration. Use preset for built-in themes, or provide custom background/text/accent colors."
    )
    latex: Optional[bool] = Field(
        default=False,
        description="Enable KaTeX math rendering for LaTeX equations (e.g. $E=mc^2$ or $$\\int_0^\\infty$$)"
    )


def create_greengale_blog_post(
    title: str,
    content: str,
    visibility: Optional[str] = "public",
    theme: Optional[dict] = None,
    latex: Optional[bool] = False
) -> str:
    """
    Create a new blog post on GreenGale.

    This tool creates blog posts using the app.greengale.blog.entry lexicon on the ATProto network.
    GreenGale supports custom themes, LaTeX/KaTeX math rendering, and multiple visibility options.

    Args:
        title: Title of the blog post (max 1,000 characters)
        content: Main content of the blog post in Markdown (max 100,000 characters)
        visibility: Post visibility - 'public', 'url' (unlisted), or 'author' (private)
        theme: Theme configuration dict with either 'preset' key or custom 'background'/'text'/'accent' colors
        latex: Enable KaTeX math rendering for LaTeX equations

    Returns:
        Success message with the blog post URL

    Raises:
        Exception: If the post creation fails
    """
    import os
    import requests
    from datetime import datetime, timezone

    try:
        # Get credentials from environment
        username = os.getenv("BSKY_USERNAME")
        password = os.getenv("BSKY_PASSWORD")
        pds_host = os.getenv("PDS_URI", "https://bsky.social")

        if not username or not password:
            raise Exception("BSKY_USERNAME and BSKY_PASSWORD environment variables must be set")

        # Normalize visibility - handle both string and enum types
        if hasattr(visibility, 'value'):
            visibility = visibility.value
        visibility = str(visibility) if visibility else "public"

        # Validate inputs
        if len(title) > 1000:
            raise Exception(f"Title exceeds maximum length of 1,000 characters (got {len(title)})")
        if len(content) > 100000:
            raise Exception(f"Content exceeds maximum length of 100,000 characters (got {len(content)})")
        if visibility not in ("public", "url", "author"):
            raise Exception(f"Invalid visibility '{visibility}'. Must be 'public', 'url', or 'author'")

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
        handle = session.get("handle", username)

        if not access_token or not user_did:
            raise Exception("Failed to get access token or DID from session")

        # Create blog post record
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        blog_record = {
            "$type": "app.greengale.blog.entry",
            "title": title,
            "content": content,
            "createdAt": now,
            "visibility": visibility
        }

        # Add theme if provided - handle both Pydantic models and dicts
        theme_description = "github-light (default)"
        if theme:
            # Convert Pydantic model to dict if needed
            if hasattr(theme, 'model_dump'):
                theme_dict = theme.model_dump(exclude_none=True)
            elif hasattr(theme, 'dict'):
                theme_dict = theme.dict(exclude_none=True)
            elif isinstance(theme, dict):
                theme_dict = theme
            else:
                theme_dict = {}

            # Extract preset value if it's an enum
            preset_val = theme_dict.get("preset")
            if preset_val and hasattr(preset_val, 'value'):
                preset_val = preset_val.value

            if preset_val:
                blog_record["theme"] = {"preset": preset_val}
                theme_description = preset_val
            elif theme_dict.get("background") and theme_dict.get("text") and theme_dict.get("accent"):
                blog_record["theme"] = {
                    "background": theme_dict["background"],
                    "text": theme_dict["text"],
                    "accent": theme_dict["accent"]
                }
                theme_description = f"custom (bg: {theme_dict['background']}, text: {theme_dict['text']}, accent: {theme_dict['accent']})"
            else:
                # Default to github-light if theme is incomplete
                blog_record["theme"] = {"preset": "github-light"}
        else:
            # Default theme
            blog_record["theme"] = {"preset": "github-light"}

        # Add LaTeX flag if enabled
        if latex:
            blog_record["latex"] = True

        # Create the record
        headers = {"Authorization": f"Bearer {access_token}"}
        create_record_url = f"{pds_host}/xrpc/com.atproto.repo.createRecord"

        create_data = {
            "repo": user_did,
            "collection": "app.greengale.blog.entry",
            "record": blog_record
        }

        post_response = requests.post(create_record_url, headers=headers, json=create_data, timeout=10)
        post_response.raise_for_status()
        result = post_response.json()

        # Extract the record key from the URI
        post_uri = result.get("uri")
        if post_uri:
            rkey = post_uri.split("/")[-1]
            # Construct the GreenGale blog URL
            blog_url = f"https://greengale.app/{handle}/{rkey}"
        else:
            blog_url = "URL generation failed"

        # Build success message
        visibility_labels = {
            "public": "public",
            "url": "unlisted (URL only)",
            "author": "private (author only)"
        }

        success_parts = [
            f"Successfully created GreenGale blog post!",
            f"Title: {title}",
            f"URL: {blog_url}",
            f"Theme: {theme_description}",
            f"Visibility: {visibility_labels.get(visibility, visibility)}",
            f"LaTeX: {'enabled' if latex else 'disabled'}"
        ]

        return "\n".join(success_parts)

    except Exception as e:
        raise Exception(f"Error creating GreenGale blog post: {str(e)}")
