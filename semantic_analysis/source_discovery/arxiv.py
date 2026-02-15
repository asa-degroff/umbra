"""
arXiv source provider.

Uses the arXiv API (Atom feed) to search for preprints.
No API key required. Rate limit: ~3 req/s.
"""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Optional

import requests

from .base import SourceProvider, DiscoveredSource

logger = logging.getLogger('umbra.source_discovery.arxiv')

ARXIV_API = "https://export.arxiv.org/api/query"

# Namespace for Atom feed parsing
ATOM_NS = '{http://www.w3.org/2005/Atom}'
ARXIV_NS = '{http://arxiv.org/schemas/atom}'


class ArxivProvider(SourceProvider):
    """arXiv source provider using the Atom API."""

    def __init__(
        self,
        max_abstract_chars: int = 2000,
        categories: Optional[list[str]] = None,
    ):
        """
        Initialize arXiv provider.

        Args:
            max_abstract_chars: Max characters from abstract to keep
            categories: Optional arXiv category filter (e.g. ['cs.AI', 'cs.CL']).
                        If None, searches all categories.
        """
        self.max_abstract_chars = max_abstract_chars
        self.categories = categories
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'UmbraBot/1.0 (https://umbra.blue; semantic analysis)'
        })
        self._last_request_time = 0.0

    @property
    def source_type(self) -> str:
        return "arxiv"

    def _rate_limit(self):
        """Respect arXiv's rate limit (~3 req/s → 0.35s between requests)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 0.35:
            time.sleep(0.35 - elapsed)
        self._last_request_time = time.time()

    def search(self, query: str, limit: int = 5) -> list[DiscoveredSource]:
        """
        Search arXiv for papers matching the query.

        Args:
            query: Search query (supports arXiv query syntax)
            limit: Maximum results

        Returns:
            List of DiscoveredSource objects
        """
        try:
            self._rate_limit()

            # Build query — optionally restrict to categories
            search_query = f'all:{query}'
            if self.categories:
                cat_filter = ' OR '.join(f'cat:{c}' for c in self.categories)
                search_query = f'({search_query}) AND ({cat_filter})'

            params = {
                'search_query': search_query,
                'start': 0,
                'max_results': limit,
                'sortBy': 'relevance',
                'sortOrder': 'descending',
            }

            response = self.session.get(ARXIV_API, params=params, timeout=15)
            response.raise_for_status()

            sources = self._parse_feed(response.text, query)
            logger.info(f"arXiv search '{query}': {len(sources)} results")
            return sources

        except Exception as e:
            logger.error(f"arXiv search error: {e}")
            return []

    def _parse_feed(self, xml_text: str, query_used: str) -> list[DiscoveredSource]:
        """Parse arXiv Atom feed into DiscoveredSource objects."""
        sources = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error(f"arXiv XML parse error: {e}")
            return []

        for entry in root.findall(f'{ATOM_NS}entry'):
            try:
                source = self._parse_entry(entry, query_used)
                if source:
                    sources.append(source)
            except Exception as e:
                logger.debug(f"Failed to parse arXiv entry: {e}")

        return sources

    def _parse_entry(self, entry: ET.Element, query_used: str) -> Optional[DiscoveredSource]:
        """Parse a single Atom entry."""
        title_el = entry.find(f'{ATOM_NS}title')
        summary_el = entry.find(f'{ATOM_NS}summary')
        id_el = entry.find(f'{ATOM_NS}id')

        if title_el is None or summary_el is None or id_el is None:
            return None

        title = ' '.join(title_el.text.strip().split())  # Collapse whitespace
        abstract = ' '.join(summary_el.text.strip().split())
        arxiv_url = id_el.text.strip()

        # Ensure HTTPS
        if arxiv_url.startswith('http://'):
            arxiv_url = 'https://' + arxiv_url[7:]

        if not abstract:
            return None

        # Get authors
        authors = []
        for author_el in entry.findall(f'{ATOM_NS}author'):
            name_el = author_el.find(f'{ATOM_NS}name')
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        # Get categories
        categories = []
        for cat_el in entry.findall(f'{ARXIV_NS}primary_category'):
            term = cat_el.get('term')
            if term:
                categories.append(term)
        for cat_el in entry.findall(f'{ATOM_NS}category'):
            term = cat_el.get('term')
            if term and term not in categories:
                categories.append(term)

        # Build excerpt: title + authors + abstract
        author_str = ', '.join(authors[:5])
        if len(authors) > 5:
            author_str += f' et al. ({len(authors)} authors)'

        cat_str = ', '.join(categories[:3])
        excerpt = f"{title}\n\nAuthors: {author_str}\nCategories: {cat_str}\n\n{abstract}"
        excerpt = excerpt[:self.max_abstract_chars]

        return DiscoveredSource(
            title=title,
            url=arxiv_url,
            excerpt=excerpt,
            full_text=abstract,
            source_type=self.source_type,
            query_used=query_used,
        )
