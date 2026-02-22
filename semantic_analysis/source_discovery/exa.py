"""
Exa source provider.

Uses the Exa Search API for neural/semantic search with research paper focus,
and find-similar for URL-based discovery.
API key required. See https://exa.ai/docs
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone, timedelta

import requests

from .base import SourceProvider, DiscoveredSource

logger = logging.getLogger('umbra.source_discovery.exa')

EXA_API = "https://api.exa.ai"

# Default daily limits
DEFAULT_MAX_REQUESTS_PER_DAY = 50
DEFAULT_MAX_COST_PER_DAY = 1.00  # USD


class ExaBudgetTracker:
    """Tracks daily Exa API usage (requests + cost) with auto-reset at midnight UTC."""

    def __init__(
        self,
        usage_file: str = "data/exa_usage.json",
        max_requests: int = DEFAULT_MAX_REQUESTS_PER_DAY,
        max_cost: float = DEFAULT_MAX_COST_PER_DAY,
    ):
        self.usage_file = Path(usage_file)
        self.max_requests = max_requests
        self.max_cost = max_cost
        self._usage = self._load()

    def _load(self) -> dict:
        """Load usage data, resetting if it's a new day."""
        try:
            if self.usage_file.exists():
                data = json.loads(self.usage_file.read_text())
                # Reset if the date has changed
                if data.get("date") == self._today():
                    return data
        except Exception as e:
            logger.debug(f"Could not load Exa usage file: {e}")

        return self._fresh()

    def _fresh(self) -> dict:
        return {"date": self._today(), "requests": 0, "cost": 0.0}

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _save(self):
        """Persist usage to disk."""
        try:
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            self.usage_file.write_text(json.dumps(self._usage, indent=2))
        except Exception as e:
            logger.debug(f"Could not save Exa usage file: {e}")

    def check_budget(self) -> bool:
        """Return True if there's budget remaining."""
        # Auto-reset on new day
        if self._usage.get("date") != self._today():
            self._usage = self._fresh()
            self._save()

        if self._usage["requests"] >= self.max_requests:
            logger.warning(
                f"Exa daily request limit reached ({self._usage['requests']}/{self.max_requests})"
            )
            return False

        if self._usage["cost"] >= self.max_cost:
            logger.warning(
                f"Exa daily cost limit reached (${self._usage['cost']:.4f}/${self.max_cost:.2f})"
            )
            return False

        return True

    def record_request(self, cost: float = 0.0):
        """Record a completed request and its cost."""
        # Auto-reset on new day
        if self._usage.get("date") != self._today():
            self._usage = self._fresh()

        self._usage["requests"] += 1
        self._usage["cost"] += cost
        self._save()

        logger.debug(
            f"Exa usage: {self._usage['requests']}/{self.max_requests} requests, "
            f"${self._usage['cost']:.4f}/${self.max_cost:.2f} cost"
        )

    @property
    def remaining_requests(self) -> int:
        if self._usage.get("date") != self._today():
            return self.max_requests
        return max(0, self.max_requests - self._usage["requests"])

    @property
    def remaining_cost(self) -> float:
        if self._usage.get("date") != self._today():
            return self.max_cost
        return max(0.0, self.max_cost - self._usage["cost"])

    @property
    def today_summary(self) -> str:
        return (
            f"{self._usage['requests']}/{self.max_requests} requests, "
            f"${self._usage['cost']:.4f}/${self.max_cost:.2f}"
        )


