"""
Frontier Service

Provides cached access to frontier detection and source discovery.
"""

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Optional
import sys

sys.path.insert(0, '/home/asa/umbra')

logger = logging.getLogger(__name__)

# Global state
_frontier_detector = None
_source_discovery = None
_relevance_analyzer = None
_source_db = None
_last_detection = None
_detection_interval = 600  # 10 minutes

_cache = {
    'zones': None,
    'zones_time': None,
    'discovery_result': None,
    'discovery_time': None,
}
_cache_ttl = 300  # 5 minutes
_init_lock = threading.Lock()


def _init_components():
    """Initialize frontier detection components."""
    global _frontier_detector, _source_discovery, _relevance_analyzer, _source_db

    if _frontier_detector is not None:
        return True

    with _init_lock:
        # Double-check after acquiring lock (another thread may have initialized)
        if _frontier_detector is not None:
            return True

        try:
            from semantic_analysis import (
                SemanticStorage,
                EmbeddingGenerator,
                create_relevance_analyzer,
                create_frontier_detector,
                create_source_discovery,
                SourceDB,
            )

            storage = SemanticStorage('/home/asa/umbra/data/chromadb')
            embedder = EmbeddingGenerator()

            _relevance_analyzer = create_relevance_analyzer(storage, embedder, use_default_negatives=True)
            _relevance_analyzer.compute_umbra_centroid(days=30)

            _frontier_detector = create_frontier_detector(storage, relevance_analyzer=_relevance_analyzer)

            _source_db = SourceDB('/home/asa/umbra/data/source_discovery.db')

            _source_discovery = create_source_discovery(
                storage=storage,
                embedder=embedder,
                frontier_detector=_frontier_detector,
                relevance_analyzer=_relevance_analyzer,
                source_db=_source_db,
            )

            logger.info("Frontier service components initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize frontier components: {e}")
            return False


def _cache_valid(key: str) -> bool:
    """Check if cache entry is valid."""
    time_key = f"{key}_time"
    if _cache.get(time_key) is None:
        return False
    
    elapsed = (datetime.now(timezone.utc) - _cache[time_key]).total_seconds()
    return elapsed < _cache_ttl


