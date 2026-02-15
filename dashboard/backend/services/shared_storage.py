"""
Shared SemanticStorage singleton for the dashboard.

All dashboard services should use get_shared_storage() instead of
creating their own SemanticStorage / PersistentClient instances.
Multiple PersistentClient instances on the same ChromaDB path
cause "Error finding id" errors due to HNSW index contention.
"""

import logging
import threading
import sys

sys.path.insert(0, '/home/asa/umbra')

logger = logging.getLogger(__name__)

_storage = None
_lock = threading.Lock()

CHROMADB_PATH = '/home/asa/umbra/data/chromadb'


def get_shared_storage():
    """Get or create the shared SemanticStorage singleton."""
    global _storage

    if _storage is not None:
        return _storage

    with _lock:
        if _storage is not None:
            return _storage

        try:
            from semantic_analysis.storage import SemanticStorage
            _storage = SemanticStorage(CHROMADB_PATH)
            logger.info(f"Shared storage initialized: {_storage.collection.count()} records")
            return _storage
        except Exception as e:
            logger.error(f"Failed to initialize shared storage: {e}")
            return None
