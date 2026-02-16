"""
Diversity Analyzer

Calculates semantic diversity metrics and generates guidance using local LLM.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
import requests

import re

import numpy as np

if TYPE_CHECKING:
    from .storage import SemanticStorage

logger = logging.getLogger('umbra.semantic_analysis')


def _sanitize_for_prompt(text: str, max_length: int = 200) -> str:
    """Strip control characters, truncate, and escape backticks for safe LLM prompt inclusion."""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = text.replace('`', "'")
    if len(text) > max_length:
        text = text[:max_length] + "..."
    return text

DEFAULT_LLM_MODEL = "qwen3:8b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"


def find_clusters(
    embeddings: np.ndarray,
    weights: np.ndarray,
    n_clusters: int,
) -> list[dict]:
    """
    Find topic clusters using simple k-means-like approach.

    Pure function — no class instance required.

    Returns list of cluster dicts with centroid, indices, size.
    """
    n = len(embeddings)
    if n < n_clusters:
        return [{
            'centroid': embeddings[0].tolist() if n > 0 else [],
            'indices': list(range(n)),
            'size': n,
            'weight_sum': float(np.sum(weights)),
        }]

    rng = np.random.default_rng(42)
    init_indices = rng.choice(n, n_clusters, replace=False, p=weights / weights.sum())
    centroids = embeddings[init_indices].copy()

    for _ in range(10):
        assignments = []
        for emb in embeddings:
            sims = [cosine_similarity(emb, c) for c in centroids]
            assignments.append(np.argmax(sims))

        new_centroids = []
        for k in range(n_clusters):
            cluster_mask = np.array(assignments) == k
            if np.any(cluster_mask):
                cluster_weights = weights[cluster_mask]
                cluster_embs = embeddings[cluster_mask]
                new_centroid = np.average(cluster_embs, axis=0, weights=cluster_weights)
                new_centroids.append(new_centroid)
            else:
                new_centroids.append(centroids[k])
        centroids = np.array(new_centroids)

    clusters = []
    for k in range(n_clusters):
        indices = [i for i, a in enumerate(assignments) if a == k]
        cluster_weights = weights[indices] if indices else np.array([0])
        clusters.append({
            'centroid': centroids[k].tolist(),
            'indices': indices,
            'size': len(indices),
            'weight_sum': float(np.sum(cluster_weights)),
            'pct': len(indices) / n * 100,
        })

    clusters.sort(key=lambda c: c['weight_sum'], reverse=True)
    return clusters


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(a)
    b = np.array(b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def temporal_weight(created_at: str, half_life_days: float = 7.0) -> float:
    """
    Calculate temporal decay weight for a record.
    
    Uses exponential decay with configurable half-life.
    
    Args:
        created_at: ISO format timestamp
        half_life_days: Days until weight is halved
        
    Returns:
        Weight between 0 and 1
    """
    if not created_at:
        return 0.5  # Default weight for records without timestamps
    
    try:
        # Parse timestamp
        if isinstance(created_at, str):
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        else:
            dt = created_at
        
        # Calculate age in days (clamp to 0 for future timestamps)
        now = datetime.now(timezone.utc)
        age_days = max(0, (now - dt).total_seconds() / 86400)

        # Exponential decay
        decay_rate = math.log(2) / half_life_days
        return math.exp(-decay_rate * age_days)
        
    except (ValueError, TypeError):
        return 0.5


class DiversityAnalyzer:
    """Analyzes semantic diversity and generates guidance."""
    
    def __init__(
        self,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        llm_model: str = DEFAULT_LLM_MODEL,
        storage: Optional['SemanticStorage'] = None,
    ):
        """
        Initialize the analyzer.
        
        Args:
            ollama_url: URL for Ollama API
            llm_model: Model name for guidance generation
            storage: Optional SemanticStorage for ANN-based metrics
        """
        self.ollama_url = ollama_url.rstrip('/')
        self.llm_model = llm_model
        self.session = requests.Session()
        self.storage = storage
    
    def calculate_metrics_ann(
        self,
        records: list[dict],
        sample_size: int = 200,
        k_neighbors: int = 10,
        temporal_half_life: float = 7.0,
    ) -> dict:
        """
        Calculate diversity metrics using ChromaDB's native ANN search.
        
        This is more efficient than manual O(n²) pairwise computation.
        Requires self.storage to be set.
        
        Args:
            records: List of records (used for clustering and platform stats)
            sample_size: Number of records to sample for ANN queries
            k_neighbors: Number of neighbors to consider
            temporal_half_life: Half-life for temporal weighting in clustering
            
        Returns:
            Dict of metrics
        """
        if not self.storage:
            logger.warning("No storage provided, falling back to manual metrics")
            return self.calculate_metrics(records, temporal_half_life=temporal_half_life)
        
        # Get ANN-based diversity metrics from storage
        ann_metrics = self.storage.compute_diversity_metrics_ann(
            sample_size=sample_size,
            k_neighbors=k_neighbors,
        )
        
        if ann_metrics.get('error'):
            logger.warning(f"ANN metrics failed: {ann_metrics['error']}, falling back to manual")
            return self.calculate_metrics(records, temporal_half_life=temporal_half_life)
        
        # Combine with clustering analysis (still need embeddings for this)
        embeddings = []
        weights = []
        for r in records:
            emb = r.get('embedding')
            if emb is not None:
                embeddings.append(emb)
                weights.append(temporal_weight(r.get('created_at'), temporal_half_life))
        
        if embeddings:
            embeddings_arr = np.array(embeddings)
            weights_arr = np.array(weights)
            
            # Run clustering on the sample
            clusters = self._find_clusters(embeddings_arr, weights_arr, n_clusters=5)
            
            # Calculate cluster dominance
            cluster_sizes = [len(c['indices']) for c in clusters]
            total = sum(cluster_sizes)
            cluster_dominance = max(cluster_sizes) / total if total > 0 else 0
            
            # Add sample texts to clusters
            for cluster in clusters:
                cluster['sample_texts'] = []
                for idx in cluster['indices'][:3]:
                    if idx < len(records):
                        text = records[idx].get('text', '')[:200]
                        cluster['sample_texts'].append(text)
            
            ann_metrics['clusters'] = clusters
            ann_metrics['cluster_dominance'] = cluster_dominance
        
        # Map ANN metrics to standard metric names for compatibility
        ann_metrics['records_with_embeddings'] = ann_metrics.get('sample_size', 0)
        ann_metrics['weighted_avg_diversity'] = ann_metrics.get('diversity_score', 0)
        ann_metrics['avg_diversity'] = ann_metrics.get('diversity_score', 0)
        ann_metrics['avg_pairwise_similarity'] = 1.0 - ann_metrics.get('avg_neighbor_distance', 0)
        ann_metrics['temporal_half_life'] = temporal_half_life
        
        return ann_metrics
    
    def calculate_metrics(
        self,
        records: list[dict],
        n_clusters: int = 5,
        temporal_half_life: float = 7.0,
    ) -> dict:
        """
        Calculate diversity metrics for a set of records.
        
        Args:
            records: List of records with 'embedding', 'created_at', etc.
            n_clusters: Number of clusters for topic analysis
            temporal_half_life: Half-life for temporal weighting
            
        Returns:
            Dict of metrics
        """
        if not records:
            return {
                'total_records': 0,
                'error': 'No records to analyze',
            }
        
        # Extract embeddings and weights
        embeddings = []
        weights = []
        platforms = {}
        
        for r in records:
            emb = r.get('embedding')
            if emb is None:
                continue
            embeddings.append(emb)
            weights.append(temporal_weight(r.get('created_at'), temporal_half_life))
            
            # Count platforms
            platform = r.get('metadata', {}).get('platform', 'unknown')
            platforms[platform] = platforms.get(platform, 0) + 1
        
        if not embeddings:
            return {
                'total_records': len(records),
                'error': 'No embeddings found',
            }
        
        embeddings = np.array(embeddings)
        weights = np.array(weights)
        
        # 1. Calculate weighted centroid
        weighted_centroid = np.average(embeddings, axis=0, weights=weights)
        
        # 2. Calculate average distance from centroid (diversity measure)
        distances_from_centroid = []
        for emb in embeddings:
            dist = 1 - cosine_similarity(emb, weighted_centroid)
            distances_from_centroid.append(dist)
        
        avg_diversity = float(np.mean(distances_from_centroid))
        weighted_avg_diversity = float(np.average(distances_from_centroid, weights=weights))
        
        # 3. Calculate pairwise similarities (topic clustering proxy)
        n = len(embeddings)
        if n > 1:
            pairwise_sims = []
            # Sample if too many records
            sample_size = min(n, 100)
            rng = np.random.default_rng(42)
            indices = rng.choice(n, sample_size, replace=False) if n > 100 else range(n)
            
            for i in indices:
                for j in indices:
                    if i < j:
                        sim = cosine_similarity(embeddings[i], embeddings[j])
                        pairwise_sims.append(sim)
            
            avg_similarity = float(np.mean(pairwise_sims)) if pairwise_sims else 0
            max_similarity = float(np.max(pairwise_sims)) if pairwise_sims else 0
        else:
            avg_similarity = 0
            max_similarity = 0
        
        # 4. Identify high-similarity clusters (potential repetition zones)
        clusters = self._find_clusters(embeddings, weights, n_clusters)
        
        # 5. Find the dominant cluster
        cluster_sizes = [len(c['indices']) for c in clusters]
        total = sum(cluster_sizes)
        cluster_dominance = max(cluster_sizes) / total if total > 0 else 0
        
        # 6. Get representative texts for each cluster
        for cluster in clusters:
            cluster['sample_texts'] = []
            for idx in cluster['indices'][:3]:  # Top 3 per cluster
                if idx < len(records):
                    text = records[idx].get('text', '')[:200]
                    cluster['sample_texts'].append(text)
        
        return {
            'total_records': len(records),
            'records_with_embeddings': len(embeddings),
            'platforms': platforms,
            'avg_diversity': avg_diversity,
            'weighted_avg_diversity': weighted_avg_diversity,
            'avg_pairwise_similarity': avg_similarity,
            'max_pairwise_similarity': max_similarity,
            'cluster_dominance': cluster_dominance,
            'clusters': clusters,
            'temporal_half_life': temporal_half_life,
        }
    
    def _find_clusters(
        self,
        embeddings: np.ndarray,
        weights: np.ndarray,
        n_clusters: int,
    ) -> list[dict]:
        """Delegate to module-level find_clusters()."""
        return find_clusters(embeddings, weights, n_clusters)
    
    def generate_guidance(self, metrics: dict) -> str:
        """
        Generate actionable guidance using local LLM.
        
        Args:
            metrics: Metrics dict from calculate_metrics()
            
        Returns:
            Guidance text
        """
        if metrics.get('error'):
            return f"Unable to generate guidance: {metrics['error']}"
        
        # Build prompt
        cluster_summary = ""
        for i, cluster in enumerate(metrics.get('clusters', [])[:5]):
            samples = cluster.get('sample_texts', [])
            sample_preview = _sanitize_for_prompt(samples[0], max_length=100) if samples else "No samples"
            cluster_summary += f"\n- Cluster {i+1} ({cluster['pct']:.1f}%): {sample_preview}"
        
        prompt = f"""You are analyzing an AI agent's recent content output for topic diversity.

