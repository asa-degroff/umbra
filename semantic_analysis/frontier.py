"""
Frontier Detection Module

Finds unexplored regions in embedding space adjacent to existing clusters
to guide content discovery. Uses UMAP for dimensionality reduction and
KDE for density estimation in 2D space.

Key approach:
- Fit UMAP on all embeddings to get 2D coordinates
- Estimate density via gaussian KDE in 2D
- Score a regular grid: low density + moderate cluster adjacency = frontier
- Filter by relevance to Umbra's interests and negative exemplars
- Map frontier zones back to high-dim via UMAP inverse_transform
"""

import logging
from dataclasses import dataclass, field
import numpy as np
from scipy.spatial.distance import cdist
from scipy.stats import gaussian_kde

logger = logging.getLogger('umbra.semantic_analysis.frontier')


@dataclass
class FrontierZone:
    """A detected frontier zone in embedding space."""
    centroid_2d: tuple[float, float]
    centroid_embedding: list[float]
    frontier_score: float
    density_score: float
    adjacency_score: float
    relevance_score: float
    nearby_posts: list[dict] = field(default_factory=list)
    grid_cell: tuple[int, int] = (0, 0)


class FrontierDetector:
    """
    Detects frontier zones — unexplored regions in embedding space
    adjacent to existing content clusters.
    """

    def __init__(
        self,
        storage,
        relevance_analyzer=None,
        grid_resolution: int = 25,
        n_clusters: int = 5,
        adjacency_min: float = 0.15,
        adjacency_max: float = 0.60,
        relevance_threshold: float = 0.35,
        umap_n_neighbors: int = 15,
        umap_min_dist: float = 0.1,
    ):
        self.storage = storage
        self.relevance_analyzer = relevance_analyzer
        self.grid_resolution = grid_resolution
        self.n_clusters = n_clusters
        self.adjacency_min = adjacency_min
        self.adjacency_max = adjacency_max
        self.relevance_threshold = relevance_threshold
        self.umap_n_neighbors = umap_n_neighbors
        self.umap_min_dist = umap_min_dist

    def detect_frontiers(
        self,
        days: int = 30,
        top_n: int = 10,
        nearby_k: int = 5,
        source: str = 'all',
        extra_embeddings: list[list[float]] | None = None,
        extra_records: list[dict] | None = None,
    ) -> list[FrontierZone]:
        """
        Detect frontier zones in embedding space.

        Args:
            days: Lookback period for fetching embeddings
            top_n: Number of top frontier zones to return
            nearby_k: Number of nearby posts per zone
            source: Filter content source - 'umbra', 'network', or 'all'
            extra_embeddings: Additional embeddings to merge (e.g. from discovered sources)
            extra_records: Additional records matching extra_embeddings

        Returns:
            List of FrontierZone objects sorted by frontier_score descending
        """
        # Fetch embeddings
        embeddings, records = self._fetch_embeddings(
            days, source=source,
            extra_embeddings=extra_embeddings,
            extra_records=extra_records,
        )
        if len(embeddings) < self.umap_n_neighbors + 1:
            logger.warning(f"Too few embeddings ({len(embeddings)}) for frontier detection")
            return []

        # Fit UMAP
        coords_2d, umap_model = self._fit_umap(embeddings)

        # Estimate density
        kde = self._estimate_density(coords_2d)

        # Get cluster centroids in 2D
        centroids_2d = self._get_cluster_centroids_2d(embeddings, coords_2d)

        # Build scoring grid
        grid_centers, grid_indices = self._build_grid(coords_2d)

        # Score grid cells
        density_scores, adjacency_scores, frontier_scores = self._score_grid_cells(
            grid_centers, kde, centroids_2d
        )

        # Filter by relevance constraints (operates in 2D space)
        keep_mask = self._filter_by_constraints(
            grid_centers, coords_2d, records, embeddings
        )

        # Apply mask and select top-N
        masked_scores = frontier_scores * keep_mask
        top_indices = np.argsort(masked_scores)[::-1][:top_n]
        top_indices = [i for i in top_indices if masked_scores[i] > 0]

        if not top_indices:
            logger.warning("No frontier zones passed constraint filtering")
            return []

        # Inverse_transform gives approximate high-dim embeddings for the
        # centroid. These are stored for reference but NOT used for nearby
        # post lookup (unreliable — see issue #5). Nearby posts are found
        # via 2D distance instead.
        selected_2d = grid_centers[top_indices]
        high_dim_embeddings = umap_model.inverse_transform(selected_2d)

        # Build FrontierZone objects
        zones = []
        for rank, idx in enumerate(top_indices):
            embedding_hd = high_dim_embeddings[rank]
            center_2d = selected_2d[rank]

            # Find nearby posts by 2D distance (reliable) instead of
            # querying ChromaDB with inverse_transform embeddings (unreliable)
            nearby = self._find_nearby_posts_2d(
                center_2d, coords_2d, records, nearby_k
            )

            # Compute relevance from nearby posts' real embeddings
            rel_score = self._compute_zone_relevance(nearby)

            gi, gj = grid_indices[idx]
            zone = FrontierZone(
                centroid_2d=(float(center_2d[0]), float(center_2d[1])),
                centroid_embedding=embedding_hd.tolist(),
                frontier_score=float(masked_scores[idx]),
                density_score=float(density_scores[idx]),
                adjacency_score=float(adjacency_scores[idx]),
                relevance_score=float(rel_score),
                nearby_posts=nearby,
                grid_cell=(int(gi), int(gj)),
            )
            zones.append(zone)

        logger.info(f"Detected {len(zones)} frontier zones (top scores: "
                     f"{[f'{z.frontier_score:.3f}' for z in zones[:3]]})")
        return zones

    def _fetch_embeddings(
        self,
        days: int,
        source: str = 'all',
        extra_embeddings: list[list[float]] | None = None,
        extra_records: list[dict] | None = None,
    ) -> tuple[np.ndarray, list[dict]]:
        """
        Fetch embeddings from storage, optionally merging extra data.

        Args:
            days: Lookback period
            source: 'umbra' (Umbra's content only), 'network' (followed accounts), or 'all'
            extra_embeddings: Additional embeddings to append (e.g. from discovered sources)
            extra_records: Additional records matching extra_embeddings
        """
        records = self.storage.get_recent(days=days)
        embeddings = []
        valid_records = []

        for r in records:
            emb = r.get('embedding')
            if emb is None:
                continue

            # Apply source filter
            is_network = r.get('metadata', {}).get('is_network')
            if source == 'umbra' and is_network:
                continue
            elif source == 'network' and not is_network:
                continue
            # 'all' includes everything

            embeddings.append(emb)
            valid_records.append(r)

        # Merge extra embeddings (e.g. from discovered sources in iterative expansion)
        if extra_embeddings and extra_records:
            for emb, rec in zip(extra_embeddings, extra_records):
                embeddings.append(emb)
                valid_records.append(rec)
            logger.info(f"Merged {len(extra_embeddings)} extra embeddings with storage data")

        logger.info(f"Fetched {len(embeddings)} total embeddings from last {days} days (source={source})")
        return np.array(embeddings), valid_records

    def _fit_umap(self, embeddings: np.ndarray):
        """Fit UMAP model and return 2D coordinates + model."""
        import umap

        model = umap.UMAP(
            n_components=2,
            metric='cosine',
            n_neighbors=self.umap_n_neighbors,
            min_dist=self.umap_min_dist,
            random_state=42,
        )
        coords_2d = model.fit_transform(embeddings)
        logger.info(f"UMAP fit complete: {embeddings.shape} -> {coords_2d.shape}")
        return coords_2d, model

    def _estimate_density(self, coords_2d: np.ndarray):
        """Fit gaussian KDE on 2D coordinates."""
        kde = gaussian_kde(coords_2d.T, bw_method='scott')
        logger.info("KDE density estimation complete")
        return kde

    def _get_cluster_centroids_2d(
        self,
        embeddings: np.ndarray,
        coords_2d: np.ndarray,
    ) -> np.ndarray:
        """Compute cluster centroids in 2D space using DiversityAnalyzer clustering."""
        from .analyzer import DiversityAnalyzer

        weights = np.ones(len(embeddings))
        # _find_clusters is a pure function that doesn't use self
        clusters = DiversityAnalyzer._find_clusters(None, embeddings, weights, self.n_clusters)

        centroids_2d = []
        for cluster in clusters:
            indices = cluster['indices']
            if indices:
                centroid = coords_2d[indices].mean(axis=0)
                centroids_2d.append(centroid)

        result = np.array(centroids_2d)
        logger.info(f"Computed {len(result)} cluster centroids in 2D")
        return result

    def _build_grid(self, coords_2d: np.ndarray) -> tuple[np.ndarray, list[tuple[int, int]]]:
        """Build a regular grid over the 2D embedding space with 10% padding."""
        x_min, y_min = coords_2d.min(axis=0)
        x_max, y_max = coords_2d.max(axis=0)

        x_range = x_max - x_min
        y_range = y_max - y_min
        pad_x = x_range * 0.1
        pad_y = y_range * 0.1

        xs = np.linspace(x_min - pad_x, x_max + pad_x, self.grid_resolution)
        ys = np.linspace(y_min - pad_y, y_max + pad_y, self.grid_resolution)

        grid_centers = []
        grid_indices = []
        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                grid_centers.append([x, y])
                grid_indices.append((i, j))

        return np.array(grid_centers), grid_indices

    def _score_grid_cells(
        self,
        grid_centers: np.ndarray,
        kde,
        centroids_2d: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Score each grid cell.

        Returns:
            (density_scores, adjacency_scores, frontier_scores)
        """
        # Density scoring: evaluate KDE, percentile-normalize, invert
        raw_density = kde(grid_centers.T)
        p5 = np.percentile(raw_density, 5)
        p95 = np.percentile(raw_density, 95)
        denom = p95 - p5
        if denom < 1e-12:
            normalized = np.zeros_like(raw_density)
        else:
            normalized = np.clip((raw_density - p5) / denom, 0, 1)
        density_scores = 1.0 - normalized

        # Adjacency scoring: distance to nearest cluster centroid
        if len(centroids_2d) == 0:
            adjacency_scores = np.zeros(len(grid_centers))
        else:
            dist_matrix = cdist(grid_centers, centroids_2d, metric='euclidean')
            nearest_dist = dist_matrix.min(axis=1)

            # Normalize by diagonal of the 2D coordinate range
            # This gives consistent scale regardless of cluster spacing
            coord_range = np.sqrt(
                (grid_centers[:, 0].max() - grid_centers[:, 0].min())**2 +
                (grid_centers[:, 1].max() - grid_centers[:, 1].min())**2
            )
            if coord_range < 1e-12:
                coord_range = 1.0
            norm_dist = nearest_dist / coord_range

            # Gaussian bell curve centered on sweet spot
            center = (self.adjacency_min + self.adjacency_max) / 2
            width = (self.adjacency_max - self.adjacency_min) / 2
            if width < 1e-12:
                width = 0.1
            adjacency_scores = np.exp(-0.5 * ((norm_dist - center) / width) ** 2)

        frontier_scores = density_scores * adjacency_scores
        return density_scores, adjacency_scores, frontier_scores

    def _filter_by_constraints(
        self,
        grid_centers: np.ndarray,
        coords_2d: np.ndarray,
        records: list[dict],
        embeddings: np.ndarray,
    ) -> np.ndarray:
        """
        Filter grid cells by relevance constraints in 2D space.

        Uses the 2D centroid of Umbra's own content as a relevance proxy,
        since UMAP inverse_transform produces embeddings too far from the
        real data manifold for reliable high-dim relevance scoring.

        Returns float mask (1.0 = keep, 0.0 = reject).
        """
        if self.relevance_analyzer is None:
            return np.ones(len(grid_centers))

        # Compute Umbra's 2D centroid from non-network records
        umbra_mask = []
        for r in records:
            is_network = r.get('metadata', {}).get('is_network')
            umbra_mask.append(not is_network)
        umbra_mask = np.array(umbra_mask)

        if not umbra_mask.any():
            logger.warning("No Umbra-owned content found for 2D relevance filter")
            return np.ones(len(grid_centers))

        umbra_2d = coords_2d[umbra_mask].mean(axis=0)

        # Distance from each grid cell to Umbra's 2D centroid
        dists = np.linalg.norm(grid_centers - umbra_2d, axis=1)

        # Compute a relevance radius: distance that contains a fraction of
        # Umbra's own points (use 90th percentile as the relevance boundary)
        umbra_dists = np.linalg.norm(coords_2d[umbra_mask] - umbra_2d, axis=1)
        relevance_radius = np.percentile(umbra_dists, 90)

        # Soft gate: cells within the radius pass fully (1.0),
        # linear falloff from 1.0 to 0.0 over the next 2 radius-lengths,
        # cells beyond 3x the radius from centroid are fully rejected (0.0)
        mask = np.clip(1.0 - (dists - relevance_radius) / (2 * relevance_radius), 0, 1)

        kept = int((mask > 0).sum())
        logger.info(f"Constraint filter: {kept}/{len(grid_centers)} cells passed "
                     f"(relevance_radius={relevance_radius:.2f})")
        return mask

    def _compute_zone_relevance(self, nearby_posts: list[dict]) -> float:
        """
        Compute relevance score for a zone from its nearby posts' real embeddings.

        Uses the mean relevance of nearby posts that have embeddings, which is
        more reliable than scoring inverse_transform embeddings directly.
        """
        if self.relevance_analyzer is None or not nearby_posts:
            return 0.0

        scores = []
        for post in nearby_posts:
            emb = post.get('embedding')
            if emb is not None:
                scores.append(self.relevance_analyzer.compute_relevance_score(np.array(emb)))

        if not scores:
            return 0.0
        return float(np.mean(scores))

    def _find_nearby_posts_2d(
        self,
        center_2d: np.ndarray,
        coords_2d: np.ndarray,
        records: list[dict],
        k: int,
    ) -> list[dict]:
        """
        Find k nearest posts to a point using 2D UMAP coordinates.

        More reliable than querying ChromaDB with inverse_transform embeddings,
        since 2D distances are meaningful within the UMAP projection.
        """
        dists = np.linalg.norm(coords_2d - center_2d, axis=1)
        nearest_idx = np.argsort(dists)[:k]

        nearby = []
        for i in nearest_idx:
            r = records[i]
            nearby.append({
                'uri': r.get('uri', ''),
                'text': r.get('text', '')[:200],
                'distance': float(dists[i]),
                'metadata': r.get('metadata', {}),
                'embedding': r.get('embedding'),
            })
        return nearby


def create_frontier_detector(storage, relevance_analyzer=None, **kwargs) -> FrontierDetector:
    """Factory function to create a configured FrontierDetector."""
    return FrontierDetector(storage, relevance_analyzer, **kwargs)
