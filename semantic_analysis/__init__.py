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

__all__ = [
    'ATProtoScraper',
    'EmbeddingGenerator', 
    'SemanticStorage',
    'DiversityAnalyzer',
    'run_analysis',
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
    analyzer = DiversityAnalyzer(ollama_url)
    
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
    
    # 5. Analyze diversity
    recent_data = storage.get_recent(days=lookback_days)
    metrics = analyzer.calculate_metrics(recent_data)
    
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
