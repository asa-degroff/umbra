"""Re-embed all ChromaDB records with the current embedding model."""
import time
import logging
import sys
import traceback

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s: %(message)s'
)
logger = logging.getLogger('re-embed')

sys.path.insert(0, '/home/asa/umbra')

try:
    from semantic_analysis.storage import SemanticStorage
    from semantic_analysis.embeddings import EmbeddingGenerator

    storage = SemanticStorage()
    embedder = EmbeddingGenerator()

    logger.info(f"Using embedding model: {embedder.model}")

    # Fetch all records
    logger.info("Fetching all records from ChromaDB...")
    data = storage._get_all(include=['documents', 'metadatas'])
    ids = data['ids']
    documents = data['documents']
    metadatas = data['metadatas']
    total = len(ids)
    logger.info(f"Loaded {total} records")

    # Re-embed in batches
    batch_size = 32
    all_embeddings = []
    start = time.time()

    for i in range(0, total, batch_size):
        batch_texts = documents[i:i+batch_size]
        try:
            batch_embs = embedder.embed_batch(batch_texts)
        except Exception as e:
            logger.error(f"Batch {i} failed: {e}")
            # Retry individually
            batch_embs = []
            for t in batch_texts:
                try:
                    batch_embs.append(embedder.embed_single(t))
                except Exception as e2:
                    logger.error(f"Single embed failed: {e2}")
                    raise
        all_embeddings.extend(batch_embs)

        done = min(i + batch_size, total)
        elapsed = time.time() - start
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0

        if done % 320 == 0 or done >= total:
            logger.info(f"Embedded {done}/{total} ({done*100//total}%) - {rate:.1f} rec/s - ETA {eta:.0f}s")
            sys.stdout.flush()

    elapsed = time.time() - start
    logger.info(f"Embedding complete: {total} records in {elapsed:.1f}s ({total/elapsed:.1f} rec/s)")

    # Drop and recreate collection (dimension changed from 4096 to 2560)
    logger.info("Recreating collection with new embedding dimension...")
    storage.clear()

    # Upsert all back in batches
    logger.info("Upserting new embeddings to ChromaDB...")
    for i in range(0, total, batch_size):
        storage.collection.upsert(
            ids=ids[i:i+batch_size],
            embeddings=all_embeddings[i:i+batch_size],
            documents=documents[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size],
        )
        done = min(i + batch_size, total)
        if done % 640 == 0 or done >= total:
            logger.info(f"Upserted {done}/{total}")

    logger.info(f"Done! All {total} records re-embedded with {embedder.model} (dim={len(all_embeddings[0])})")

except Exception:
    logger.error(f"FATAL ERROR:\n{traceback.format_exc()}")
    sys.exit(1)
