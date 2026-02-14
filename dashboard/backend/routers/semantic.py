"""
Semantic Analysis API Router

Endpoints for semantic diversity analysis data.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from dashboard.backend.services.chromadb_service import ChromaDBService
from config_loader import get_config

logger = logging.getLogger('dashboard.api.semantic')

router = APIRouter()

# Initialize service
chromadb_service = ChromaDBService("./data/chromadb")


@router.get("/stats")
async def get_stats():
    """Get semantic database statistics."""
    return chromadb_service.get_stats()


@router.get("/records")
async def get_records(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    platform: Optional[str] = None,
    collection: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = Query(None, pattern="^(umbra|network|all)$"),
):
    """
    Get semantic records with pagination and filtering.
    
    Args:
        limit: Max records to return
        offset: Pagination offset
        platform: Filter by platform (bluesky, comind, etc.)
        collection: Filter by AT Protocol collection
        search: Full-text search in document text
        start_date: Filter records after this date (ISO format)
        end_date: Filter records before this date (ISO format)
        source: Filter by source - "umbra" (own content), "network" (followed accounts), or "all"
    """
    return chromadb_service.get_records_filtered(
        limit=limit,
        offset=offset,
        platform=platform,
        collection=collection,
        search=search,
        start_date=start_date,
        end_date=end_date,
        source=source,
    )


@router.get("/embeddings")
async def get_embeddings(
    limit: int = Query(500, ge=1, le=2000),
):
    """Get embeddings for visualization."""
    return chromadb_service.get_embeddings_for_visualization(limit=limit)


# Cache for 2D projections (in-memory)
_embeddings_2d_cache: dict = {}
_embeddings_2d_lock = asyncio.Lock()


@router.get("/embeddings/2d")
async def get_embeddings_2d(
    limit: int = Query(1000, ge=1, le=5000),
    method: str = Query("umap", pattern="^(umap|pca)$"),
):
    """
    Get 2D-projected embeddings for scatter plot visualization.
    
    Uses UMAP or PCA to reduce high-dimensional embeddings to 2D.
    Results are cached until new records are added.
    """
    import hashlib
    import numpy as np
    
    try:
        # Get raw embeddings
        raw_data = chromadb_service.get_embeddings_for_visualization(limit=limit)
        if raw_data.get("error"):
            return raw_data
        
        data = raw_data.get("data", [])
        if not data:
            return {"points": [], "method": method, "total": 0}
        
        # Filter out records without embeddings
        valid_data = [d for d in data if d.get("embedding") is not None and len(d.get("embedding", [])) > 0]
        if not valid_data:
            return {"points": [], "method": method, "total": 0, "error": "No embeddings found"}
        
        # Create cache key based on URIs and method
        uri_hash = hashlib.md5(
            (method + "".join(sorted(d["uri"] for d in valid_data))).encode()
        ).hexdigest()[:16]
        
        # Check cache
        async with _embeddings_2d_lock:
            if uri_hash in _embeddings_2d_cache:
                logger.info(f"Using cached 2D embeddings ({method})")
                return _embeddings_2d_cache[uri_hash]

        # Extract embeddings matrix
        embeddings = np.array([d["embedding"] for d in valid_data])
        logger.info(f"Reducing {len(embeddings)} embeddings to 2D using {method}...")

        # Reduce dimensionality
        if method == "umap":
            import umap
            reducer = umap.UMAP(
                n_components=2,
                n_neighbors=min(15, len(embeddings) - 1),
                min_dist=0.1,
                metric="cosine",
                random_state=42,
            )
            coords_2d = reducer.fit_transform(embeddings)
        else:  # PCA
            from sklearn.decomposition import PCA
            reducer = PCA(n_components=2, random_state=42)
            coords_2d = reducer.fit_transform(embeddings)

        # Build response
        points = []
        for i, d in enumerate(valid_data):
            full_text = d.get("text", "") or ""
            points.append({
                "x": float(coords_2d[i, 0]),
                "y": float(coords_2d[i, 1]),
                "uri": d["uri"],
                "platform": d.get("platform", "unknown"),
                "text_preview": full_text[:200] + ("..." if len(full_text) > 200 else ""),
                "text": full_text,  # Full text for detail view
                "created_at": d.get("created_at"),
            })

        result = {
            "points": points,
            "method": method,
            "total": len(points),
        }

        # Cache result
        async with _embeddings_2d_lock:
            _embeddings_2d_cache[uri_hash] = result
        logger.info(f"Cached 2D embeddings: {len(points)} points")

        return result
        
    except Exception as e:
        logger.error(f"Error computing 2D embeddings: {e}")
        return {"points": [], "method": method, "total": 0, "error": str(e)}


@router.get("/metrics")
async def get_metrics():
    """Get current diversity metrics using ANN-based computation."""
    try:
        from semantic_analysis.analyzer import DiversityAnalyzer
        from semantic_analysis.storage import SemanticStorage
        
        storage = SemanticStorage("./data/chromadb")
        analyzer = DiversityAnalyzer(storage=storage)  # Pass storage for ANN
        
        recent = storage.get_recent(days=7)
        if not recent:
            return {"error": "No recent records found"}
        
        # Use ANN-based metrics for efficiency
        metrics = analyzer.calculate_metrics_ann(recent)
        return metrics
    except Exception as e:
        logger.error(f"Error calculating metrics: {e}")
        return {"error": str(e)}


@router.get("/guidance")
async def get_guidance():
    """Get latest diversity guidance."""
    try:
        from semantic_analysis.analyzer import DiversityAnalyzer
        from semantic_analysis.storage import SemanticStorage
        
        storage = SemanticStorage("./data/chromadb")
        analyzer = DiversityAnalyzer()
        
        recent = storage.get_recent(days=7)
        if not recent:
            return {"guidance": "No recent records to analyze."}
        
        metrics = analyzer.calculate_metrics(recent)
        guidance = analyzer.generate_guidance(metrics)
        
        return {
            "guidance": guidance,
            "summary": analyzer.format_summary(metrics),
            "metrics": {
                "diversity": metrics.get("weighted_avg_diversity"),
                "cluster_dominance": metrics.get("cluster_dominance"),
                "records_analyzed": metrics.get("records_with_embeddings"),
            }
        }
    except Exception as e:
        logger.error(f"Error generating guidance: {e}")
        return {"error": str(e)}


@router.post("/analyze")
async def trigger_analysis():
    """Trigger semantic analysis on-demand."""
    try:
        from semantic_analysis import run_analysis
        
        config = get_config()
        umbra_did = config.get('semantic_analysis.umbra_did', 'did:plc:oetfdqwocv4aegq2yj6ix4w5')
        result = run_analysis(
            pds_host="https://bsky.social",
            did=umbra_did,
            access_token=None,
            chromadb_path="./data/chromadb",
            lookback_days=7,
            dry_run=True,
        )
        
        return result
    except Exception as e:
        logger.error(f"Error running analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Relevance Analysis Endpoints
# ============================================================================

@router.get("/relevance/top")
async def get_relevance_top(
    days: int = Query(14, ge=1, le=90),
    min_relevance: float = Query(0.5, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get top relevant posts from network content.
    
    Returns posts from followed accounts ranked by relevance to Umbra's interests.
    """
    try:
        from dashboard.backend.services.relevance_service import relevance_service
        return relevance_service.get_top_posts(days=days, min_relevance=min_relevance, limit=limit)
    except Exception as e:
        logger.error(f"Error getting relevance top: {e}")
        return {"posts": [], "error": str(e)}


