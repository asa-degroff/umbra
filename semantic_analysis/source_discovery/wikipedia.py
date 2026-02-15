"""
Wikipedia source provider.

Uses the Wikipedia API to search and fetch article content.
"""

import logging
import requests
from typing import Optional
from .base import SourceProvider, DiscoveredSource

logger = logging.getLogger('umbra.source_discovery.wikipedia')

# Wikipedia API endpoints
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"


class WikipediaProvider(SourceProvider):
    """Wikipedia source provider using the MediaWiki API."""
    
    def __init__(self, language: str = "en", max_extract_chars: int = 2000):
        """
        Initialize Wikipedia provider.
        
        Args:
            language: Wikipedia language code
            max_extract_chars: Maximum characters to extract per article
        """
        self.language = language
        self.max_extract_chars = max_extract_chars
        self.api_url = f"https://{language}.wikipedia.org/w/api.php"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'UmbraBot/1.0 (https://umbra.blue; semantic analysis)'
        })
    
    @property
    def source_type(self) -> str:
        return "wikipedia"
    
    def search(self, query: str, limit: int = 5) -> list[DiscoveredSource]:
        """
        Search Wikipedia for articles matching the query.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of DiscoveredSource objects
        """
        try:
            # Search for matching articles
            search_results = self._search_titles(query, limit)
            
            if not search_results:
                logger.debug(f"No Wikipedia results for: {query}")
                return []
            
            # Fetch extracts for each result
            sources = []
            for title in search_results:
                source = self._fetch_article(title, query)
                if source:
                    sources.append(source)
            
            logger.info(f"Wikipedia search '{query}': {len(sources)} results")
            return sources
            
        except Exception as e:
            logger.error(f"Wikipedia search error: {e}")
            return []
    
    def _search_titles(self, query: str, limit: int) -> list[str]:
        """Search for article titles matching the query."""
        params = {
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'srlimit': limit,
            'format': 'json',
        }
        
        try:
            response = self.session.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('query', {}).get('search', [])
            return [r['title'] for r in results]
            
        except Exception as e:
            logger.error(f"Wikipedia title search error: {e}")
            return []
    
    def _fetch_article(self, title: str, query_used: str) -> Optional[DiscoveredSource]:
        """Fetch article content and create DiscoveredSource."""
        params = {
            'action': 'query',
            'titles': title,
            'prop': 'extracts|info',
            'exintro': False,           # Get full article, not just intro
            'explaintext': True,        # Plain text, no HTML
            'exlimit': 1,
            'exchars': self.max_extract_chars,
            'inprop': 'url',
            'format': 'json',
        }
        
        try:
            response = self.session.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            pages = data.get('query', {}).get('pages', {})
            if not pages:
                return None
            
            # Get first (only) page
            page = list(pages.values())[0]
            
            if 'missing' in page:
                return None
            
            extract = page.get('extract', '')
            url = page.get('fullurl', f"https://{self.language}.wikipedia.org/wiki/{title.replace(' ', '_')}")
            
            if not extract:
                return None
            
            # Create excerpt (first ~500 chars or first paragraph)
            excerpt = self._create_excerpt(extract)
            
            return DiscoveredSource(
                title=title,
                url=url,
                excerpt=excerpt,
                full_text=extract,
                source_type=self.source_type,
                query_used=query_used,
            )
            
        except Exception as e:
            logger.error(f"Wikipedia article fetch error for '{title}': {e}")
            return None
    
    def _create_excerpt(self, text: str, max_length: int = 500) -> str:
        """Create a concise excerpt from article text."""
        # Try to get first meaningful paragraph
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        
        if not paragraphs:
            return text[:max_length]
        
        # Skip very short paragraphs (likely headers or stubs)
        for para in paragraphs:
            if len(para) > 100:
                if len(para) <= max_length:
                    return para
                # Truncate at sentence boundary
                sentences = para.split('. ')
                excerpt = ""
                for sent in sentences:
                    if len(excerpt) + len(sent) + 2 <= max_length:
                        excerpt += sent + ". "
                    else:
                        break
                return excerpt.strip() if excerpt else para[:max_length]
        
        # Fallback: concatenate short paragraphs
        excerpt = ""
        for para in paragraphs:
            if len(excerpt) + len(para) + 1 <= max_length:
                excerpt += para + " "
            else:
                break
        
        return excerpt.strip() if excerpt else text[:max_length]
    
    def get_article_by_title(self, title: str) -> Optional[DiscoveredSource]:
        """Fetch a specific article by exact title."""
        return self._fetch_article(title, query_used=f"direct:{title}")
