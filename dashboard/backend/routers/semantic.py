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
from pydantic import BaseModel, Field

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from dashboard.backend.services.chromadb_service import ChromaDBService
from dashboard.backend.services.shared_storage import get_shared_storage
from config_loader import get_config

logger = logging.getLogger('dashboard.api.semantic')

router = APIRouter()

# Initialize service (uses shared storage singleton - no duplicate PersistentClient)
chromadb_service = ChromaDBService()


def _generate_topic_labels(cluster_texts: dict[int, list[str]]) -> dict[int, str]:
    """
    Generate short topic labels for clusters using local LLM.

    Args:
        cluster_texts: Dict mapping cluster_id -> list of sample texts

    Returns:
        Dict mapping cluster_id -> short topic label string
    """
    labels = {}
    non_noise = {k: v for k, v in cluster_texts.items() if k != -1 and v}

    if not non_noise:
        return labels

    try:
        import requests as req

        # Build a single prompt for all clusters at once (cheaper than per-cluster)
        cluster_descriptions = []
        for cid in sorted(non_noise.keys()):
            texts = non_noise[cid]
            samples = "\n".join(f"  - {t[:150]}" for t in texts[:4])
            cluster_descriptions.append(f"Cluster {cid}:\n{samples}")

        all_clusters = "\n\n".join(cluster_descriptions)

        prompt = f"""Given these text clusters from an AI agent's content, generate a SHORT topic label (2-4 words) for each cluster. The label should capture the main theme.

{all_clusters}

Return ONLY a JSON object mapping cluster number to label. Example:
{{"0": "AI consciousness", "1": "Protocol design", "2": "Creative writing"}}

Labels:"""

        # Determine which LLM model to use
        llm_model = "qwen3:8b"  # default
        try:
            config = get_config()
            configured_model = config.get("semantic_analysis.ollama.llm_model", "")
            if configured_model:
                # Verify the model exists in Ollama
                tags_resp = req.get("http://localhost:11434/api/tags", timeout=5)
                available = [m["name"] for m in tags_resp.json().get("models", [])]
                if configured_model in available:
                    llm_model = configured_model
                else:
                    logger.debug(f"Configured model '{configured_model}' not found, using {llm_model}")
        except Exception:
            pass

        # Use /api/chat with thinking disabled for fast structured output
        resp = req.post(
            "http://localhost:11434/api/chat",
            json={
                "model": llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "keep_alive": "60s",
                "options": {"temperature": 0.3, "num_predict": 1024},
            },
            timeout=300,
        )
        resp.raise_for_status()
        result = resp.json().get("message", {}).get("content", "").strip()

        # Strip markdown code fences if present
        import re
        result = re.sub(r'^```json\s*', '', result)
        result = re.sub(r'\s*```$', '', result).strip()

        # Parse JSON from response — try from the end first (thinking text has reasoning before JSON)
        import json
        end = result.rfind("}") + 1
        if end > 0:
            # Search backwards for the matching opening brace
            depth = 0
            start = -1
            for i in range(end - 1, -1, -1):
                if result[i] == '}':
                    depth += 1
                elif result[i] == '{':
                    depth -= 1
                    if depth == 0:
                        start = i
                        break

            if start >= 0:
                try:
                    raw_labels = json.loads(result[start:end])
                    for k, v in raw_labels.items():
                        try:
                            labels[int(k)] = str(v)[:50]
                        except (ValueError, TypeError):
                            pass
                except json.JSONDecodeError as je:
                    logger.warning(f"Failed to parse topic labels JSON: {je}, snippet: {result[start:end][:200]}")
            else:
                logger.warning(f"No JSON object found in LLM response ({len(result)} chars)")
        else:
            logger.warning(f"No closing brace in LLM response ({len(result)} chars)")

        logger.info(f"Generated {len(labels)} topic labels via LLM")

    except Exception as e:
        logger.warning(f"Topic label generation failed: {e}", exc_info=True)

    return labels


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
    refresh: bool = Query(False),
):
    """
    Get 2D-projected embeddings for scatter plot visualization.

    Uses UMAP or PCA to reduce high-dimensional embeddings to 2D.
    Results are cached until new records are added.
    """
    import hashlib
    import numpy as np

    try:
        # Check disk cache first (survives restarts)
        if not refresh:
            try:
                from dashboard.backend.services.disk_cache import disk_cache, get_config_hash
                config_hash = get_config_hash()
                if disk_cache.is_fresh("embeddings_2d", max_age_seconds=48 * 3600, config_hash=config_hash):
                    wrapper = disk_cache.get("embeddings_2d")
                    if wrapper:
                        data = wrapper["data"]
                        data["from_cache"] = True
                        # Also populate in-memory cache
                        async with _embeddings_2d_lock:
                            _embeddings_2d_cache["disk"] = data
                        return data
            except Exception as e:
                logger.warning(f"Disk cache read (embeddings_2d) failed: {e}")

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

        # Check in-memory cache
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
                min_dist=0.05,
                metric="cosine",
                random_state=42,
            )
            coords_2d = reducer.fit_transform(embeddings)
        else:  # PCA
            from sklearn.decomposition import PCA
            reducer = PCA(n_components=2, random_state=42)
            coords_2d = reducer.fit_transform(embeddings)

        # Run HDBSCAN on 2D projection for topic clustering
        cluster_labels = np.full(len(coords_2d), -1)
        cluster_meta = []
        try:
            from sklearn.cluster import HDBSCAN as _HDBSCAN
            n = len(coords_2d)
            clusterer = _HDBSCAN(
                min_cluster_size=max(15, n // 60),
                min_samples=5,
                metric="euclidean",
            )
            cluster_labels = clusterer.fit_predict(coords_2d)

            # Collect sample texts per cluster for label generation
            unique_labels = sorted(set(cluster_labels))
            cluster_texts = {}
            for i, label in enumerate(cluster_labels):
                if label not in cluster_texts:
                    cluster_texts[label] = []
                if len(cluster_texts[label]) < 5:
                    text = (valid_data[i].get("text", "") or "")[:200]
                    if text:
                        cluster_texts[label].append(text)

            # Generate LLM topic labels (limit to top 12 clusters by size)
            real_clusters = {k: v for k, v in cluster_texts.items() if k != -1}
            if len(real_clusters) <= 12:
                topic_labels = _generate_topic_labels(cluster_texts)
            else:
                # Too many clusters for one LLM call — label the top 12
                sorted_ids = sorted(real_clusters.keys(), 
                    key=lambda k: int(np.sum(cluster_labels == k)), reverse=True)
                top_texts = {k: cluster_texts[k] for k in sorted_ids[:12]}
                topic_labels = _generate_topic_labels(top_texts)

            topic_palette = [
                "#f43f5e", "#3b82f6", "#22c55e", "#f59e0b",
                "#a855f7", "#06b6d4", "#ec4899", "#84cc16",
                "#f97316", "#6366f1", "#14b8a6", "#e11d48",
            ]

            for label in unique_labels:
                count = int(np.sum(cluster_labels == label))
                if label == -1:
                    cluster_meta.append({
                        "id": -1,
                        "label": "Unclustered",
                        "count": count,
                        "color": "#6b7280",
                    })
                else:
                    cluster_meta.append({
                        "id": int(label),
                        "label": topic_labels.get(label, f"Topic {label + 1}"),
                        "count": count,
                        "color": topic_palette[label % len(topic_palette)],
                    })

            n_clusters = len([l for l in unique_labels if l != -1])
            n_noise = int(np.sum(cluster_labels == -1))
            logger.info(f"HDBSCAN: {n_clusters} clusters, {n_noise} noise points")

        except ImportError:
            logger.warning("sklearn HDBSCAN not available, skipping topic clustering")
        except Exception as e:
            logger.warning(f"HDBSCAN clustering failed: {e}")

        # Build response
        points = []
        for i, d in enumerate(valid_data):
            full_text = d.get("text", "") or ""
            points.append({
                "x": float(coords_2d[i, 0]),
                "y": float(coords_2d[i, 1]),
                "uri": d["uri"],
                "platform": d.get("platform", "unknown"),
                "cluster_id": int(cluster_labels[i]),
                "text_preview": full_text[:200] + ("..." if len(full_text) > 200 else ""),
                "text": full_text,
                "created_at": d.get("created_at"),
            })

        result = {
            "points": points,
            "method": method,
            "total": len(points),
            "clusters": cluster_meta,
        }

        # Cache result (in-memory)
        async with _embeddings_2d_lock:
            _embeddings_2d_cache[uri_hash] = result

        # Persist to disk cache
        try:
            from dashboard.backend.services.disk_cache import disk_cache, get_config_hash
            disk_cache.put("embeddings_2d", result, config_hash=get_config_hash())
        except Exception as e:
            logger.warning(f"Disk cache write (embeddings_2d) failed: {e}")

        logger.info(f"Cached 2D embeddings: {len(points)} points")

        return result
        
    except Exception as e:
        logger.error(f"Error computing 2D embeddings: {e}")
        return {"points": [], "method": method, "total": 0, "error": str(e)}


@router.get("/metrics")
async def get_metrics(refresh: bool = Query(False)):
    """Get current diversity metrics using ANN-based computation."""
    try:
        from dashboard.backend.services.disk_cache import disk_cache, get_config_hash

        # Serve from disk cache unless refresh requested
        if not refresh:
            config_hash = get_config_hash()
            if disk_cache.is_fresh("metrics", max_age_seconds=48 * 3600, config_hash=config_hash):
                wrapper = disk_cache.get("metrics")
                if wrapper:
                    data = wrapper["data"]
                    data["from_cache"] = True
                    return data

        from semantic_analysis.analyzer import DiversityAnalyzer

        storage = get_shared_storage()
        if storage is None:
            return {"error": "Storage not available"}

        analyzer = DiversityAnalyzer(storage=storage)  # Pass storage for ANN

        recent = storage.get_recent(days=7)
        if not recent:
            return {"error": "No recent records found"}

        # Use ANN-based metrics for efficiency
        metrics = analyzer.calculate_metrics_ann(recent)

        # Write to disk cache
        try:
            disk_cache.put("metrics", metrics, config_hash=get_config_hash())
        except Exception as e:
            logger.warning(f"Disk cache write (metrics) failed: {e}")

        return metrics
    except Exception as e:
        logger.error(f"Error calculating metrics: {e}")
        return {"error": str(e)}


@router.get("/guidance")
async def get_guidance(refresh: bool = Query(False)):
    """Get latest diversity guidance."""
    try:
        from dashboard.backend.services.disk_cache import disk_cache, get_config_hash

        # Serve from disk cache unless refresh requested
        if not refresh:
            config_hash = get_config_hash()
            if disk_cache.is_fresh("guidance", max_age_seconds=48 * 3600, config_hash=config_hash):
                wrapper = disk_cache.get("guidance")
                if wrapper:
                    data = wrapper["data"]
                    data["from_cache"] = True
                    return data

        from semantic_analysis.analyzer import DiversityAnalyzer

        storage = get_shared_storage()
        if storage is None:
            return {"guidance": "Storage not available."}

        analyzer = DiversityAnalyzer()

        recent = storage.get_recent(days=7)
        if not recent:
            return {"guidance": "No recent records to analyze."}

        metrics = analyzer.calculate_metrics(recent)
        guidance = analyzer.generate_guidance(metrics)

        # Generate topic labels for clusters
        raw_clusters = metrics.get("clusters", [])[:8]
        cluster_texts_for_labels = {}
        for i, cluster in enumerate(raw_clusters):
            texts = cluster.get("sample_texts", [])
            if texts:
                cluster_texts_for_labels[i] = texts
        topic_labels = _generate_topic_labels(cluster_texts_for_labels)

        # Build cluster data for dashboard (strip embeddings, keep display fields)
        clusters_display = []
        for i, cluster in enumerate(raw_clusters):
            clusters_display.append({
                "index": i + 1,
                "label": topic_labels.get(i, f"Cluster {i + 1}"),
                "pct": round(cluster.get("pct", 0), 1),
                "size": cluster.get("size", 0),
                "weight_sum": round(cluster.get("weight_sum", 0), 2),
                "sample_texts": cluster.get("sample_texts", [])[:3],
            })

        result = {
            "guidance": guidance,
            "summary": analyzer.format_summary(metrics),
            "metrics": {
                "diversity": metrics.get("weighted_avg_diversity"),
                "avg_diversity": metrics.get("avg_diversity"),
                "cluster_dominance": metrics.get("cluster_dominance"),
                "avg_pairwise_similarity": metrics.get("avg_pairwise_similarity"),
                "max_pairwise_similarity": metrics.get("max_pairwise_similarity"),
                "records_analyzed": metrics.get("records_with_embeddings"),
                "total_records": metrics.get("total_records"),
                "temporal_half_life": metrics.get("temporal_half_life"),
            },
            "clusters": clusters_display,
            "platforms": metrics.get("platforms", {}),
        }

        # Write to disk cache
        try:
            disk_cache.put("guidance", result, config_hash=get_config_hash())
        except Exception as e:
            logger.warning(f"Disk cache write (guidance) failed: {e}")

        return result
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

@router.get("/frontier/seeds")
async def get_interest_seeds(
    days: int = Query(30, ge=7, le=90),
    refresh: bool = Query(False),
):
    """
    Get detected interest seeds.
    
    Seeds are anchor points in embedding space: cluster centroids (main topics)
    and outlier posts (intentional creative diversifications).
    """
    import asyncio
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        result = await asyncio.to_thread(frontier_service.get_seeds, days=days, force_refresh=refresh)
        # Strip internal _seed_objects before sending to client
        result.pop('_seed_objects', None)
        return result
    except Exception as e:
        logger.error(f"Error getting seeds: {e}")
        return {"seeds": [], "error": str(e)}


@router.get("/frontier/zones")
async def get_frontier_zones(
    days: int = Query(30, ge=7, le=90),
    top_n: int = Query(10, ge=1, le=20),
    source: str = Query("all", pattern="^(umbra|network|all)$"),
    use_seeds: bool = Query(True),
    refresh: bool = Query(False),
):
    """
    Get detected frontier zones.
    
    Frontier zones are unexplored regions in embedding space
    adjacent to existing content clusters or interest seeds.
    """
    import asyncio
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        return await asyncio.to_thread(
            frontier_service.get_zones,
            days=days,
            top_n=top_n,
            source=source,
            use_seeds=use_seeds,
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
    background: bool = Query(False),
):
    """
    Run source discovery to find external content in frontier zones.

    Searches Wikipedia, arXiv, and Semantic Scholar for content in detected frontiers.
    Set background=true to run asynchronously and poll for results.
    """
    import asyncio
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        # Run in thread to avoid blocking the event loop
        return await asyncio.to_thread(
            frontier_service.discover_sources,
            max_rounds=max_rounds,
            max_total_sources=max_sources,
            initial_zones=initial_zones,
            days=days,
            source=source,
            force_refresh=refresh,
            background=background,
        )
    except Exception as e:
        logger.error(f"Error in source discovery: {e}")
        return {"error": str(e)}


class FocusedDiscoveryRequest(BaseModel):
    seed_ids: list[str] = Field(..., min_length=1, description="Seed IDs to focus discovery on")
    max_rounds: int = Field(2, ge=1, le=5)
    max_sources: int = Field(25, ge=5, le=100)
    initial_zones: int = Field(3, ge=1, le=10)
    days: int = Field(30, ge=7, le=90)
    source: str = Field("all", pattern="^(umbra|network|all)$")


@router.post("/frontier/discover/focused")
async def discover_sources_focused(body: FocusedDiscoveryRequest):
    """
    Run source discovery focused on specific seeds.

    Accepts a list of seed_ids and runs discovery only in zones
    generated from those seeds, rather than all detected seeds.
    """
    import asyncio
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        # Run in thread to avoid blocking the event loop
        return await asyncio.to_thread(
            frontier_service.discover_sources_focused,
            seed_ids=body.seed_ids,
            max_rounds=body.max_rounds,
            max_sources_per_zone=5,
            max_total_sources=body.max_sources,
            initial_zones=body.initial_zones,
            days=body.days,
            source=body.source,
        )
    except Exception as e:
        logger.error(f"Error in focused source discovery: {e}")
        return {"error": str(e)}


@router.get("/frontier/sources")
async def get_frontier_sources(
    status: Optional[str] = Query(None, pattern="^(frontier|pending|used|rejected)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get persisted discovered sources from the database.

    Unlike /frontier/discover, this returns previously saved results
    without re-running discovery.
    """
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        return frontier_service.get_persisted_sources(
            status=status,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"Error getting persisted sources: {e}")
        return {"sources": [], "error": str(e)}


@router.post("/frontier/sources/{source_id}/feedback")
async def rate_source(
    source_id: int,
    rating: int = Query(..., ge=-1, le=1),
):
    """
    Rate a discovered source (thumbs up / thumbs down).

    rating: -1 = downrank, 0 = clear, 1 = uprank.
    Downranked sources are also marked as 'rejected'.
    """
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        return frontier_service.rate_source(source_id, rating)
    except Exception as e:
        logger.error(f"Error rating source {source_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/frontier/sources/evaluate")
async def evaluate_pending_sources(
    threshold: float = Query(0.4, ge=0.0, le=1.0),
):
    """
    Re-evaluate pending sources against current Umbra content.

    Recomputes relevance scores with a fresh centroid and promotes
    sources above the threshold to 'frontier' status.
    """
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        return frontier_service.evaluate_pending(threshold=threshold)
    except Exception as e:
        logger.error(f"Error evaluating pending sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/frontier/sources/cleanup")
async def cleanup_old_sources(
    max_age_days: int = Query(90, ge=7, le=365),
):
    """
    Delete sources older than max_age_days.

    User-rated sources are preserved regardless of age.
    """
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        return frontier_service.cleanup_sources(max_age_days=max_age_days)
    except Exception as e:
        logger.error(f"Error cleaning up sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/frontier/models")
async def get_model_status():
    """
    Get status of Ollama models (LLM and embedding).

    Returns loaded models with VRAM usage, expiry, and active/idle status.
    """
    import asyncio
    return await asyncio.to_thread(_get_model_status_sync)


def _get_model_status_sync():
    import requests as req
    from datetime import datetime, timezone

    ollama_url = "http://localhost:11434"
    result = {"models": [], "error": None}

    try:
        resp = req.get(f"{ollama_url}/api/ps", timeout=5)
        resp.raise_for_status()
        data = resp.json()

        now = datetime.now(timezone.utc)

        for m in data.get("models", []):
            expires_str = m.get("expires_at", "")
            expires_at = None
            seconds_remaining = None
            if expires_str:
                try:
                    expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                    seconds_remaining = max(0, (expires_at - now).total_seconds())
                except (ValueError, TypeError):
                    pass

            size_vram_gb = round(m.get("size_vram", 0) / 1e9, 1)
            size_total_gb = round(m.get("size", 0) / 1e9, 1)

            model_info = {
                "name": m.get("name", "unknown"),
                "family": m.get("details", {}).get("family", ""),
                "parameter_size": m.get("details", {}).get("parameter_size", ""),
                "quantization": m.get("details", {}).get("quantization_level", ""),
                "size_vram_gb": size_vram_gb,
                "size_total_gb": size_total_gb,
                "context_length": m.get("context_length", 0),
                "expires_at": expires_str,
                "seconds_remaining": int(seconds_remaining) if seconds_remaining is not None else None,
                "status": "active" if seconds_remaining and seconds_remaining > 60 else "idle",
            }
            result["models"].append(model_info)

    except req.ConnectionError:
        result["error"] = "Ollama not reachable"
    except Exception as e:
        result["error"] = str(e)

    # Also check GPU VRAM if possible
    try:
        import subprocess
        proc = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram"],
            capture_output=True, text=True, timeout=5,
            env={**__import__("os").environ, "HSA_OVERRIDE_GFX_VERSION": "10.3.0"},
        )
        if proc.returncode == 0:
            lines = proc.stdout.strip().split("\n")
            gpu_info = []
            for line in lines:
                if "Total Memory" in line and "Used" not in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        gpu_id = parts[0].strip()
                        total_bytes = int(parts[1].strip())
                        gpu_info.append({"gpu": gpu_id, "total_gb": round(total_bytes / 1e9, 1)})
                elif "Used Memory" in line:
                    parts = line.split(":")
                    if len(parts) >= 2 and gpu_info:
                        used_bytes = int(parts[1].strip())
                        gpu_info[-1]["used_gb"] = round(used_bytes / 1e9, 1)
                        gpu_info[-1]["pct"] = round(used_bytes / (gpu_info[-1]["total_gb"] * 1e9) * 100, 1) if gpu_info[-1]["total_gb"] > 0 else 0
            result["gpu"] = gpu_info
    except Exception:
        pass  # GPU info is optional

    return result


@router.get("/frontier/stats")
async def get_frontier_stats():
    """Get frontier service statistics."""
    try:
        from dashboard.backend.services.frontier_service import frontier_service
        return frontier_service.get_stats()
    except Exception as e:
        logger.error(f"Error getting frontier stats: {e}")
        return {"error": str(e)}


@router.get("/frontier/providers")
async def get_frontier_providers():
    """Debug: list active source providers."""
    try:
        from dashboard.backend.services.frontier_service import _source_discovery
        if _source_discovery is None:
            return {"error": "Source discovery not initialized"}
        providers = []
        for p in _source_discovery.providers:
            info = {"source_type": p.source_type, "has_find_similar": hasattr(p, 'find_similar')}
            if hasattr(p, 'api_key'):
                info["has_api_key"] = bool(p.api_key)
            if hasattr(p, 'budget'):
                info["budget"] = p.budget.today_summary
            providers.append(info)
        return {"providers": providers}
    except Exception as e:
        return {"error": str(e)}
