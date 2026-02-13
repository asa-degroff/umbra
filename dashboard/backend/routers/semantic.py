"""
Semantic Analysis API Router

Endpoints for semantic diversity analysis data.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from dashboard.backend.services.chromadb_service import ChromaDBService

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
):
    """Get semantic records with pagination."""
    return chromadb_service.get_records(limit=limit, offset=offset, platform=platform)


@router.get("/embeddings")
async def get_embeddings(
    limit: int = Query(500, ge=1, le=2000),
):
    """Get embeddings for visualization."""
    return chromadb_service.get_embeddings_for_visualization(limit=limit)


@router.get("/metrics")
async def get_metrics():
    """Get current diversity metrics."""
    try:
        from semantic_analysis.analyzer import DiversityAnalyzer
        from semantic_analysis.storage import SemanticStorage
        
        storage = SemanticStorage("./data/chromadb")
        analyzer = DiversityAnalyzer()
        
        recent = storage.get_recent(days=7)
        if not recent:
            return {"error": "No recent records found"}
        
        metrics = analyzer.calculate_metrics(recent)
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
        
        result = run_analysis(
            pds_host="https://bsky.social",
            did="did:plc:oetfdqwocv4aegq2yj6ix4w5",
            access_token=None,
            chromadb_path="./data/chromadb",
            lookback_days=7,
            dry_run=True,
        )
        
        return result
    except Exception as e:
        logger.error(f"Error running analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))
