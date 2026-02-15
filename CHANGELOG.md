# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- No source expiration or TTL in source_discovery.db (#56)
- Source discovery is fully synchronous with no timeout (#55)
- No semantic deduplication across providers (#54)
- Only Wikipedia provider implemented (#37)
- Frontier dashboard view with zones scatter chart, sources table, and discovery controls
- Ollama dependency not validated — silent degradation (#17)
- No input validation in SourceDiscovery constructor (#12)

### Fixed
- ArxivProvider and SemanticScholarProvider missing from top-level exports (#57)
- SourceDB read operations lack locking while writes use _lock (#51)
- temporal_weight allows weights > 1.0 for future timestamps (#52)
- UMAP cache key based on only 3 sampled rows is fragile (#50)
- _seed_objects with full embeddings leaked into API-facing cache dict (#49)
- arXiv API called over plain HTTP (#47)
- DiscoveredSource.from_dict crashes on unknown keys (#46)
- evaluate_pending_sources is never called anywhere (#53)
- rounds_completed off-by-one in discovery loop (#45)
- _apply_feedback accumulates duplicate negative exemplars on every call (#44)
- Semantic Scholar 429 handler drops query without retry (#41)
- Semantic Scholar null abstract filtering drops all results (#40)
- Fallback keyword filter drops short meaningful terms (#24)
- NameError if max_rounds=0 — round_num undefined (#19)
- Missing error handling in zone relevance computation (#18)
- Silent failure when embeddings insufficient for UMAP (#16)
- In-run source deduplication missing across zones/rounds (#15)
- JSON parsing fragility from LLM in query generator (#11)
- Fragile text chunking — sentence splitting on '. ' (#10)
- Thread safety in frontier service global state (#8)
- Empty centroid array edge case crashes cdist (#7)
- No embedding validation before UMAP/KDE (#6)
- UMAP inverse_transform unreliability in nearby post lookup (#5)
- Constraint filter math off-by-2x (#4)

### Changed
- Chunking overhead wasted on academic providers with short abstracts (#58)
- Density scoring logic duplicated between seeded and unseeded paths (#48)
- WikipediaProvider.search_with_chunks duplicates base class (#43)
- Query generator prompt biased toward Wikipedia queries (#42)
- Relevance filter operates in 2D space only (#14)
- UMAP refitting on every detect_frontiers() call (#13)
- Frontier classification uses relevance_score not zone membership (#9)
- Adjacency normalization conflates spatial scales (#3)
- Iterative expansion re-runs detect_frontiers() with same data (#2)
- Source persistence: discovered sources only in memory with 5-min cache TTL (#1)
