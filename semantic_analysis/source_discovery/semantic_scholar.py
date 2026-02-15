"""
Semantic Scholar source provider.

Uses the Semantic Scholar Academic Graph API to search papers.
No API key required. Rate limit: 100 req/5min for unauthenticated.
"""

import logging
import time
from typing import Optional

import requests

from .base import SourceProvider, DiscoveredSource

logger = logging.getLogger('umbra.source_discovery.semantic_scholar')

S2_API = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarProvider(SourceProvider):
    """Semantic Scholar source provider using the Academic Graph API."""

    def __init__(
        self,
        max_abstract_chars: int = 2000,
        fields_of_study: Optional[list[str]] = None,
        min_citation_count: int = 0,
        year_range: Optional[str] = None,
    ):
        """
        Initialize Semantic Scholar provider.

        Args:
            max_abstract_chars: Max characters from abstract to keep
            fields_of_study: Optional filter (e.g. ['Computer Science', 'Biology']).
            min_citation_count: Minimum citation count filter
            year_range: Year filter (e.g. '2020-2026', '2024-', '-2020')
        """
        self.max_abstract_chars = max_abstract_chars
        self.fields_of_study = fields_of_study
        self.min_citation_count = min_citation_count
        self.year_range = year_range
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'UmbraBot/1.0 (https://umbra.blue; semantic analysis)'
        })
        self._last_request_time = 0.0

    @property
    def source_type(self) -> str:
        return "semantic_scholar"

    def _rate_limit(self):
        """Respect S2 rate limit (100 req / 5 min, with margin for burst sensitivity)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 5.0:
            time.sleep(5.0 - elapsed)
        self._last_request_time = time.time()

    def search(self, query: str, limit: int = 5, _retries: int = 2) -> list[DiscoveredSource]:
        """
        Search Semantic Scholar for papers matching the query.

        Args:
            query: Search query string
            limit: Maximum results
            _retries: Internal retry counter for rate limit backoff

        Returns:
            List of DiscoveredSource objects
        """
        try:
            self._rate_limit()

            params = {
                'query': query,
                'limit': min(limit, 20),  # S2 max per page is 100, keep low
                'fields': 'title,abstract,url,authors,year,citationCount,fieldsOfStudy,externalIds',
            }

            if self.fields_of_study:
                params['fieldsOfStudy'] = ','.join(self.fields_of_study)

            if self.year_range:
                params['year'] = self.year_range

            if self.min_citation_count > 0:
                params['minCitationCount'] = self.min_citation_count

            response = self.session.get(
                f"{S2_API}/paper/search",
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            papers = data.get('data', [])
            sources = []

            for paper in papers:
                source = self._parse_paper(paper, query)
                if source:
                    sources.append(source)

            logger.info(f"Semantic Scholar search '{query}': {len(sources)} results")
            return sources

        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                if _retries > 0:
                    wait = 10 * (3 - _retries)  # 10s, 20s
                    logger.warning(f"Semantic Scholar rate limited, retrying in {wait}s "
                                   f"({_retries} retries left)")
                    time.sleep(wait)
                    return self.search(query, limit, _retries - 1)
                logger.warning("Semantic Scholar rate limited, no retries left")
            else:
                logger.error(f"Semantic Scholar HTTP error: {e}")
            return []
        except Exception as e:
            logger.error(f"Semantic Scholar search error: {e}")
            return []

    def _parse_paper(self, paper: dict, query_used: str) -> Optional[DiscoveredSource]:
        """Parse a single paper result into DiscoveredSource."""
        title = (paper.get('title') or '').strip()
        abstract = paper.get('abstract') or ''

        if not title:
            return None

        if not abstract:
            logger.debug(f"Skipping paper '{title}' — no abstract available")
            return None

        # Build URL — prefer Semantic Scholar URL, fallback to DOI or ArXiv
        url = paper.get('url', '')
        external_ids = paper.get('externalIds', {}) or {}

        if not url:
            doi = external_ids.get('DOI')
            if doi:
                url = f"https://doi.org/{doi}"
            else:
                arxiv_id = external_ids.get('ArXiv')
                if arxiv_id:
                    url = f"https://arxiv.org/abs/{arxiv_id}"

        if not url:
            return None

        # Authors
        authors = []
        for author in paper.get('authors', []):
            name = author.get('name', '').strip()
            if name:
                authors.append(name)

        author_str = ', '.join(authors[:5])
        if len(authors) > 5:
            author_str += f' et al. ({len(authors)} authors)'

        # Metadata
        year = paper.get('year', '')
        citations = paper.get('citationCount', 0)
        fields = paper.get('fieldsOfStudy', []) or []
        fields_str = ', '.join(fields[:3]) if fields else 'Unknown'

        # Build excerpt
        excerpt_parts = [
            title,
            f"\nAuthors: {author_str}" if author_str else "",
            f"\nYear: {year}" if year else "",
            f"\nFields: {fields_str}",
            f"\nCitations: {citations}" if citations else "",
            f"\n\n{abstract}",
        ]
        excerpt = ''.join(excerpt_parts)[:self.max_abstract_chars]

        return DiscoveredSource(
            title=title,
            url=url,
            excerpt=excerpt,
            full_text=abstract,
            source_type=self.source_type,
            query_used=query_used,
        )
