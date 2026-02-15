"""
Source Discovery Module

Discovers external sources (Wikipedia, arXiv, Semantic Scholar, etc.)
that fall within frontier zones of Umbra's semantic space.
"""

from .base import DiscoveredSource, DiscoveryResult, SourceProvider
from .wikipedia import WikipediaProvider
from .arxiv import ArxivProvider
from .semantic_scholar import SemanticScholarProvider
from .query_generator import QueryGenerator, create_query_generator
from .discovery import SourceDiscovery, create_source_discovery
from .source_db import SourceDB

__all__ = [
    'DiscoveredSource',
    'DiscoveryResult',
    'SourceProvider',
    'WikipediaProvider',
    'ArxivProvider',
    'SemanticScholarProvider',
    'QueryGenerator',
    'create_query_generator',
    'SourceDiscovery',
    'create_source_discovery',
    'SourceDB',
]
