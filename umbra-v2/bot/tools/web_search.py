"""
Web search tool using Brave Search API.

Replaces Letta's built-in web_search (which uses Exa) for self-hosted deployments.
"""

import os
import json
from typing import Optional, List
from pydantic import BaseModel, Field


class WebSearchArgs(BaseModel):
    query: str = Field(description="The search query")
    num_results: int = Field(default=10, ge=1, le=20, description="Number of results to return")
    freshness: Optional[str] = Field(
        default=None,
        description="Time filter: 'pd' (past day), 'pw' (past week), 'pm' (past month), 'py' (past year)",
    )


def web_search(
    query: str,
    num_results: int = 10,
    freshness: Optional[str] = None,
) -> str:
    """
    Search the web using Brave Search API.

    Returns relevant web results with titles, URLs, and descriptions.

    Args:
        query: The search query to find relevant web content.
        num_results: Number of results to return (1-20). Defaults to 10.
        freshness: Time filter for results. Options: 'pd' (past day),
                   'pw' (past week), 'pm' (past month), 'py' (past year).

    Returns:
        JSON string containing search results with title, url, and description.
    """
    import requests

    api_key = os.environ.get("BRAVE_SEARCH_API_KEY")
    if not api_key:
        raise ValueError("BRAVE_SEARCH_API_KEY environment variable not set")

    params = {
        "q": query,
        "count": min(num_results, 20),
    }
    if freshness:
        params["freshness"] = freshness

    resp = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        },
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("web", {}).get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
            "age": item.get("age", ""),
        })

    return json.dumps(results, indent=2)
