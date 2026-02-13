#!/usr/bin/env python3
"""
Robust batch backfill script for semantic analysis.
Processes records in batches with checkpointing and resume capability.
"""

import json
import logging
import sys
import time
import traceback
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/umbra-backfill.log'),
    ]
)
logger = logging.getLogger(__name__)

# Flush after each log
for handler in logging.root.handlers:
    handler.flush = lambda: None

from semantic_analysis import ATProtoScraper, EmbeddingGenerator, SemanticStorage, DiversityAnalyzer

BATCH_SIZE = 25  # Smaller batches for reliability
CHECKPOINT_FILE = Path('/tmp/umbra-backfill-checkpoint.json')


def save_checkpoint(processed_uris: set, total_scraped: int):
    """Save progress checkpoint."""
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump({
            'processed_uris': list(processed_uris),
            'total_scraped': total_scraped,
            'timestamp': time.time(),
        }, f)
    logger.info(f"Checkpoint saved: {len(processed_uris)} records processed")


def load_checkpoint() -> set:
    """Load progress from checkpoint."""
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE) as f:
                data = json.load(f)
                logger.info(f"Loaded checkpoint: {len(data.get('processed_uris', []))} already processed")
                return set(data.get('processed_uris', []))
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
    return set()


def main():
    pds_host = 'https://bsky.social'
    did = 'did:plc:oetfdqwocv4aegq2yj6ix4w5'
    chromadb_path = './data/chromadb'
    
    logger.info("=" * 60)
    logger.info("UMBRA SEMANTIC BACKFILL - STARTING")
    logger.info("=" * 60)
    
    # Initialize components
    logger.info("Initializing components...")
    scraper = ATProtoScraper(pds_host, did, access_token=None)
    embedder = EmbeddingGenerator("http://localhost:11434")
    storage = SemanticStorage(chromadb_path)
    analyzer = DiversityAnalyzer("http://localhost:11434")
    
    # Load checkpoint
    checkpoint_uris = load_checkpoint()
    
    # 1. Scrape all records (no limit)
    logger.info("Scraping ALL records from AT Protocol...")
    sys.stdout.flush()
    
    records = scraper.scrape_all(max_per_collection=None)
    logger.info(f"Total records scraped: {len(records)}")
    sys.stdout.flush()
    
    # 2. Filter to new records (not in storage AND not in checkpoint)
    existing_uris = storage.get_existing_uris()
    all_processed = existing_uris | checkpoint_uris
    new_records = [r for r in records if r['uri'] not in all_processed]
    
    logger.info(f"Already in ChromaDB: {len(existing_uris)}")
    logger.info(f"Already in checkpoint: {len(checkpoint_uris)}")
    logger.info(f"New records to process: {len(new_records)}")
    sys.stdout.flush()
    
    if not new_records:
        logger.info("No new records to process!")
    else:
        # 3. Process in batches
        total_batches = (len(new_records) + BATCH_SIZE - 1) // BATCH_SIZE
        processed_this_run = set()
        failed_batches = 0
        
        for i in range(0, len(new_records), BATCH_SIZE):
            batch = new_records[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} records)...")
            sys.stdout.flush()
            
            try:
                # Generate embeddings
                texts = [r['text'] for r in batch]
                start = time.time()
                embeddings = embedder.embed_batch(texts)
                embed_time = time.time() - start
                
                # Store in ChromaDB
                storage.upsert(batch, embeddings)
                store_time = time.time() - start - embed_time
                
                # Track progress
                batch_uris = {r['uri'] for r in batch}
                processed_this_run.update(batch_uris)
                
                elapsed = time.time() - start
                logger.info(f"  Batch {batch_num} complete: {elapsed:.1f}s total ({embed_time:.1f}s embed, {store_time:.1f}s store)")
                sys.stdout.flush()
                
                # Save checkpoint every 5 batches
                if batch_num % 5 == 0:
                    save_checkpoint(checkpoint_uris | processed_this_run, len(records))
                
            except Exception as e:
                logger.error(f"  ERROR in batch {batch_num}: {e}")
                logger.error(traceback.format_exc())
                failed_batches += 1
                sys.stdout.flush()
                
                # If too many failures, abort
                if failed_batches >= 3:
                    logger.error("Too many failures, aborting!")
                    save_checkpoint(checkpoint_uris | processed_this_run, len(records))
                    sys.exit(1)
                
                # Wait and continue
                time.sleep(5)
                continue
        
        # Final checkpoint
        save_checkpoint(checkpoint_uris | processed_this_run, len(records))
        logger.info(f"Processing complete! {len(processed_this_run)} records added this run.")
    
    # 4. Run analysis
    logger.info("Running diversity analysis...")
    sys.stdout.flush()
    
    try:
        recent_data = storage.get_recent(days=30)
        metrics = analyzer.calculate_metrics(recent_data)
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("ANALYSIS COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total records in DB: {len(storage.get_existing_uris())}")
        logger.info(f"Records analyzed (30 days): {metrics.get('records_with_embeddings', 0)}")
        logger.info(f"Diversity score: {metrics.get('weighted_avg_diversity', 0):.3f}")
        logger.info(f"Cluster dominance: {metrics.get('cluster_dominance', 0):.1%}")
        
        # Generate guidance
        guidance = analyzer.generate_guidance(metrics)
        logger.info(f"\nGuidance:\n{guidance}")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        logger.error(traceback.format_exc())
    
    logger.info("")
    logger.info("BACKFILL FINISHED")
    sys.stdout.flush()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
