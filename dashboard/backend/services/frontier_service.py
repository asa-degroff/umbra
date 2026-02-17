"""
Frontier Service

Provides cached access to frontier detection and source discovery.
"""

import asyncio
import logging
import threading
import time
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
_seed_detector = None
_last_detection = None
_detection_interval = 600  # 10 minutes

_cache = {
    'zones': None,
    'zones_time': None,
    'seeds': None,
    'seeds_time': None,
    'seed_objects': None,  # Raw InterestSeed list, separate from API-facing cache
    'discovery_result': None,
    'discovery_time': None,
}
_cache_ttl = 300  # 5 minutes
_init_lock = threading.Lock()
_discovery_lock = threading.Lock()
_discovery_running = False
_init_started = False
_init_done = threading.Event()


def start_background_init():
    """Start component initialization in a background thread so the server stays responsive."""
    global _init_started
    if _init_started:
        return
    _init_started = True

    def _bg():
        try:
            _init_components()
        except Exception as e:
            logger.error(f"Background init failed: {e}", exc_info=True)
        finally:
            _init_done.set()

    thread = threading.Thread(target=_bg, daemon=True)
    thread.start()
    logger.info("Frontier service background initialization started")


def _init_components():
    """Initialize frontier detection components."""
    global _frontier_detector, _source_discovery, _relevance_analyzer, _source_db, _seed_detector

    if _frontier_detector is not None:
        return True

    with _init_lock:
        # Double-check after acquiring lock (another thread may have initialized)
        if _frontier_detector is not None:
            return True

        try:
            from semantic_analysis import (
                EmbeddingGenerator,
                create_relevance_analyzer,
                create_frontier_detector,
                create_source_discovery,
                SourceDB,
            )
            from semantic_analysis.seeds import create_interest_seed_detector
            from dashboard.backend.services.shared_storage import get_shared_storage

            logger.info("Init: getting shared storage...")
            storage = get_shared_storage()
            if storage is None:
                logger.error("Shared storage not available")
                return False
            logger.info("Init: creating embedder...")
            embedder = EmbeddingGenerator()

            logger.info("Init: creating relevance analyzer...")
            _relevance_analyzer = create_relevance_analyzer(storage, embedder, use_default_negatives=True)
            logger.info("Init: computing umbra centroid...")
            _relevance_analyzer.compute_umbra_centroid(days=30)
            logger.info("Init: centroid done, creating frontier detector...")

            _frontier_detector = create_frontier_detector(storage, relevance_analyzer=_relevance_analyzer)

            logger.info("Init: creating seed detector...")
            _seed_detector = create_interest_seed_detector(storage)

            _source_db = SourceDB('/home/asa/umbra/data/source_discovery.db')

            _source_discovery = create_source_discovery(
                storage=storage,
                embedder=embedder,
                frontier_detector=_frontier_detector,
                relevance_analyzer=_relevance_analyzer,
                source_db=_source_db,
            )

            # Apply any existing user feedback
            _apply_feedback()

            logger.info("Frontier service components initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize frontier components: {e}")
            return False


def _apply_feedback():
    """Load user-rated sources and feed them into the relevance analyzer."""
    if _source_db is None or _relevance_analyzer is None:
        return

    try:
        import numpy as np

        downranked = _source_db.get_rated_sources(rating=-1)
        upranked = _source_db.get_rated_sources(rating=1)

        # Filter to matching embedding dimension (old sources may have stale dims)
        expected_dim = _relevance_analyzer._umbra_centroid.shape[0] if _relevance_analyzer._umbra_centroid is not None else None

        neg_embeddings = []
        pos_embeddings = []
        skipped = 0
        for s in downranked:
            if s.embedding:
                arr = np.array(s.embedding)
                if expected_dim is None or arr.shape[0] == expected_dim:
                    neg_embeddings.append(arr)
                else:
                    skipped += 1
        for s in upranked:
            if s.embedding:
                arr = np.array(s.embedding)
                if expected_dim is None or arr.shape[0] == expected_dim:
                    pos_embeddings.append(arr)
                else:
                    skipped += 1

        if skipped:
            logger.warning(f"Skipped {skipped} feedback sources with stale embedding dimension")

        if neg_embeddings or pos_embeddings:
            _relevance_analyzer.add_feedback_exemplars(neg_embeddings, pos_embeddings)
            logger.info(
                f"Applied user feedback: {len(neg_embeddings)} negative, "
                f"{len(pos_embeddings)} positive exemplars"
            )
    except Exception as e:
        logger.error(f"Error applying feedback: {e}")


