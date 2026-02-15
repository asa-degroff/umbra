"""
Main source discovery loop.

Orchestrates frontier detection, query generation, source fetching,
and iterative expansion.
"""

import logging
from typing import Optional
import numpy as np

from .base import DiscoveredSource, DiscoveryResult, SourceProvider
from .wikipedia import WikipediaProvider
from .arxiv import ArxivProvider
from .semantic_scholar import SemanticScholarProvider
from .query_generator import QueryGenerator
from .source_db import SourceDB

logger = logging.getLogger('umbra.source_discovery.discovery')


class SourceDiscovery:
    """
    Discovers external sources that fall within frontier zones.
    
    Uses an iterative approach:
    1. Detect frontier zones
    2. Generate queries from zone context
    3. Fetch sources and embed them
    4. Classify sources as frontier/pending
    5. Re-detect frontiers with new sources
    6. Repeat until limits reached
    """
    
    def __init__(
        self,
        storage,
        embedder,
        frontier_detector,
        relevance_analyzer=None,
        providers: Optional[list[SourceProvider]] = None,
        query_generator: Optional[QueryGenerator] = None,
        ollama_url: str = "http://localhost:11434",
        source_db: Optional[SourceDB] = None,
    ):
        """
        Initialize source discovery.

        Args:
            storage: SemanticStorage instance
            embedder: EmbeddingGenerator instance
            frontier_detector: FrontierDetector instance
            relevance_analyzer: Optional RelevanceAnalyzer for scoring
            providers: List of source providers (default: Wikipedia)
            query_generator: Optional custom query generator
            ollama_url: Ollama URL for query generation
            source_db: Optional SourceDB for persisting discovered sources
        """
        if storage is None:
            raise ValueError("storage is required")
        if embedder is None:
            raise ValueError("embedder is required")
        if frontier_detector is None:
            raise ValueError("frontier_detector is required")

        self.storage = storage
        self.embedder = embedder
        self.frontier_detector = frontier_detector
        self.relevance_analyzer = relevance_analyzer
        self.source_db = source_db

        self.providers = providers or [
            WikipediaProvider(),
            ArxivProvider(),
            SemanticScholarProvider(),
        ]
        self.query_generator = query_generator or QueryGenerator(ollama_url)
    
    def discover(
        self,
        max_rounds: int = 3,
        max_sources_per_zone: int = 10,
        max_total_sources: int = 50,
        initial_zones: int = 5,
        queries_per_zone: int = 3,
        days: int = 30,
        source: str = 'all',
        chunk_sources: bool = True,
        chunk_size: int = 1500,
        frontier_threshold: float = 0.4,
        seeds: Optional[list] = None,
    ) -> DiscoveryResult:
        """
        Run the source discovery loop.

        Args:
            max_rounds: Maximum expansion rounds
            max_sources_per_zone: Sources to fetch per zone
            max_total_sources: Hard cap on total sources
            initial_zones: Number of frontier zones to start with
            queries_per_zone: Queries to generate per zone
            days: Lookback period for frontier detection
            source: Content source filter ('umbra', 'network', 'all')
            chunk_sources: Whether to chunk long sources
            chunk_size: Characters per chunk
            frontier_threshold: Min relevance to count as "in frontier"
            seeds: Optional list of InterestSeed objects for seed-aware discovery

        Returns:
            DiscoveryResult with categorized sources
        """
        result = DiscoveryResult()
        
        all_sources: list[DiscoveredSource] = []
        all_embeddings: list[np.ndarray] = []  # Parallel to all_sources, for semantic dedup
        explored_zone_ids: set[tuple] = set()  # Track by grid cell
        seen_urls: set[tuple[str, int]] = set()  # (url, chunk_index) dedup within run
        semantic_dedup_threshold = 0.95  # Skip sources with cosine sim > this to any existing
        
        # Initial frontier detection
        if seeds:
            logger.info(f"Starting discovery (seed-aware, {len(seeds)} seeds): "
                       f"max_rounds={max_rounds}, max_sources={max_total_sources}")
        else:
            logger.info(f"Starting discovery: max_rounds={max_rounds}, max_sources={max_total_sources}")

        try:
            current_zones = self.frontier_detector.detect_frontiers(
                days=days,
                top_n=initial_zones,
                source=source,
                seeds=seeds,
            )
        except Exception as e:
            logger.error(f"Initial frontier detection failed: {e}")
            result.errors.append(f"Frontier detection failed: {e}")
            return result
        
        if not current_zones:
            logger.warning("No frontier zones detected")
            return result
        
        logger.info(f"Detected {len(current_zones)} initial frontier zones")
        
        rounds_completed = 0
        for round_num in range(max_rounds):
            logger.info(f"=== Round {round_num + 1}/{max_rounds} ===")

            # Check total source cap
            if len(all_sources) >= max_total_sources:
                logger.info(f"Reached max_total_sources cap ({max_total_sources})")
                result.capped = True
                break
            
            zones_this_round = 0
            
            for zone in current_zones:
                zone_id = zone.grid_cell
                
                if zone_id in explored_zone_ids:
                    continue
                
                if len(all_sources) >= max_total_sources:
                    result.capped = True
                    break
                
                # Generate queries for this zone, enriched with seed context if available
                seed_label = None
                seed_texts = None
                if seeds and zone.seed_id:
                    matching = [s for s in seeds if s.seed_id == zone.seed_id]
                    if matching:
                        seed_label = matching[0].label
                        seed_texts = matching[0].representative_texts

                queries = self.query_generator.generate_queries(
                    zone.nearby_posts,
                    num_queries=queries_per_zone,
                    seed_label=seed_label,
                    seed_texts=seed_texts,
                )
                
                if not queries:
                    logger.debug(f"No queries generated for zone {zone_id}")
                    explored_zone_ids.add(zone_id)
                    continue
                
                # Fetch sources for each query
                zone_sources: list[DiscoveredSource] = []
                sources_remaining = max_sources_per_zone
                
                for query in queries:
                    if sources_remaining <= 0:
                        break
                    
                    for provider in self.providers:
                        try:
                            if chunk_sources:
                                sources = provider.search_with_chunks(
                                    query,
                                    limit=min(3, sources_remaining),
                                    chunk_size=chunk_size,
                                )
                            else:
                                sources = provider.search(
                                    query,
                                    limit=min(3, sources_remaining),
                                )
                            
                            zone_sources.extend(sources)
                            sources_remaining -= len(sources)
                            
                        except Exception as e:
                            logger.error(f"Provider {provider.source_type} error: {e}")
                            result.errors.append(f"{provider.source_type}: {e}")
                
                # Deduplicate against DB
                if self.source_db and zone_sources:
                    unique_sources = []
                    for s in zone_sources:
                        existing = self.source_db.get_by_url(s.url)
                        if not existing:
                            unique_sources.append(s)
                        else:
                            logger.debug(f"Skipping already-discovered URL: {s.url}")
                    zone_sources = unique_sources

                # Deduplicate within this run (across zones/rounds)
                if zone_sources:
                    deduped = []
                    for s in zone_sources:
                        key = (s.url, s.chunk_index)
                        if key not in seen_urls:
                            seen_urls.add(key)
                            deduped.append(s)
                    zone_sources = deduped

                if not zone_sources:
                    explored_zone_ids.add(zone_id)
                    continue

                # Embed sources
                try:
                    texts = [s.excerpt for s in zone_sources]
                    embeddings = self.embedder.embed_batch(texts)
                    semantic_dupes = 0

                    for source_obj, embedding in zip(zone_sources, embeddings):
                        emb_arr = np.array(embedding)
                        source_obj.embedding = embedding
                        source_obj.frontier_zone_id = str(zone_id)

                        # Semantic dedup: skip if too similar to an already-accepted source
                        if all_embeddings:
                            emb_norm = emb_arr / (np.linalg.norm(emb_arr) or 1.0)
                            existing = np.array(all_embeddings)
                            norms = np.linalg.norm(existing, axis=1, keepdims=True)
                            norms[norms == 0] = 1.0
                            existing_norm = existing / norms
                            max_sim = float(np.max(existing_norm @ emb_norm))
                            if max_sim > semantic_dedup_threshold:
                                semantic_dupes += 1
                                continue

                        # Score relevance
                        if self.relevance_analyzer:
                            source_obj.relevance_score = self.relevance_analyzer.compute_relevance_score(
                                emb_arr
                            )

                        # Classify: frontier vs pending
                        if source_obj.relevance_score >= frontier_threshold:
                            source_obj.status = 'frontier'
                            result.frontier_sources.append(source_obj)
                        else:
                            source_obj.status = 'pending'
                            result.pending_sources.append(source_obj)

                        all_sources.append(source_obj)
                        all_embeddings.append(emb_arr)

                    if semantic_dupes:
                        logger.info(f"Semantic dedup: skipped {semantic_dupes} near-duplicate sources")

                except Exception as e:
                    logger.error(f"Embedding error: {e}")
                    result.errors.append(f"Embedding: {e}")

                # Persist to DB
                if self.source_db and zone_sources:
                    self.source_db.save_sources(zone_sources)
                
                explored_zone_ids.add(zone_id)
                zones_this_round += 1
                
                logger.info(f"Zone {zone_id}: {len(zone_sources)} sources "
                           f"({sum(1 for s in zone_sources if s.status == 'frontier')} frontier)")
            
            result.zones_explored = len(explored_zone_ids)
            
            if zones_this_round == 0:
                logger.info("No new zones explored this round")
                break

            rounds_completed += 1

            # Re-detect frontiers for next round (if not last round)
            if round_num < max_rounds - 1 and len(all_sources) < max_total_sources:
                try:
                    # Build extra data from discovered sources so UMAP sees
                    # the new embeddings and can reveal new frontier zones
                    extra_embeddings = [s.embedding for s in all_sources if s.embedding]
                    extra_records = [
                        {
                            'uri': f'discovered:{s.url}',
                            'text': s.excerpt,
                            'embedding': s.embedding,
                            'metadata': {},
                        }
                        for s in all_sources if s.embedding
                    ]

                    logger.info(f"Re-detecting frontiers with {len(extra_embeddings)} "
                               f"discovered source embeddings")

                    new_zones = self.frontier_detector.detect_frontiers(
                        days=days,
                        top_n=initial_zones,
                        source=source,
                        extra_embeddings=extra_embeddings,
                        extra_records=extra_records,
                        seeds=seeds,
                    )

                    # Filter to unexplored zones
                    current_zones = [z for z in new_zones if z.grid_cell not in explored_zone_ids]

                    if not current_zones:
                        logger.info("No new frontier zones to explore")
                        break

                    logger.info(f"Found {len(current_zones)} new zones for next round")

                except Exception as e:
                    logger.error(f"Re-detection failed: {e}")
                    result.errors.append(f"Re-detection: {e}")
                    break
        
        # === Outlier exploration phase ===
        # Directly explore outlier seeds that may not have produced frontier zones
        if seeds and len(all_sources) < max_total_sources:
            outlier_seeds = [s for s in seeds if s.seed_type == "outlier"]
            # Skip outliers that already had zones explored for them
            explored_seed_ids = set()
            for s_obj in all_sources:
                if s_obj.frontier_zone_id:
                    explored_seed_ids.add(s_obj.frontier_zone_id)

            if outlier_seeds:
                logger.info(f"Outlier exploration: {len(outlier_seeds)} outlier seeds to explore")

            for outlier in outlier_seeds:
                if len(all_sources) >= max_total_sources:
                    result.capped = True
                    break

                logger.info(f"Exploring outlier seed: {outlier.label} ({outlier.seed_id})")

                # Generate queries from outlier context
                queries = self.query_generator.generate_queries(
                    [],  # No nearby posts — use seed context only
                    num_queries=queries_per_zone,
                    seed_label=outlier.label,
                    seed_texts=outlier.representative_texts,
                )

                if not queries:
                    logger.debug(f"No queries generated for outlier {outlier.seed_id}")
                    continue

                # Fetch sources
                outlier_sources: list[DiscoveredSource] = []
                sources_remaining = max_sources_per_zone

                for query in queries:
                    if sources_remaining <= 0:
                        break

                    for provider in self.providers:
                        try:
                            if chunk_sources:
                                sources = provider.search_with_chunks(
                                    query,
                                    limit=min(3, sources_remaining),
                                    chunk_size=chunk_size,
                                )
                            else:
                                sources = provider.search(
                                    query,
                                    limit=min(3, sources_remaining),
                                )

                            outlier_sources.extend(sources)
                            sources_remaining -= len(sources)

                        except Exception as e:
                            logger.error(f"Provider {provider.source_type} error (outlier): {e}")
                            result.errors.append(f"{provider.source_type} (outlier): {e}")

                # Deduplicate against DB
                if self.source_db and outlier_sources:
                    unique = []
                    for s in outlier_sources:
                        if not self.source_db.get_by_url(s.url):
                            unique.append(s)
                    outlier_sources = unique

                # Deduplicate within this run
                if outlier_sources:
                    deduped = []
                    for s in outlier_sources:
                        key = (s.url, s.chunk_index)
                        if key not in seen_urls:
                            seen_urls.add(key)
                            deduped.append(s)
                    outlier_sources = deduped

                if not outlier_sources:
                    continue

                # Embed and classify
                try:
                    texts = [s.excerpt for s in outlier_sources]
                    embeddings = self.embedder.embed_batch(texts)
                    semantic_dupes = 0

                    for source_obj, embedding in zip(outlier_sources, embeddings):
                        emb_arr = np.array(embedding)
                        source_obj.embedding = embedding
                        source_obj.frontier_zone_id = f"outlier:{outlier.seed_id}"

                        # Semantic dedup
                        if all_embeddings:
                            emb_norm = emb_arr / (np.linalg.norm(emb_arr) or 1.0)
                            existing = np.array(all_embeddings)
                            norms = np.linalg.norm(existing, axis=1, keepdims=True)
                            norms[norms == 0] = 1.0
                            existing_norm = existing / norms
                            max_sim = float(np.max(existing_norm @ emb_norm))
                            if max_sim > semantic_dedup_threshold:
                                semantic_dupes += 1
                                continue

                        # Score relevance
                        if self.relevance_analyzer:
                            source_obj.relevance_score = self.relevance_analyzer.compute_relevance_score(
                                emb_arr
                            )

                        # Classify
                        if source_obj.relevance_score >= frontier_threshold:
                            source_obj.status = 'frontier'
                            result.frontier_sources.append(source_obj)
                        else:
                            source_obj.status = 'pending'
                            result.pending_sources.append(source_obj)

                        all_sources.append(source_obj)
                        all_embeddings.append(emb_arr)

                    if semantic_dupes:
                        logger.info(f"Outlier semantic dedup: skipped {semantic_dupes} near-duplicates")

                except Exception as e:
                    logger.error(f"Embedding error (outlier): {e}")
                    result.errors.append(f"Embedding (outlier): {e}")

                # Persist
                if self.source_db and outlier_sources:
                    self.source_db.save_sources(outlier_sources)

                logger.info(f"Outlier {outlier.label}: {len(outlier_sources)} sources "
                           f"({sum(1 for s in outlier_sources if s.status == 'frontier')} frontier)")

        result.rounds_completed = rounds_completed
        result.total_sources_found = len(all_sources)

        logger.info(f"Discovery complete: {len(result.frontier_sources)} frontier, "
                   f"{len(result.pending_sources)} pending, "
                   f"{result.zones_explored} zones, {result.rounds_completed} rounds")
        
        return result
    
    def evaluate_pending_sources(
        self,
        pending_sources: list[DiscoveredSource],
        threshold: float = 0.4,
    ) -> tuple[list[DiscoveredSource], list[DiscoveredSource]]:
        """
        Re-evaluate pending sources against current frontiers.
        
        Call this periodically to check if pending sources have
        become relevant as Umbra's content evolves.
        
        Args:
            pending_sources: Sources to re-evaluate
            threshold: Relevance threshold for frontier status
            
        Returns:
            Tuple of (newly_frontier, still_pending)
        """
        if not self.relevance_analyzer:
            return [], pending_sources
        
        # Recompute Umbra centroid with latest data
        self.relevance_analyzer.compute_umbra_centroid(days=30)
        
        newly_frontier = []
        still_pending = []
        
        for source in pending_sources:
            if not source.embedding:
                still_pending.append(source)
                continue
            
            score = self.relevance_analyzer.compute_relevance_score(
                np.array(source.embedding)
            )
            source.relevance_score = score
            
            if score >= threshold:
                source.status = 'frontier'
                newly_frontier.append(source)
            else:
                still_pending.append(source)
        
        logger.info(f"Re-evaluated {len(pending_sources)} pending: "
                   f"{len(newly_frontier)} promoted to frontier")
        
        return newly_frontier, still_pending


def create_source_discovery(
    storage,
    embedder,
    frontier_detector,
    relevance_analyzer=None,
    ollama_url: str = "http://localhost:11434",
    source_db: Optional[SourceDB] = None,
    db_path: Optional[str] = None,
) -> SourceDiscovery:
    """
    Factory function to create a configured SourceDiscovery.

    If neither source_db nor db_path is provided, defaults to
    data/source_discovery.db alongside the ChromaDB path.
    """
    if source_db is None and db_path is not None:
        source_db = SourceDB(db_path)

    return SourceDiscovery(
        storage=storage,
        embedder=embedder,
        frontier_detector=frontier_detector,
        relevance_analyzer=relevance_analyzer,
        ollama_url=ollama_url,
        source_db=source_db,
    )