METRICS:
- Total records analyzed: {metrics.get('records_with_embeddings', 0)}
- Average diversity score: {metrics.get('avg_diversity', 0):.3f} (higher = more diverse)
- Weighted diversity (recent posts matter more): {metrics.get('weighted_avg_diversity', 0):.3f}
- Average pairwise similarity: {metrics.get('avg_pairwise_similarity', 0):.3f} (lower = more diverse)
- Dominant cluster concentration: {metrics.get('cluster_dominance', 0):.1%}

TOPIC CLUSTERS (by recency-weighted importance):
{cluster_summary}

PLATFORM DISTRIBUTION:
{metrics.get('platforms', {})}

Based on this analysis, provide 2-3 sentences of specific, actionable guidance for the agent to diversify their thinking and output. Focus on:
1. Specific topic areas that appear underexplored
2. Types of content or perspectives to seek out
3. Patterns to be aware of (e.g., if one cluster is dominant)

Be concrete and specific, not generic. The agent should be able to act on your guidance immediately."""

        try:
            resp = self.session.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "keep_alive": "60m",
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 4096,
                    },
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get('message', {}).get('content', '').strip()
            
        except requests.RequestException as e:
            logger.error(f"Guidance generation failed: {e}")
            return self._fallback_guidance(metrics)
    
    def _fallback_guidance(self, metrics: dict) -> str:
        """Generate simple guidance without LLM."""
        parts = []
        
        diversity = metrics.get('weighted_avg_diversity', 0)
        if diversity < 0.3:
            parts.append("Your recent content shows high thematic concentration. Consider exploring topics outside your usual focus areas.")
        
        dominance = metrics.get('cluster_dominance', 0)
        if dominance > 0.4:
            parts.append(f"One topic cluster accounts for {dominance:.0%} of your recent output. Try balancing with other themes.")
        
        platforms = metrics.get('platforms', {})
        if len(platforms) == 1:
            parts.append(f"All content is from {list(platforms.keys())[0]}. Consider cross-posting to other platforms.")
        
        if not parts:
            parts.append("Your content shows reasonable diversity. Keep exploring new perspectives and topics.")
        
        return " ".join(parts)
    
    def format_summary(self, metrics: dict) -> str:
        """Format metrics into a human-readable summary."""
        if metrics.get('error'):
            return f"Analysis incomplete: {metrics['error']}"
        
        lines = [
            f"Analyzed {metrics.get('records_with_embeddings', 0)} records",
            f"Diversity score: {metrics.get('weighted_avg_diversity', 0):.2f}",
            f"Topic concentration: {metrics.get('cluster_dominance', 0):.0%}",
        ]
        
        platforms = metrics.get('platforms', {})
        if platforms:
            platform_str = ", ".join(f"{k}: {v}" for k, v in platforms.items())
            lines.append(f"Platforms: {platform_str}")
        
        return "\n".join(lines)
