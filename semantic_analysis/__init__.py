"""
Semantic Analysis Module for Umbra

This module provides semantic diversity analysis for Umbra's content output.
It scrapes posts from the AT Protocol, generates embeddings, and provides
guidance to help Umbra avoid repetitive topic loops.
"""

from .scraper import ATProtoScraper
from .embeddings import EmbeddingGenerator
from .storage import SemanticStorage
from .analyzer import DiversityAnalyzer
from .network_scraper import NetworkScraper
from .graph import SocialGraph, build_umbra_graph
from .relevance import RelevanceAnalyzer, create_relevance_analyzer
from .frontier import FrontierDetector, FrontierZone, InsufficientDataError, create_frontier_detector
from .source_discovery import (
    SourceDiscovery,
    create_source_discovery,
    DiscoveredSource,
    DiscoveryResult,
    WikipediaProvider,
    ArxivProvider,
    SemanticScholarProvider,
    QueryGenerator,
    SourceDB,
)
from .seeds import InterestSeed, InterestSeedDetector, create_interest_seed_detector

__all__ = [
    'ATProtoScraper',
    'EmbeddingGenerator',
    'SemanticStorage',
    'DiversityAnalyzer',
    'NetworkScraper',
    'SocialGraph',
    'build_umbra_graph',
    'RelevanceAnalyzer',
    'create_relevance_analyzer',
    'FrontierDetector',
    'FrontierZone',
    'InsufficientDataError',
    'create_frontier_detector',
    'SourceDiscovery',
    'create_source_discovery',
    'DiscoveredSource',
    'DiscoveryResult',
    'WikipediaProvider',
    'ArxivProvider',
    'SemanticScholarProvider',
    'QueryGenerator',
    'SourceDB',
    'InterestSeed',
    'InterestSeedDetector',
    'create_interest_seed_detector',
    'run_analysis',
    'run_network_analysis',
]


def run_analysis(
    pds_host: str,
    did: str,
    access_token: str,
    ollama_url: str = "http://localhost:11434",
    chromadb_path: str = "./data/chromadb",
    lookback_days: int = 7,
    dry_run: bool = False,
) -> dict:
    """
    Run the full semantic analysis pipeline.
    
    Args:
        pds_host: The PDS host URL (e.g., "https://bsky.social")
        did: The DID of the account to analyze
        access_token: Bearer token for authenticated requests
        ollama_url: URL for the Ollama API
        chromadb_path: Path to ChromaDB storage
        lookback_days: Number of days to analyze
        dry_run: If True, don't update anything, just return analysis
        
    Returns:
        dict with keys:
            - summary: Human-readable analysis summary
            - guidance: Actionable guidance for diversification
            - metrics: Raw diversity metrics
            - new_records: Number of new records processed
    """
    # Initialize components
    scraper = ATProtoScraper(pds_host, did, access_token)
    embedder = EmbeddingGenerator(ollama_url)
    storage = SemanticStorage(chromadb_path)
    analyzer = DiversityAnalyzer(ollama_url, storage=storage)  # Pass storage for ANN
    
    # 1. Scrape all records
    records = scraper.scrape_all()
    
    # 2. Filter to new records (not already in storage)
    existing_uris = storage.get_existing_uris()
    new_records = [r for r in records if r['uri'] not in existing_uris]
    
    # 3. Generate embeddings for new records
    if new_records:
        texts = [r['text'] for r in new_records]
        embeddings = embedder.embed_batch(texts)
        
        # 4. Store new records with embeddings
        if not dry_run:
            storage.upsert(new_records, embeddings)
    
    # 5. Analyze diversity using ANN-based metrics (more efficient)
    recent_data = storage.get_recent(days=lookback_days)
    metrics = analyzer.calculate_metrics_ann(recent_data)
    
    # 6. Generate guidance
    guidance = analyzer.generate_guidance(metrics)
    
    # 7. Build summary
    summary = analyzer.format_summary(metrics)
    
    return {
        'summary': summary,
        'guidance': guidance,
        'metrics': metrics,
        'new_records': len(new_records),
        'total_records': len(records),
        'dry_run': dry_run,
    }


def run_network_analysis(
    ollama_url: str = "http://localhost:11434",
    chromadb_path: str = "./data/chromadb",
    max_accounts: int = 50,
    max_posts_per_account: int = 30,
    since_days: int = 7,
    dry_run: bool = False,
) -> dict:
    """
    Run network analysis: scrape followed accounts and index their content.
    
    Args:
        ollama_url: URL for the Ollama API
        chromadb_path: Path to ChromaDB storage
        max_accounts: Maximum accounts to scrape
        max_posts_per_account: Maximum posts per account
        since_days: Look back N days
        dry_run: If True, don't store anything
        
    Returns:
        dict with scraping and indexing stats
    """
    import logging
    logger = logging.getLogger('umbra.semantic_analysis')
    
    # Initialize components
    network_scraper = NetworkScraper()
    embedder = EmbeddingGenerator(ollama_url)
    storage = SemanticStorage(chromadb_path)
    
    # 1. Scrape network content
    logger.info(f"Scraping network (max {max_accounts} accounts, {max_posts_per_account} posts each)...")
    result = network_scraper.scrape_network(
        max_accounts=max_accounts,
        max_posts_per_account=max_posts_per_account,
        since_days=since_days,
    )
    
    posts = result['posts']
    logger.info(f"Scraped {len(posts)} posts from {result['accounts_with_posts']} accounts")
    
    # 2. Filter to new posts (not already in storage)
    existing_uris = storage.get_existing_uris()
    new_posts = [p for p in posts if p['uri'] not in existing_uris]
    logger.info(f"New posts to index: {len(new_posts)} (already have {len(posts) - len(new_posts)})")
    
    # 3. Generate embeddings for new posts
    if new_posts and not dry_run:
        logger.info("Generating embeddings...")
        texts = [p['text'] for p in new_posts]
        embeddings = embedder.embed_batch(texts)
        
        # 4. Store with embeddings
        storage.upsert(new_posts, embeddings)
        logger.info(f"Indexed {len(new_posts)} network posts")
    
    return {
        'accounts_scraped': result['accounts_scraped'],
        'accounts_with_posts': result['accounts_with_posts'],
        'total_posts_scraped': len(posts),
        'new_posts_indexed': len(new_posts) if not dry_run else 0,
        'already_indexed': len(posts) - len(new_posts),
        'since_days': since_days,
        'dry_run': dry_run,
    }
