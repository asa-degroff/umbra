"""
AT Protocol Scraper

Fetches records from various AT Protocol collections for semantic analysis.
Supports Bluesky posts, Greengale/WhiteWind blogs, and Comind cognition records.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional
import requests

logger = logging.getLogger('umbra.semantic_analysis')

# Collection configurations: NSID -> text extraction function
COLLECTIONS = {
    'app.bsky.feed.post': {
        'platform': 'bluesky',
        'extract_text': lambda r: r.get('text', ''),
        'extract_created': lambda r: r.get('createdAt'),
    },
    'app.greengale.document': {
        'platform': 'greengale',
        'extract_text': lambda r: f"{r.get('title', '')}\n\n{r.get('content', '')}",
        'extract_created': lambda r: r.get('createdAt'),
    },
    'com.whtwnd.blog.entry': {
        'platform': 'whitewind',
        'extract_text': lambda r: f"{r.get('title', '')}\n\n{r.get('content', '')}",
        'extract_created': lambda r: r.get('createdAt'),
    },
    'network.comind.concept': {
        'platform': 'comind',
        'extract_text': lambda r: f"Concept: {r.get('concept', '')}\n\n{r.get('understanding', '')}",
        'extract_created': lambda r: r.get('createdAt'),
    },
    'network.comind.memory': {
        'platform': 'comind',
        'extract_text': lambda r: r.get('content', ''),
        'extract_created': lambda r: r.get('createdAt'),
    },
    'network.comind.thought': {
        'platform': 'comind',
        'extract_text': lambda r: r.get('thought', ''),
        'extract_created': lambda r: r.get('createdAt'),
    },
    'network.comind.reflection': {
        'platform': 'comind',
        'extract_text': lambda r: r.get('reflection', ''),
        'extract_created': lambda r: r.get('createdAt'),
    },
}


class ATProtoScraper:
    """Scrapes records from AT Protocol PDS."""
    
    def __init__(self, pds_host: str, did: str, access_token: Optional[str] = None):
        """
        Initialize the scraper.
        
        Args:
            pds_host: PDS host URL (e.g., "https://bsky.social")
            did: DID of the account to scrape
            access_token: Optional bearer token for authenticated requests
        """
        self.pds_host = pds_host.rstrip('/')
        self.did = did
        self.access_token = access_token
        self.session = requests.Session()
        if access_token:
            self.session.headers['Authorization'] = f'Bearer {access_token}'
        self.session.headers['User-Agent'] = 'Umbra-SemanticAnalysis/1.0'
    
    def list_records(
        self,
        collection: str,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> tuple[list[dict], Optional[str]]:
        """
        List records from a collection.
        
        Args:
            collection: The NSID of the collection
            limit: Maximum records to fetch per request
            cursor: Pagination cursor
            
        Returns:
            Tuple of (records, next_cursor)
        """
        params = {
            'repo': self.did,
            'collection': collection,
            'limit': min(limit, 100),
        }
        if cursor:
            params['cursor'] = cursor
            
        try:
            resp = self.session.get(
                f"{self.pds_host}/xrpc/com.atproto.repo.listRecords",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get('records', []), data.get('cursor')
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch {collection}: {e}")
            return [], None
    
    def scrape_collection(self, collection: str, max_records: Optional[int] = None) -> list[dict]:
        """
        Scrape all records from a collection.
        
        Args:
            collection: The NSID of the collection
            max_records: Maximum total records to fetch (None = no limit)
            
        Returns:
            List of normalized record dicts
        """
        config = COLLECTIONS.get(collection)
        if not config:
            logger.warning(f"Unknown collection: {collection}")
            return []
        
        records = []
        cursor = None
        
        while max_records is None or len(records) < max_records:
            batch, cursor = self.list_records(collection, cursor=cursor)
            if not batch:
                break
                
            for record in batch:
                uri = record.get('uri', '')
                value = record.get('value', {})
                
                # Extract text content
                text = config['extract_text'](value)
                if not text or not text.strip():
                    continue
                
                # Extract timestamp
                created_at = config['extract_created'](value)
                if created_at:
                    try:
                        # Parse ISO format
                        if isinstance(created_at, str):
                            # Handle various ISO formats
                            created_at = created_at.replace('Z', '+00:00')
                            created_at = datetime.fromisoformat(created_at)
                    except (ValueError, TypeError):
                        created_at = None
                
                records.append({
                    'uri': uri,
                    'collection': collection,
                    'platform': config['platform'],
                    'text': text.strip(),
                    'created_at': created_at,
                    'word_count': len(text.split()),
                })
            
            if not cursor:
                break
            
            # Small delay to be polite to the API
            time.sleep(0.1)
        
        logger.info(f"Scraped {len(records)} records from {collection}")
        return records
    
    def scrape_all(self, max_per_collection: Optional[int] = None) -> list[dict]:
        """
        Scrape all known collections.
        
        Args:
            max_per_collection: Maximum records per collection (None = no limit)
            
        Returns:
            List of all normalized records
        """
        all_records = []
        
        for collection in COLLECTIONS:
            records = self.scrape_collection(collection, max_per_collection)
            all_records.extend(records)
        
        # Sort by creation time (newest first)
        def sort_key(r):
            dt = r.get('created_at')
            if dt is None:
                return datetime.min.replace(tzinfo=timezone.utc)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        
        all_records.sort(key=sort_key, reverse=True)
        
        logger.info(f"Scraped {len(all_records)} total records across {len(COLLECTIONS)} collections")
        return all_records


def scrape_umbra_records(
    pds_host: str = "https://bsky.social",
    did: str = "did:plc:oetfdqwocv4aegq2yj6ix4w5",
    access_token: Optional[str] = None,
) -> list[dict]:
    """
    Convenience function to scrape Umbra's records.
    
    Args:
        pds_host: PDS host URL
        did: Umbra's DID (defaults to umbra.blue)
        access_token: Optional bearer token
        
    Returns:
        List of normalized records
    """
    scraper = ATProtoScraper(pds_host, did, access_token)
    return scraper.scrape_all()