class ExaProvider(SourceProvider):
    """Exa source provider using neural search and find-similar."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_text_chars: int = 2000,
        search_type: str = "neural",
        category: str = "research paper",
        days_back: int = 365,
        max_requests_per_day: int = DEFAULT_MAX_REQUESTS_PER_DAY,
        max_cost_per_day: float = DEFAULT_MAX_COST_PER_DAY,
        usage_file: str = "data/exa_usage.json",
    ):
        """
        Initialize Exa provider.

        Args:
            api_key: Exa API key. Falls back to EXA_API_KEY env var, then config.yaml.
            max_text_chars: Max characters of text content per result.
            search_type: Exa search type ('neural', 'auto', 'deep').
            category: Content category filter ('research paper', 'news', etc.)
            days_back: Only return content published within this many days.
            max_requests_per_day: Daily request cap (default 50).
            max_cost_per_day: Daily cost cap in USD (default $1.00).
            usage_file: Path to JSON file for tracking daily usage.
        """
        self.api_key = api_key or os.environ.get("EXA_API_KEY", "")

        # Fall back to config.yaml
        exa_cfg = {}
        if not self.api_key:
            try:
                import yaml
                with open("config.yaml") as f:
                    cfg = yaml.safe_load(f) or {}
                exa_cfg = cfg.get("semantic_analysis", {}).get("exa", {})
                self.api_key = exa_cfg.get("api_key", "")
            except Exception:
                pass

        if not self.api_key:
            logger.warning("No Exa API key configured — ExaProvider will be disabled")

        self.max_text_chars = max_text_chars
        self.search_type = exa_cfg.get("search_type", search_type)
        self.category = exa_cfg.get("category", category)
        self.days_back = exa_cfg.get("days_back", days_back)

        # Budget tracking
        self.budget = ExaBudgetTracker(
            usage_file=usage_file,
            max_requests=exa_cfg.get("max_requests_per_day", max_requests_per_day),
            max_cost=exa_cfg.get("max_cost_per_day", max_cost_per_day),
        )

        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "UmbraBot/1.0 (https://umbra.blue; semantic analysis)",
        })
        self._last_request_time = 0.0

    @property
    def source_type(self) -> str:
        return "exa"

    def _rate_limit(self, min_interval: float = 0.25):
        """Basic rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def search(self, query: str, limit: int = 5) -> list[DiscoveredSource]:
        """
        Search Exa for research papers and academic content.

        Args:
            query: Search query (semantic/natural language works best)
            limit: Maximum results

        Returns:
            List of DiscoveredSource objects
        """
        if not self.api_key:
            return []

        if not self.budget.check_budget():
            return []

        try:
            self._rate_limit()

            # Calculate date window
            start_date = (
                datetime.now(timezone.utc) - timedelta(days=self.days_back)
            ).strftime("%Y-%m-%dT00:00:00.000Z")

            payload = {
                "query": query,
                "type": self.search_type,
                "category": self.category,
                "numResults": min(limit, 10),
                "startPublishedDate": start_date,
                "contents": {
                    "summary": {"query": query},
                    "highlights": {
                        "maxCharacters": 500,
                        "query": query,
                    },
                    "text": {
                        "maxCharacters": self.max_text_chars,
                    },
                },
            }

            response = self.session.post(
                f"{EXA_API}/search",
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            # Track usage
            cost = data.get("costDollars", {}).get("total", 0)
            self.budget.record_request(cost)

            sources = self._parse_results(data.get("results", []), query)

            logger.info(
                f"Exa search '{query}': {len(sources)} results "
                f"(${cost:.4f}, type={self.search_type}) "
                f"[budget: {self.budget.today_summary}]"
            )
            return sources

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            logger.error(f"Exa search HTTP error {status}: {e}")
            # Still count the request (it consumed quota on Exa's side)
            self.budget.record_request(0)
            return []
        except Exception as e:
            logger.error(f"Exa search error: {e}")
            return []

    def find_similar(self, url: str, limit: int = 5) -> list[DiscoveredSource]:
        """
        Find sources similar to a given URL.

        Uses Exa's embeddings-based similarity search — no query needed.

        Args:
            url: URL to find similar content for
            limit: Maximum results

        Returns:
            List of DiscoveredSource objects
        """
        if not self.api_key:
            return []

        if not self.budget.check_budget():
            return []

        try:
            self._rate_limit()

            # Calculate date window
            start_date = (
                datetime.now(timezone.utc) - timedelta(days=self.days_back)
            ).strftime("%Y-%m-%dT00:00:00.000Z")

            payload = {
                "url": url,
                "numResults": min(limit, 10),
                "startPublishedDate": start_date,
                "excludeDomains": [
                    # Exclude the source domain to get diverse results
                    self._extract_domain(url),
                ],
                "contents": {
                    "summary": True,
                    "highlights": {"maxCharacters": 500},
                    "text": {"maxCharacters": self.max_text_chars},
                },
            }

            # Remove empty excludeDomains
            if not payload["excludeDomains"][0]:
                del payload["excludeDomains"]

            response = self.session.post(
                f"{EXA_API}/findSimilar",
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            # Track usage
            cost = data.get("costDollars", {}).get("total", 0)
            self.budget.record_request(cost)

            sources = self._parse_results(
                data.get("results", []),
                query_used=f"similar:{url}",
            )

            logger.info(
                f"Exa findSimilar '{url[:60]}': {len(sources)} results "
                f"(${cost:.4f}) [budget: {self.budget.today_summary}]"
            )
            return sources

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            logger.error(f"Exa findSimilar HTTP error {status}: {e}")
            self.budget.record_request(0)
            return []
        except Exception as e:
            logger.error(f"Exa findSimilar error: {e}")
            return []

    def _parse_results(
        self, results: list[dict], query_used: str
    ) -> list[DiscoveredSource]:
        """Parse Exa API results into DiscoveredSource objects."""
        sources = []

        for result in results:
            try:
                source = self._parse_result(result, query_used)
                if source:
                    sources.append(source)
            except Exception as e:
                logger.debug(f"Failed to parse Exa result: {e}")

        return sources

    def _parse_result(
        self, result: dict, query_used: str
    ) -> Optional[DiscoveredSource]:
        """Parse a single Exa result."""
        title = result.get("title", "").strip()
        url = result.get("url", "").strip()

        if not title or not url:
            return None

        # Build excerpt from best available content
        summary = result.get("summary", "")
        highlights = result.get("highlights", [])
        full_text = result.get("text", "")
        author = result.get("author", "")
        published = result.get("publishedDate", "")

        # Excerpt: summary > highlights > text truncation
        if summary:
            excerpt_body = summary
        elif highlights:
            excerpt_body = " ".join(highlights)
        elif full_text:
            excerpt_body = full_text[:1000]
        else:
            return None  # No content at all — skip

        # Build rich excerpt
        parts = [title]
        if author:
            parts.append(f"Author: {author}")
        if published:
            parts.append(f"Published: {published[:10]}")
        parts.append("")
        parts.append(excerpt_body)

        excerpt = "\n".join(parts)[:self.max_text_chars]

        return DiscoveredSource(
            title=title,
            url=url,
            excerpt=excerpt,
            full_text=full_text or excerpt_body,
            source_type=self.source_type,
            query_used=query_used,
        )

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL for exclusion."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ""
