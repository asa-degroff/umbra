"""
Network Scraper

Fetches content from accounts in Umbra's social graph (follows, followers).
Extends the base ATProtoScraper to build a network-wide content index.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests

logger = logging.getLogger('umbra.semantic_analysis.network')

# Default rate limiting
DEFAULT_DELAY_BETWEEN_ACCOUNTS = 1.0  # seconds between different accounts
DEFAULT_DELAY_BETWEEN_REQUESTS = 0.2  # seconds between requests to same account


class NetworkScraper:
    """Scrapes content from accounts in the social graph."""
    
    def __init__(
        self,
        pds_host: str = "https://bsky.social",
        appview_host: str = "https://public.api.bsky.app",
        source_did: str = "did:plc:oetfdqwocv4aegq2yj6ix4w5",  # Umbra's DID
        access_token: Optional[str] = None,
        delay_between_accounts: float = DEFAULT_DELAY_BETWEEN_ACCOUNTS,
        delay_between_requests: float = DEFAULT_DELAY_BETWEEN_REQUESTS,
    ):
        """
        Initialize the network scraper.
        
        Args:
            pds_host: PDS host URL for repo operations
            appview_host: AppView host URL for graph queries (public API)
            source_did: DID of the central account (Umbra)
            access_token: Optional bearer token for authenticated requests
            delay_between_accounts: Seconds to wait between scraping different accounts
            delay_between_requests: Seconds to wait between API requests
        """
        self.pds_host = pds_host.rstrip('/')
        self.appview_host = appview_host.rstrip('/')
        self.source_did = source_did
        self.delay_between_accounts = delay_between_accounts
        self.delay_between_requests = delay_between_requests
        
        self.session = requests.Session()
        if access_token:
            self.session.headers['Authorization'] = f'Bearer {access_token}'
        self.session.headers['User-Agent'] = 'Umbra-NetworkAnalysis/1.0'
    
    def get_follows(self, actor: Optional[str] = None, max_results: Optional[int] = None) -> list[dict]:
        """
        Get list of accounts that an actor follows.
        
        Args:
            actor: DID or handle of the actor (defaults to source_did)
            max_results: Maximum number of follows to fetch (None = all)
            
        Returns:
            List of profile dicts with 'did', 'handle', 'displayName', etc.
        """
        actor = actor or self.source_did
        follows = []
        cursor = None
        
        while True:
            # Limit batch size if we're close to max_results
            batch_limit = 100
            if max_results:
                remaining = max_results - len(follows)
                batch_limit = min(100, remaining)
                if batch_limit <= 0:
                    break
            
            params = {
                'actor': actor,
                'limit': batch_limit,
            }
            if cursor:
                params['cursor'] = cursor
            
            try:
                resp = self.session.get(
                    f"{self.appview_host}/xrpc/app.bsky.graph.getFollows",
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                
                batch = data.get('follows', [])
                follows.extend(batch)
                
                # Check if we've reached max_results
                if max_results and len(follows) >= max_results:
                    follows = follows[:max_results]
                    break
                
                cursor = data.get('cursor')
                if not cursor or not batch:
                    break
                
                time.sleep(self.delay_between_requests)
                
            except requests.RequestException as e:
                logger.warning(f"Failed to fetch follows for {actor}: {e}")
                break
        
        logger.info(f"Found {len(follows)} accounts followed by {actor}")
        return follows
    
    def get_followers(self, actor: Optional[str] = None, max_results: Optional[int] = None) -> list[dict]:
        """
        Get list of accounts that follow an actor.
        
        Args:
            actor: DID or handle of the actor (defaults to source_did)
            max_results: Maximum number of followers to fetch (None = all)
            
        Returns:
            List of profile dicts
        """
        actor = actor or self.source_did
        followers = []
        cursor = None
        
        while True:
            params = {
                'actor': actor,
                'limit': 100,
            }
            if cursor:
                params['cursor'] = cursor
            
            try:
                resp = self.session.get(
                    f"{self.appview_host}/xrpc/app.bsky.graph.getFollowers",
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                
                batch = data.get('followers', [])
                followers.extend(batch)
                
                cursor = data.get('cursor')
                if not cursor or not batch:
                    break
                
                if max_results and len(followers) >= max_results:
                    followers = followers[:max_results]
                    break
                
                time.sleep(self.delay_between_requests)
                
            except requests.RequestException as e:
                logger.warning(f"Failed to fetch followers for {actor}: {e}")
                break
        
        logger.info(f"Found {len(followers)} followers of {actor}")
        return followers
    
    def get_author_feed(
        self,
        actor: str,
        max_posts: int = 100,
        since: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Get recent posts from an author's feed.
        
        Args:
            actor: DID or handle of the author
            max_posts: Maximum posts to fetch
            since: Only fetch posts after this datetime
            
        Returns:
            List of post dicts with 'uri', 'text', 'created_at', etc.
        """
        posts = []
        cursor = None
        
        while len(posts) < max_posts:
            params = {
                'actor': actor,
                'limit': min(100, max_posts - len(posts)),
                'filter': 'posts_no_replies',  # Just original posts, not replies
            }
            if cursor:
                params['cursor'] = cursor
            
            try:
                resp = self.session.get(
                    f"{self.appview_host}/xrpc/app.bsky.feed.getAuthorFeed",
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                
                feed = data.get('feed', [])
                if not feed:
                    break
                
                for item in feed:
                    post = item.get('post', {})
                    record = post.get('record', {})
                    
                    # Extract post data
                    uri = post.get('uri', '')
                    text = record.get('text', '')
                    created_at_str = record.get('createdAt', '')
                    
                    if not text or not text.strip():
                        continue
                    
                    # Parse timestamp
                    created_at = None
                    if created_at_str:
                        try:
                            created_at_str = created_at_str.replace('Z', '+00:00')
                            created_at = datetime.fromisoformat(created_at_str)
                        except (ValueError, TypeError):
                            pass
                    
                    # Check if post is too old
                    if since and created_at and created_at < since:
                        # Posts are in reverse chronological order, so we can stop
                        cursor = None
                        break
                    
                    # Get author info
                    author = post.get('author', {})
                    
                    posts.append({
                        'uri': uri,
                        'text': text.strip(),
                        'created_at': created_at,
                        'word_count': len(text.split()),
                        'source_did': author.get('did', ''),
                        'source_handle': author.get('handle', ''),
                        'source_display_name': author.get('displayName', ''),
                        'collection': 'app.bsky.feed.post',
                        'platform': 'bluesky',
                        'is_network': True,  # Flag to distinguish from Umbra's own content
                    })
                
                cursor = data.get('cursor')
                if not cursor:
                    break
                
                time.sleep(self.delay_between_requests)
                
            except requests.RequestException as e:
                logger.warning(f"Failed to fetch feed for {actor}: {e}")
                break
        
        return posts
    
    def scrape_network(
        self,
        max_accounts: Optional[int] = None,
        max_posts_per_account: int = 50,
        since_days: int = 7,
        include_followers: bool = False,
    ) -> dict:
        """
        Scrape content from the social network.
        
        Args:
            max_accounts: Maximum number of accounts to scrape (None = all)
            max_posts_per_account: Maximum posts per account
            since_days: Only fetch posts from the last N days
            include_followers: Also scrape from accounts that follow the source
            
        Returns:
            Dict with 'posts', 'accounts_scraped', 'total_posts', metadata
        """
        since = datetime.now(timezone.utc) - timedelta(days=since_days)
        
        # Get accounts to scrape
        accounts_to_scrape = []
        
        # Always include follows
        follows = self.get_follows(max_results=max_accounts)
        for f in follows:
            accounts_to_scrape.append({
                'did': f.get('did'),
                'handle': f.get('handle'),
                'display_name': f.get('displayName', ''),
                'relationship': 'follows',
            })
        
        # Optionally include followers
        if include_followers:
            remaining = (max_accounts - len(accounts_to_scrape)) if max_accounts else None
            if remaining is None or remaining > 0:
                followers = self.get_followers(max_results=remaining)
                for f in followers:
                    # Avoid duplicates
                    if not any(a['did'] == f.get('did') for a in accounts_to_scrape):
                        accounts_to_scrape.append({
                            'did': f.get('did'),
                            'handle': f.get('handle'),
                            'display_name': f.get('displayName', ''),
                            'relationship': 'follower',
                        })
        
        logger.info(f"Scraping content from {len(accounts_to_scrape)} accounts...")
        
        # Scrape posts from each account
        all_posts = []
        accounts_scraped = 0
        accounts_with_posts = 0
        
        for i, account in enumerate(accounts_to_scrape):
            did = account['did']
            handle = account['handle']
            
            logger.info(f"[{i+1}/{len(accounts_to_scrape)}] Scraping @{handle}...")
            
            try:
                posts = self.get_author_feed(
                    actor=did,
                    max_posts=max_posts_per_account,
                    since=since,
                )
                
                if posts:
                    all_posts.extend(posts)
                    accounts_with_posts += 1
                    logger.info(f"  Found {len(posts)} posts from @{handle}")
                else:
                    logger.debug(f"  No recent posts from @{handle}")
                
                accounts_scraped += 1
                
            except Exception as e:
                logger.warning(f"  Error scraping @{handle}: {e}")
            
            # Rate limiting between accounts
            if i < len(accounts_to_scrape) - 1:
                time.sleep(self.delay_between_accounts)
        
        # Sort by creation time (newest first)
        all_posts.sort(
            key=lambda p: p.get('created_at') or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        
        logger.info(f"Network scrape complete: {len(all_posts)} posts from {accounts_with_posts}/{accounts_scraped} accounts")
        
        return {
            'posts': all_posts,
            'accounts_scraped': accounts_scraped,
            'accounts_with_posts': accounts_with_posts,
            'total_posts': len(all_posts),
            'since': since.isoformat(),
            'source_did': self.source_did,
        }
    
    def get_network_stats(self) -> dict:
        """
        Get basic statistics about the social network.
        
        Returns:
            Dict with follower/following counts
        """
        follows = self.get_follows()
        followers = self.get_followers()
        
        return {
            'source_did': self.source_did,
            'following_count': len(follows),
            'follower_count': len(followers),
            'follows': [{'did': f.get('did'), 'handle': f.get('handle')} for f in follows],
            'followers_sample': [{'did': f.get('did'), 'handle': f.get('handle')} for f in followers[:20]],
        }


def scrape_umbra_network(
    max_accounts: int = 50,
    max_posts_per_account: int = 30,
    since_days: int = 7,
) -> dict:
    """
    Convenience function to scrape Umbra's network.
    
    Args:
        max_accounts: Maximum accounts to scrape
        max_posts_per_account: Maximum posts per account
        since_days: Look back N days
        
    Returns:
        Dict with posts and metadata
    """
    scraper = NetworkScraper()
    return scraper.scrape_network(
        max_accounts=max_accounts,
        max_posts_per_account=max_posts_per_account,
        since_days=since_days,
    )