@router.get("/relevance/accounts")
async def get_relevance_accounts(
    days: int = Query(14, ge=1, le=90),
    min_relevance: float = Query(0.5, ge=0.0, le=1.0),
    limit: int = Query(15, ge=1, le=50),
):
    """
    Get accounts ranked by relevance to Umbra's interests.
    
    Shows which followed accounts share the most relevant content.
    """
    try:
        from dashboard.backend.services.relevance_service import relevance_service
        return relevance_service.get_top_accounts(days=days, min_relevance=min_relevance, limit=limit)
    except Exception as e:
        logger.error(f"Error getting relevance accounts: {e}")
        return {"accounts": [], "error": str(e)}


@router.get("/relevance/trending")
async def get_relevance_trending(
    days: int = Query(14, ge=1, le=90),
    min_relevance: float = Query(0.5, ge=0.0, le=1.0),
    min_posts: int = Query(2, ge=2, le=10),
):
    """
    Get trending topics from network that are relevant to Umbra.
    
    Clusters similar posts to identify common themes.
    """
    try:
        from dashboard.backend.services.relevance_service import relevance_service
        return relevance_service.get_trending_topics(days=days, min_relevance=min_relevance, min_posts=min_posts)
    except Exception as e:
        logger.error(f"Error getting trending topics: {e}")
        return {"topics": [], "error": str(e)}


@router.get("/relevance/stats")
async def get_relevance_stats():
    """Get relevance analyzer statistics."""
    try:
        from dashboard.backend.services.relevance_service import relevance_service
        return relevance_service.get_stats()
    except Exception as e:
        logger.error(f"Error getting relevance stats: {e}")
        return {"error": str(e)}


# ============================================================================
# Frontier Detection Endpoints
# ============================================================================

@router.get("/frontier/zones")
async def get_frontier_zones(
    days: int = Query(30, ge=7, le=90),
    top_n: int = Query(10, ge=1, le=20),
    source: str = Query("all", pattern="^(umbra|network|all)$"),
    refresh: bool = Query(False),
):
    """
    Get detected frontier zones.
    
    Frontier zones are unexplored regions in embedding space
    adjacent to existing content clusters.
    """
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        return frontier_service.get_zones(
            days=days,
            top_n=top_n,
            source=source,
            force_refresh=refresh,
        )
    except Exception as e:
        logger.error(f"Error getting frontier zones: {e}")
        return {"zones": [], "error": str(e)}


@router.get("/frontier/discover")
async def discover_sources(
    max_rounds: int = Query(2, ge=1, le=5),
    max_sources: int = Query(25, ge=5, le=100),
    initial_zones: int = Query(3, ge=1, le=10),
    days: int = Query(30, ge=7, le=90),
    source: str = Query("all", pattern="^(umbra|network|all)$"),
    refresh: bool = Query(False),
):
    """
    Run source discovery to find external content in frontier zones.
    
    Searches Wikipedia for content that falls within detected frontiers.
    Note: This can take 30-60 seconds on first run.
    """
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        return frontier_service.discover_sources(
            max_rounds=max_rounds,
            max_total_sources=max_sources,
            initial_zones=initial_zones,
            days=days,
            source=source,
            force_refresh=refresh,
        )
    except Exception as e:
        logger.error(f"Error in source discovery: {e}")
        return {"error": str(e)}


@router.get("/frontier/stats")
async def get_frontier_stats():
    """Get frontier service statistics."""
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        return frontier_service.get_stats()
    except Exception as e:
        logger.error(f"Error getting frontier stats: {e}")
        return {"error": str(e)}
