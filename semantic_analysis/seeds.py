"""
Interest Seeds Module

Replaces single-centroid frontier filtering with multiple anchor points:
cluster centroids (main topics) + detected outliers (intentional diversifications),
each weighted by recency and rarity so smaller/newer interests get boosted.

This is a self-contained, testable component. Frontier/discovery integration
is a separate follow-up.
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

import numpy as np
import requests

from .analyzer import (
    find_clusters,
    cosine_similarity,
    temporal_weight,
    _sanitize_for_prompt,
    DEFAULT_LLM_MODEL,
)

if TYPE_CHECKING:
    from .storage import SemanticStorage

logger = logging.getLogger('umbra.semantic_analysis.seeds')


@dataclass
class InterestSeed:
    """A detected interest seed — either a topic cluster or an outlier diversification."""
    seed_id: str                            # "cluster_0", "outlier_3"
    seed_type: str                          # "cluster" or "outlier"
    label: str                              # LLM-generated, e.g. "bioluminescence ecology"
    centroid: list[float]                   # Unit-normalized high-dim embedding
    representative_texts: list[str]         # Up to 5 post texts (for labeling + query gen)
    post_count: int                         # Posts in this seed (1 for outliers)
    post_indices: list[int]                 # Indices into source embeddings array
    weight: float                           # Combined recency × rarity weight
    recency_weight: float                   # Average temporal decay of seed's posts
    rarity_weight: float                    # Inverse-log of cluster size
    avg_distance_to_global_centroid: float  # Diagnostic: how far from the blob center
    created_at: str                         # ISO timestamp

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            'seed_id': self.seed_id,
            'seed_type': self.seed_type,
            'label': self.label,
            'centroid': self.centroid,
            'representative_texts': self.representative_texts,
            'post_count': self.post_count,
            'post_indices': self.post_indices,
            'weight': self.weight,
            'recency_weight': self.recency_weight,
            'rarity_weight': self.rarity_weight,
            'avg_distance_to_global_centroid': self.avg_distance_to_global_centroid,
            'created_at': self.created_at,
        }


class InterestSeedDetector:
    """
    Detects interest seeds from Umbra's content — cluster centroids for main
    topics and outliers for intentional creative diversifications.
    """

    def __init__(
        self,
        storage: 'SemanticStorage',
        ollama_url: str = "http://localhost:11434",
        llm_model: str = DEFAULT_LLM_MODEL,
        n_clusters: int = 5,
        outlier_percentile: float = 95.0,
        min_cluster_posts: int = 3,
        recency_half_life: float = 14.0,
        max_seeds: int = 10,
    ):
        self.storage = storage
        self.ollama_url = ollama_url.rstrip('/')
        self.llm_model = llm_model
        self.n_clusters = n_clusters
        self.outlier_percentile = outlier_percentile
        self.min_cluster_posts = min_cluster_posts
        self.recency_half_life = recency_half_life
        self.max_seeds = max_seeds
        self.session = requests.Session()

    def detect_seeds(
        self,
        days: int = 30,
        label_seeds: bool = True,
    ) -> list['InterestSeed']:
        """
        Detect interest seeds from Umbra's recent content.

        Pipeline:
        1. Fetch embeddings + compute temporal weights
        2. Cluster with weighted k-means
        3. Build cluster seeds (large clusters)
        4. Detect outliers (small clusters + within-cluster outliers)
        5. Sort by combined weight, trim to max_seeds
        6. Label via LLM (optional)

        Args:
            days: Lookback period for content
            label_seeds: Whether to generate LLM labels for each seed

        Returns:
            List of InterestSeed objects sorted by weight descending
        """
        # 1. Fetch Umbra's content
        records = self.storage.get_umbra_content(days=days)
        if not records:
            logger.warning("No Umbra content found for seed detection")
            return []

        embeddings = []
        weights = []
        texts = []
        created_ats = []

        for r in records:
            emb = r.get('embedding')
            if emb is None:
                continue
            embeddings.append(emb)
            weights.append(temporal_weight(r.get('created_at'), self.recency_half_life))
            texts.append(r.get('text', ''))
            created_ats.append(r.get('created_at', ''))

        if len(embeddings) < 2:
            logger.warning(f"Only {len(embeddings)} embeddings, need at least 2 for seed detection")
            return []

        embeddings_arr = np.array(embeddings)
        weights_arr = np.array(weights)

        # 2. Cluster
        effective_n_clusters = min(self.n_clusters, len(embeddings_arr))
        clusters = find_clusters(embeddings_arr, weights_arr, effective_n_clusters)

        # 3. Global centroid (diagnostic only)
        global_centroid = np.average(embeddings_arr, axis=0, weights=weights_arr)
        global_norm = np.linalg.norm(global_centroid)
        if global_norm > 0:
            global_centroid = global_centroid / global_norm

        # 3b. Compute adaptive outlier threshold from within-cluster distances
        all_within_dists: list[float] = []
        for cluster in clusters:
            centroid_arr = np.array(cluster['centroid'])
            for i in cluster['indices']:
                all_within_dists.append(1.0 - cosine_similarity(embeddings_arr[i], centroid_arr))

        if all_within_dists:
            outlier_threshold = float(np.percentile(all_within_dists, self.outlier_percentile))
        else:
            outlier_threshold = 0.4  # Fallback
        logger.info(f"Adaptive outlier threshold: {outlier_threshold:.3f} "
                    f"(p{self.outlier_percentile} of within-cluster distances)")

        now_iso = datetime.now(timezone.utc).isoformat()
        seeds: list[InterestSeed] = []
        outlier_candidates: list[int] = []

        # 4. Build cluster seeds + collect outlier candidates
        for k, cluster in enumerate(clusters):
            indices = cluster['indices']
            size = cluster['size']

            if size < self.min_cluster_posts:
                # Dissolve small cluster: all members become outlier candidates
                outlier_candidates.extend(indices)
                continue

            # Centroid (unit-normalized)
            centroid = np.array(cluster['centroid'])
            centroid_norm = np.linalg.norm(centroid)
            if centroid_norm > 0:
                centroid = centroid / centroid_norm

            # Representative texts: 5 posts closest to centroid
            sims_to_centroid = [
                (i, cosine_similarity(embeddings_arr[i], centroid))
                for i in indices
            ]
            sims_to_centroid.sort(key=lambda x: x[1], reverse=True)
            rep_indices = [idx for idx, _ in sims_to_centroid[:5]]
            rep_texts = [texts[idx] for idx in rep_indices]

            # Detect within-cluster outliers
            for i in indices:
                dist = 1.0 - cosine_similarity(embeddings_arr[i], centroid)
                if dist > outlier_threshold:
                    outlier_candidates.append(i)

            # Recency weight: mean temporal weight of cluster members
            cluster_recency = float(np.mean([weights_arr[i] for i in indices]))

            # Rarity weight: inverse-log of cluster size
            cluster_rarity = 1.0 / (1.0 + math.log(1 + size))

            # Combined weight: geometric mean
            combined = math.sqrt(cluster_recency * cluster_rarity)

            # Distance to global centroid
            avg_dist = float(1.0 - cosine_similarity(centroid, global_centroid))

            seeds.append(InterestSeed(
                seed_id=f"cluster_{k}",
                seed_type="cluster",
                label="",
                centroid=centroid.tolist(),
                representative_texts=rep_texts,
                post_count=size,
                post_indices=indices,
                weight=combined,
                recency_weight=cluster_recency,
                rarity_weight=cluster_rarity,
                avg_distance_to_global_centroid=avg_dist,
                created_at=now_iso,
            ))

        # 5. Confirm outliers: must be far from ALL cluster centroids
        cluster_centroids = [
            np.array(s.centroid) for s in seeds if s.seed_type == "cluster"
        ]

        # Deduplicate outlier candidates
        seen_outliers: set[int] = set()
        confirmed_outliers: list[int] = []
        for i in outlier_candidates:
            if i in seen_outliers:
                continue
            seen_outliers.add(i)

            if cluster_centroids:
                max_sim = max(
                    cosine_similarity(embeddings_arr[i], c)
                    for c in cluster_centroids
                )
                # If close to any cluster centroid, it's not a true outlier
                if (1.0 - max_sim) <= outlier_threshold:
                    continue

            confirmed_outliers.append(i)

        # 6. Build outlier seeds
        for j, i in enumerate(confirmed_outliers):
            emb = embeddings_arr[i]
            emb_norm = np.linalg.norm(emb)
            if emb_norm > 0:
                centroid = (emb / emb_norm).tolist()
            else:
                centroid = emb.tolist()

            outlier_recency = float(weights_arr[i])
            outlier_rarity = 1.0  # Maximum rarity for single-post outliers
            combined = math.sqrt(outlier_recency * outlier_rarity)
            avg_dist = float(1.0 - cosine_similarity(emb, global_centroid))

            seeds.append(InterestSeed(
                seed_id=f"outlier_{j}",
                seed_type="outlier",
                label="",
                centroid=centroid,
                representative_texts=[texts[i]],
                post_count=1,
                post_indices=[i],
                weight=combined,
                recency_weight=outlier_recency,
                rarity_weight=outlier_rarity,
                avg_distance_to_global_centroid=avg_dist,
                created_at=now_iso,
            ))

        # 7. Reserve slots for both types: clusters always get representation
        cluster_seeds = [s for s in seeds if s.seed_type == "cluster"]
        outlier_seeds = [s for s in seeds if s.seed_type == "outlier"]

        cluster_seeds.sort(key=lambda s: s.weight, reverse=True)
        outlier_seeds.sort(key=lambda s: s.weight, reverse=True)

        # Allocate: all clusters get a slot, remaining slots go to outliers
        max_cluster_slots = min(len(cluster_seeds), self.max_seeds)
        max_outlier_slots = self.max_seeds - max_cluster_slots

        seeds = cluster_seeds[:max_cluster_slots] + outlier_seeds[:max_outlier_slots]
        seeds.sort(key=lambda s: (s.seed_type == "outlier", -s.weight))  # Clusters first, then outliers

        # 8. Label seeds
        if label_seeds:
            for seed in seeds:
                seed.label = self._label_seed(seed)

        logger.info(
            f"Detected {len(seeds)} interest seeds "
            f"({sum(1 for s in seeds if s.seed_type == 'cluster')} clusters, "
            f"{sum(1 for s in seeds if s.seed_type == 'outlier')} outliers)"
        )
        return seeds

    def _label_seed(self, seed: InterestSeed) -> str:
        """Generate a short label for a seed using the local LLM."""
        if not seed.representative_texts:
            return "unknown topic"

        sanitized = [
            _sanitize_for_prompt(t, max_length=200)
            for t in seed.representative_texts[:5]
        ]
        posts_text = "\n".join(f"- {t}" for t in sanitized)

        prompt = (
            "Given these posts by an AI agent, generate a SHORT label (2-5 words) "
            "that captures the theme.\n\n"
            f"Posts:\n{posts_text}\n\n"
            "Label:"
        )

        try:
            resp = self.session.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.llm_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 20,
                    },
                },
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json().get('response', '').strip()

            # Validate: strip quotes, check word count
            label = raw.strip('"\'').strip()
            words = label.split()
            if 1 <= len(words) <= 10:
                return label
            # Too long — truncate to first 5 words
            if len(words) > 10:
                return " ".join(words[:5])

            return self._fallback_label(seed)

        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning(f"LLM labeling failed for {seed.seed_id}: {e}")
            return self._fallback_label(seed)

    def _fallback_label(self, seed: InterestSeed) -> str:
        """Generate a simple label from keyword extraction."""
        text = seed.representative_texts[0] if seed.representative_texts else ""
        if not text:
            return "unknown topic"

        stopwords = {
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
            'had', 'her', 'was', 'one', 'our', 'out', 'has', 'his', 'how',
            'its', 'may', 'new', 'now', 'old', 'see', 'way', 'who', 'did',
            'get', 'got', 'let', 'say', 'she', 'too', 'use', 'into', 'just',
            'than', 'them', 'then', 'this', 'that', 'what', 'when', 'will',
            'with', 'been', 'from', 'have', 'here', 'much', 'some', 'such',
            'very', 'more', 'most', 'also', 'about', 'would', 'could',
            'should', 'these', 'those', 'there', 'their', 'which', 'being',
            'think', 'really', 'like', 'just', 'know', 'want', 'make',
        }

        words = text.lower().split()
        keywords = [w for w in words if len(w) > 2 and w.isalpha() and w not in stopwords]

        # Deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique.append(w)

        if unique:
            return " ".join(unique[:3])
        return "miscellaneous topic"


def create_interest_seed_detector(
    storage: 'SemanticStorage',
    ollama_url: str = "http://localhost:11434",
    llm_model: Optional[str] = None,
    **kwargs,
) -> InterestSeedDetector:
    """Factory function to create a configured InterestSeedDetector."""
    return InterestSeedDetector(
        storage=storage,
        ollama_url=ollama_url,
        llm_model=llm_model or DEFAULT_LLM_MODEL,
        **kwargs,
    )
