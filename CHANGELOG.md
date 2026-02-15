# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Only Wikipedia provider implemented (#37)
- Frontier dashboard view with zones scatter chart, sources table, and discovery controls
- Ollama dependency not validated — silent degradation (#17)
- No input validation in SourceDiscovery constructor (#12)

### Fixed
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
- WikipediaProvider.search_with_chunks duplicates base class (#43)
- Query generator prompt biased toward Wikipedia queries (#42)
- Relevance filter operates in 2D space only (#14)
- UMAP refitting on every detect_frontiers() call (#13)
- Frontier classification uses relevance_score not zone membership (#9)
- Adjacency normalization conflates spatial scales (#3)
- Iterative expansion re-runs detect_frontiers() with same data (#2)
- Source persistence: discovered sources only in memory with 5-min cache TTL (#1)