def _ensure_ready() -> bool:
    """Non-blocking check if components are initialized. Starts background init if needed."""
    if _frontier_detector is not None:
        return True
    start_background_init()
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
        """Check if service is available (non-blocking)."""
        if _frontier_detector is not None:
            return True
        # Kick off background init if not started
        start_background_init()
        return False
    
    def get_seeds(
        self,
        days: int = 30,
        force_refresh: bool = False,
    ) -> dict:
        """
        Get detected interest seeds.

        Args:
            days: Lookback period
            force_refresh: Skip cache

        Returns:
            Dict with seeds list and metadata
        """
        if not _ensure_ready() or _seed_detector is None:
            return {"seeds": [], "error": "Service initializing, please wait..."}

        cache_key = f"seeds_{days}"

        if not force_refresh and _cache_valid('seeds'):
            cached = _cache.get('seeds')
            if cached and cached.get('cache_key') == cache_key:
                return cached

        try:
            seeds = _seed_detector.detect_seeds(days=days, label_seeds=True)

            result = {
                "seeds": [
                    {
                        "seed_id": s.seed_id,
                        "seed_type": s.seed_type,
                        "label": s.label,
                        "post_count": s.post_count,
                        "weight": round(s.weight, 3),
                        "recency_weight": round(s.recency_weight, 3),
                        "rarity_weight": round(s.rarity_weight, 3),
                        "avg_distance_to_global_centroid": round(s.avg_distance_to_global_centroid, 3),
                        "representative_texts": [t[:200] for t in s.representative_texts[:3]],
                    }
                    for s in seeds
                ],
                "count": len(seeds),
                "cluster_count": sum(1 for s in seeds if s.seed_type == "cluster"),
                "outlier_count": sum(1 for s in seeds if s.seed_type == "outlier"),
                "days": days,
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "cache_key": cache_key,
            }

            _cache['seeds'] = result
            _cache['seeds_time'] = datetime.now(timezone.utc)
            _cache['seed_objects'] = seeds

            return result

        except Exception as e:
            logger.error(f"Error detecting seeds: {e}")
            return {"seeds": [], "error": str(e)}

    def get_zones(
        self,
        days: int = 30,
        top_n: int = 10,
        source: str = 'all',
        use_seeds: bool = True,
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
        if not _ensure_ready():
            return {"zones": [], "error": "Service initializing, please wait..."}
        
        cache_key = f"zones_{days}_{top_n}_{source}_{use_seeds}"
        
        if not force_refresh and _cache_valid('zones'):
            cached = _cache.get('zones')
            if cached and cached.get('cache_key') == cache_key:
                return cached

        # Get seeds if enabled
        seed_objects = None
        if use_seeds and _seed_detector is not None:
            try:
                self.get_seeds(days=days)  # Populates cache
                seed_objects = _cache.get('seed_objects')
            except Exception as e:
                logger.warning(f"Seed detection failed, falling back to unseeded: {e}")

        try:
            # Retry up to 3 times on transient ChromaDB errors
            last_err = None
            for attempt in range(3):
                try:
                    zones = _frontier_detector.detect_frontiers(
                        days=days,
                        top_n=top_n,
                        source=source,
                        seeds=seed_objects,
                    )
                    break
                except Exception as e:
                    last_err = e
                    err_str = str(e)
                    # Retry on ChromaDB contention / InsufficientDataError from 0 embeddings
                    if "got 0" in err_str or "Error finding id" in err_str:
                        logger.warning(f"Frontier detection attempt {attempt + 1}/3 failed (transient): {e}")
                        time.sleep(1 + attempt)
                        continue
                    raise  # Non-transient error, don't retry
            else:
                # All retries exhausted — serve stale cache if available
                if _cache.get('zones') is not None:
                    logger.warning("All retries failed, serving stale cached zones")
                    return _cache['zones']
                raise last_err

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
                        "seed_id": z.seed_id,
                        "seed_label": z.seed_label,
                        "nearby_posts": [
                            {
                                "text": p.get('text', ''),
                                "uri": p.get('uri', ''),
                            }
                            for p in z.nearby_posts[:3]
                        ],
                    }
                    for z in zones
                ],
                "count": len(zones),
                "seeded": seed_objects is not None,
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
    
    @staticmethod
    def _format_discovery_result(result) -> dict:
        """Format a DiscoveryResult into the API response dict."""
        return {
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
            "status": "complete",
        }

    def discover_sources_focused(
        self,
        seed_ids: list[str],
        max_rounds: int = 2,
        max_sources_per_zone: int = 5,
        max_total_sources: int = 25,
        initial_zones: int = 3,
        days: int = 30,
        source: str = 'all',
    ) -> dict:
        """
        Run source discovery focused on specific seeds.

        Filters the full seed list to only the requested seed_ids,
        then passes those to discover(). Results are NOT cached
        (focused results are query-specific).

        Args:
            seed_ids: List of seed_id strings to focus on
            max_rounds: Maximum expansion rounds
            max_sources_per_zone: Sources per zone
            max_total_sources: Total source cap
            initial_zones: Starting zones
            days: Lookback period
            source: Content filter

        Returns:
            Dict with discovery results plus focused_seeds metadata
        """
        if not _ensure_ready():
            return {"error": "Service initializing, please wait..."}

        if not seed_ids:
            return {"error": "No seed_ids provided"}

        # Get seed objects from cache or detect fresh
        seed_objects = _cache.get('seed_objects')
        if seed_objects is None and _seed_detector is not None:
            try:
                self.get_seeds(days=days)
                seed_objects = _cache.get('seed_objects')
            except Exception as e:
                logger.warning(f"Seed detection for focused discovery failed: {e}")

        if not seed_objects:
            return {"error": "No seeds available — run seed detection first"}

        # Filter to only the requested seeds
        seed_id_set = set(seed_ids)
        filtered_seeds = [s for s in seed_objects if s.seed_id in seed_id_set]

        if not filtered_seeds:
            return {"error": f"None of the requested seed_ids were found in detected seeds"}

        matched_labels = [s.label for s in filtered_seeds]
        logger.info(f"Running focused discovery on {len(filtered_seeds)} seeds: {matched_labels}")

        _apply_feedback()
        try:
            # Attach event emitter for live WebSocket broadcasting
            emitter = None
            try:
                from dashboard.backend.websocket import ws_manager
                from dashboard.backend.services.discovery_emitter import DiscoveryEventEmitter
                emitter = DiscoveryEventEmitter(ws_manager)
            except Exception:
                pass

            result = _source_discovery.discover(
                seeds=filtered_seeds,
                max_rounds=max_rounds,
                max_sources_per_zone=max_sources_per_zone,
                max_total_sources=max_total_sources,
                initial_zones=initial_zones,
                days=days,
                source=source,
                event_emitter=emitter,
            )
            response = self._format_discovery_result(result)
            response['focused'] = True
            response['focused_seeds'] = matched_labels
            return response
        except Exception as e:
            logger.error(f"Error in focused source discovery: {e}")
            return {"error": str(e), "status": "error"}

    def discover_sources(
        self,
        max_rounds: int = 2,
        max_sources_per_zone: int = 5,
        max_total_sources: int = 25,
        initial_zones: int = 3,
        days: int = 30,
        source: str = 'all',
        force_refresh: bool = False,
        background: bool = False,
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
            background: If True, run in a background thread and return immediately

        Returns:
            Dict with discovery results, or status dict if background=True
        """
        global _discovery_running

        if not _ensure_ready():
            return {"error": "Service initializing, please wait..."}

        if not force_refresh and _cache_valid('discovery_result'):
            return _cache['discovery_result']

        # If already running, report status
        if _discovery_running:
            return {
                "status": "in_progress",
                "message": "Discovery is already running in the background",
            }

        kwargs = dict(
            max_rounds=max_rounds,
            max_sources_per_zone=max_sources_per_zone,
            max_total_sources=max_total_sources,
            initial_zones=initial_zones,
            days=days,
            source=source,
        )

        if background:
            thread = threading.Thread(
                target=self._run_discovery_background,
                kwargs=kwargs,
                daemon=True,
            )
            thread.start()
            return {
                "status": "started",
                "message": "Discovery started in background. Poll this endpoint to get results.",
            }

        # Synchronous path (backwards-compatible)
        return self._run_discovery(**kwargs)

    def _run_discovery(self, **kwargs) -> dict:
        """Execute discovery synchronously and cache the result."""
        _apply_feedback()
        try:
            # Attach event emitter for live WebSocket broadcasting
            try:
                from dashboard.backend.websocket import ws_manager
                from dashboard.backend.services.discovery_emitter import DiscoveryEventEmitter
                kwargs['event_emitter'] = DiscoveryEventEmitter(ws_manager)
            except Exception as e:
                logger.debug(f"Could not attach event emitter: {e}")

            # Detect seeds and pass to discovery for seed-aware exploration
            seed_objects = _cache.get('seed_objects')
            if seed_objects is None and _seed_detector is not None:
                try:
                    days = kwargs.get('days', 30)
                    self.get_seeds(days=days)  # Populates _cache['seed_objects']
                    seed_objects = _cache.get('seed_objects')
                except Exception as e:
                    logger.warning(f"Seed detection for discovery failed: {e}")

            if seed_objects:
                kwargs['seeds'] = seed_objects
                logger.info(f"Passing {len(seed_objects)} seeds to discovery")

            result = _source_discovery.discover(**kwargs)
            response = self._format_discovery_result(result)
            _cache['discovery_result'] = response
            _cache['discovery_time'] = datetime.now(timezone.utc)
            return response
        except Exception as e:
            logger.error(f"Error in source discovery: {e}")
            return {"error": str(e), "status": "error"}

    def _run_discovery_background(self, **kwargs):
        """Execute discovery in a background thread."""
        global _discovery_running
        with _discovery_lock:
            _discovery_running = True
        try:
            self._run_discovery(**kwargs)
        finally:
            with _discovery_lock:
                _discovery_running = False
    
    def rate_source(self, source_id: int, rating: int) -> dict:
        """Rate a source and apply feedback to the relevance analyzer."""
        if not _ensure_ready() or _source_db is None:
            raise RuntimeError("Service initializing, please wait...")

        updated = _source_db.rate_source(source_id, rating)
        if not updated:
            raise ValueError(f"Source {source_id} not found")

        # Re-apply all feedback so the analyzer stays up-to-date
        _apply_feedback()

        # Fetch updated source to return current status
        rows = _source_db.conn.execute(
            "SELECT status FROM discovered_sources WHERE id = ?", (source_id,)
        ).fetchone()
        status = rows['status'] if rows else 'unknown'

        return {
            "success": True,
            "source_id": source_id,
            "rating": rating,
            "status": status,
        }

    def evaluate_pending(self, threshold: float = 0.4) -> dict:
        """
        Re-evaluate pending sources against current Umbra content.

        Loads all pending sources from the DB, re-scores them with a fresh
        centroid, promotes those above threshold to 'frontier', and persists
        the updates.

        Returns:
            Dict with promoted count and updated source IDs.
        """
        if not _ensure_ready() or _source_db is None or _source_discovery is None:
            return {"error": "Service initializing, please wait..."}

        try:
            pending = _source_db.get_sources(status='pending', limit=1000)
            if not pending:
                return {"promoted": 0, "still_pending": 0, "message": "No pending sources"}

            _apply_feedback()

            promoted, still_pending = _source_discovery.evaluate_pending_sources(
                pending, threshold=threshold
            )

            # Persist status + score changes
            promoted_ids = []
            for s in promoted:
                if s.id is not None:
                    _source_db.update_source(s.id, 'frontier', s.relevance_score)
                    promoted_ids.append(s.id)

            for s in still_pending:
                if s.id is not None:
                    _source_db.update_source(s.id, 'pending', s.relevance_score)

            logger.info(f"Evaluated {len(pending)} pending sources: "
                       f"{len(promoted)} promoted to frontier")

            return {
                "promoted": len(promoted),
                "still_pending": len(still_pending),
                "promoted_ids": promoted_ids,
                "threshold": threshold,
            }

        except Exception as e:
            logger.error(f"Error evaluating pending sources: {e}")
            return {"error": str(e)}

    def get_persisted_sources(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Get sources from the persistence DB (not just cache)."""
        if not _ensure_ready() or _source_db is None:
            return {"sources": [], "error": "Service initializing, please wait..."}

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
                        "user_rating": s.user_rating,
                        "rated_at": s.rated_at.isoformat() if s.rated_at else None,
                    }
                    for s in sources
                ],
                "count": len(sources),
            }
        except Exception as e:
            logger.error(f"Error getting persisted sources: {e}")
            return {"sources": [], "error": str(e)}

    def cleanup_sources(self, max_age_days: int = 90) -> dict:
        """Delete old sources from the DB, preserving user-rated ones."""
        if not _ensure_ready() or _source_db is None:
            return {"error": "Service initializing, please wait..."}
        try:
            deleted = _source_db.cleanup_old(max_age_days=max_age_days, protect_rated=True)
            return {"deleted": deleted, "max_age_days": max_age_days}
        except Exception as e:
            logger.error(f"Error cleaning up sources: {e}")
            return {"error": str(e)}

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
