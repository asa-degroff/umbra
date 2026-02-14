"""
Relevance Service

Provides cached access to the RelevanceAnalyzer for the dashboard.
Handles centroid computation on startup and periodic refresh.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
import sys

# Add umbra to path for imports
sys.path.insert(0, '/home/asa/umbra')

logger = logging.getLogger(__name__)

# Global state
_analyzer = None
_last_refresh = None
_refresh_interval = 300  # 5 minutes
_cache = {
    'top_posts': None,
    'top_accounts': None,
    'trending_topics': None,
    'stats': None,
    'cache_time': None,
}
_cache_ttl = 60  # 1 minute cache for API responses


def _get_analyzer():
    """Get or create the relevance analyzer."""
    global _analyzer, _last_refresh
    
    if _analyzer is None:
        try:
            from semantic_analysis import SemanticStorage, EmbeddingGenerator, create_relevance_analyzer
            
            storage = SemanticStorage('/home/asa/umbra/data/chromadb')
            embedder = EmbeddingGenerator()
            _analyzer = create_relevance_analyzer(storage, embedder, use_default_negatives=True)
            
            # Compute initial centroid
            _analyzer.compute_umbra_centroid(days=30)
            _last_refresh = datetime.now(timezone.utc)
            
            logger.info("Relevance analyzer initialized with centroid")
        except Exception as e:
            logger.error(f"Failed to initialize relevance analyzer: {e}")
            return None
    
    return _analyzer


def _should_refresh() -> bool:
    """Check if centroid should be refreshed."""
    global _last_refresh
    
    if _last_refresh is None:
        return True
    
    elapsed = (datetime.now(timezone.utc) - _last_refresh).total_seconds()
    return elapsed > _refresh_interval


def _refresh_centroid():
    """Refresh the centroid if needed."""
    global _analyzer, _last_refresh
    
    if _analyzer and _should_refresh():
        try:
            _analyzer.compute_umbra_centroid(days=30)
            _last_refresh = datetime.now(timezone.utc)
            _invalidate_cache()
            logger.info("Refreshed relevance centroid")
        except Exception as e:
            logger.error(f"Failed to refresh centroid: {e}")


def _invalidate_cache():
    """Invalidate all cached data."""
    global _cache
    _cache = {
        'top_posts': None,
        'top_accounts': None,
        'trending_topics': None,
        'stats': None,
        'cache_time': None,
    }


def _cache_valid() -> bool:
    """Check if cache is still valid."""
    if _cache['cache_time'] is None:
        return False
    
    elapsed = (datetime.now(timezone.utc) - _cache['cache_time']).total_seconds()
    return elapsed < _cache_ttl


class RelevanceService:
    """Service for accessing relevance data with caching."""
    
    @property
    def is_available(self) -> bool:
        """Check if the relevance analyzer is available."""
        return _get_analyzer() is not None
    
    def initialize(self) -> bool:
        """Initialize the analyzer (call on startup)."""
        analyzer = _get_analyzer()
        return analyzer is not None
    
    def get_top_posts(
        self,
        days: int = 14,
        min_relevance: float = 0.5,
        limit: int = 20,
    ) -> dict:
        """
        Get top relevant posts from network.
        
        Returns:
            Dict with posts list and metadata
        """
        _refresh_centroid()
        
        # Check cache
        cache_key = f"top_posts_{days}_{min_relevance}_{limit}"
        if _cache_valid() and _cache.get('top_posts'):
            return _cache['top_posts']
        
        analyzer = _get_analyzer()
        if not analyzer:
            return {"posts": [], "error": "Analyzer not available"}
        
        try:
            posts = analyzer.analyze_network_content(
                days=days,
                min_relevance=min_relevance,
                limit=limit,
            )
            
            result = {
                "posts": [
                    {
                        "uri": p['uri'],
                        "text": p['text'],
                        "relevance_score": round(p['relevance_score'], 3),
                        "source_handle": p['source_handle'],
                        "created_at": p['metadata'].get('created_at'),
                    }
                    for p in posts
                ],
                "count": len(posts),
                "days": days,
                "min_relevance": min_relevance,
            }
            
            _cache['top_posts'] = result
            _cache['cache_time'] = datetime.now(timezone.utc)
            
            return result
        except Exception as e:
            logger.error(f"Error getting top posts: {e}")
            return {"posts": [], "error": str(e)}
    
    def get_top_accounts(
        self,
        days: int = 14,
        min_relevance: float = 0.5,
        limit: int = 15,
    ) -> dict:
        """
        Get accounts ranked by relevance.
        
        Returns:
            Dict with accounts list and metadata
        """
        _refresh_centroid()
        
        if _cache_valid() and _cache.get('top_accounts'):
            return _cache['top_accounts']
        
        analyzer = _get_analyzer()
        if not analyzer:
            return {"accounts": [], "error": "Analyzer not available"}
        
        try:
            by_account = analyzer.find_relevant_by_account(
                days=days,
                min_relevance=min_relevance,
            )
            
            accounts = []
            for handle, stats in list(by_account.items())[:limit]:
                accounts.append({
                    "handle": handle,
                    "post_count": stats['post_count'],
                    "avg_relevance": round(stats['avg_relevance'], 3),
                    "top_post": stats['top_posts'][0]['text'][:150] if stats['top_posts'] else None,
                })
            
            result = {
                "accounts": accounts,
                "count": len(accounts),
                "days": days,
            }
            
            _cache['top_accounts'] = result
            _cache['cache_time'] = datetime.now(timezone.utc)
            
            return result
        except Exception as e:
            logger.error(f"Error getting top accounts: {e}")
            return {"accounts": [], "error": str(e)}
    
    def get_trending_topics(
        self,
        days: int = 14,
        min_relevance: float = 0.5,
        min_posts: int = 2,
    ) -> dict:
        """
        Get trending topics from network.
        
        Returns:
            Dict with topics list and metadata
        """
        _refresh_centroid()
        
        if _cache_valid() and _cache.get('trending_topics'):
            return _cache['trending_topics']
        
        analyzer = _get_analyzer()
        if not analyzer:
            return {"topics": [], "error": "Analyzer not available"}
        
        try:
            topics = analyzer.find_trending_topics(
                days=days,
                min_relevance=min_relevance,
                min_posts=min_posts,
            )
            
            result = {
                "topics": [
                    {
                        "post_count": t['post_count'],
                        "avg_relevance": round(t['avg_relevance'], 3),
                        "contributors": t['handles'][:5],
                        "sample_text": t['representative_posts'][0]['text'][:200] if t['representative_posts'] else None,
                    }
                    for t in topics[:10]
                ],
                "count": len(topics),
                "days": days,
            }
            
            _cache['trending_topics'] = result
            _cache['cache_time'] = datetime.now(timezone.utc)
            
            return result
        except Exception as e:
            logger.error(f"Error getting trending topics: {e}")
            return {"topics": [], "error": str(e)}
    
    def get_stats(self) -> dict:
        """Get relevance analyzer stats."""
        analyzer = _get_analyzer()
        if not analyzer:
            return {"error": "Analyzer not available"}
        
        stats = analyzer.get_stats()
        stats['last_refresh'] = _last_refresh.isoformat() if _last_refresh else None
        stats['refresh_interval'] = _refresh_interval
        
        return stats


# Global service instance
relevance_service = RelevanceService()