class FrontierService:
    """Service for frontier detection and source discovery."""
    
    @property
    def is_available(self) -> bool:
        """Check if service is available."""
        return _init_components()
    
    def get_zones(
        self,
        days: int = 30,
        top_n: int = 10,
        source: str = 'all',
        force_refresh: bool = False,
    ) -> dict:
        """
        Get frontier zones.
        
        Args:
            days: Lookback period
            top_n: Number of zones to return
            source: Content filter ('umbra', 'network', 'all')
            force_refresh: Skip cache
            
        Returns:
            Dict with zones list and metadata
        """
        if not _init_components():
            return {"zones": [], "error": "Service not available"}
        
        cache_key = f"zones_{days}_{top_n}_{source}"
        
        if not force_refresh and _cache_valid('zones'):
            cached = _cache.get('zones')
            if cached and cached.get('cache_key') == cache_key:
                return cached
        
        try:
            zones = _frontier_detector.detect_frontiers(
                days=days,
                top_n=top_n,
                source=source,
            )
            
            result = {
                "zones": [
                    {
                        "id": f"{z.grid_cell[0]}_{z.grid_cell[1]}",
                        "grid_cell": z.grid_cell,
                        "centroid_2d": z.centroid_2d,
                        "frontier_score": round(z.frontier_score, 3),
                        "density_score": round(z.density_score, 3),
                        "adjacency_score": round(z.adjacency_score, 3),
                        "relevance_score": round(z.relevance_score, 3),
                        "nearby_posts": [
                            {
                                "text": p.get('text', '')[:200],
                                "uri": p.get('uri', ''),
                            }
                            for p in z.nearby_posts[:3]
                        ],
                    }
                    for z in zones
                ],
                "count": len(zones),
                "days": days,
                "source": source,
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "cache_key": cache_key,
            }
            
            _cache['zones'] = result
            _cache['zones_time'] = datetime.now(timezone.utc)
            
            return result
            
        except Exception as e:
            logger.error(f"Error detecting frontiers: {e}")
            return {"zones": [], "error": str(e)}
    
    def discover_sources(
        self,
        max_rounds: int = 2,
        max_sources_per_zone: int = 5,
        max_total_sources: int = 25,
        initial_zones: int = 3,
        days: int = 30,
        source: str = 'all',
        force_refresh: bool = False,
    ) -> dict:
        """
        Run source discovery.
        
        Args:
            max_rounds: Maximum expansion rounds
            max_sources_per_zone: Sources per zone
            max_total_sources: Total source cap
            initial_zones: Starting zones
            days: Lookback period
            source: Content filter
            force_refresh: Skip cache
            
        Returns:
            Dict with discovery results
        """
        if not _init_components():
            return {"error": "Service not available"}
        
        if not force_refresh and _cache_valid('discovery_result'):
            return _cache['discovery_result']
        
        try:
            result = _source_discovery.discover(
                max_rounds=max_rounds,
                max_sources_per_zone=max_sources_per_zone,
                max_total_sources=max_total_sources,
                initial_zones=initial_zones,
                days=days,
                source=source,
            )
            
            response = {
                "frontier_sources": [
                    {
                        "title": s.title,
                        "url": s.url,
                        "excerpt": s.excerpt[:300],
                        "source_type": s.source_type,
                        "relevance_score": round(s.relevance_score, 3),
                        "query_used": s.query_used,
                        "status": s.status,
                    }
                    for s in result.frontier_sources
                ],
                "pending_sources": [
                    {
                        "title": s.title,
                        "url": s.url,
                        "excerpt": s.excerpt[:300],
                        "source_type": s.source_type,
                        "relevance_score": round(s.relevance_score, 3),
                        "query_used": s.query_used,
                        "status": s.status,
                    }
                    for s in result.pending_sources
                ],
                "stats": {
                    "zones_explored": result.zones_explored,
                    "rounds_completed": result.rounds_completed,
                    "total_sources_found": result.total_sources_found,
                    "capped": result.capped,
                },
                "errors": result.errors,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
            
            _cache['discovery_result'] = response
            _cache['discovery_time'] = datetime.now(timezone.utc)
            
            return response
            
        except Exception as e:
            logger.error(f"Error in source discovery: {e}")
            return {"error": str(e)}
    
    def get_persisted_sources(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Get sources from the persistence DB (not just cache)."""
        if not _init_components() or _source_db is None:
            return {"sources": [], "error": "Service not available"}

        try:
            sources = _source_db.get_sources(status=status, limit=limit, offset=offset)
            return {
                "sources": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "url": s.url,
                        "excerpt": s.excerpt[:300],
                        "source_type": s.source_type,
                        "relevance_score": round(s.relevance_score, 3),
                        "status": s.status,
                        "frontier_zone_id": s.frontier_zone_id,
                        "query_used": s.query_used,
                        "discovered_at": s.discovered_at.isoformat(),
                        "chunk_index": s.chunk_index,
                        "total_chunks": s.total_chunks,
                    }
                    for s in sources
                ],
                "count": len(sources),
            }
        except Exception as e:
            logger.error(f"Error getting persisted sources: {e}")
            return {"sources": [], "error": str(e)}

    def get_stats(self) -> dict:
        """Get frontier service stats."""
        stats = {
            "available": _frontier_detector is not None,
            "zones_cached": _cache.get('zones') is not None,
            "discovery_cached": _cache.get('discovery_result') is not None,
            "cache_ttl": _cache_ttl,
            "detection_interval": _detection_interval,
        }
        if _source_db is not None:
            try:
                stats["source_db"] = _source_db.get_stats()
            except Exception as e:
                stats["source_db_error"] = str(e)
        return stats


# Global service instance
frontier_service = FrontierService()
