"""
Semantic Storage

ChromaDB-based storage for embeddings and metadata.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import json

logger = logging.getLogger('umbra.semantic_analysis')

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not installed. Run: pip install chromadb")


class SemanticStorage:
    """ChromaDB-based storage for semantic embeddings."""
    
    COLLECTION_NAME = "umbra_content"
    
    def __init__(self, db_path: str = "./data/chromadb"):
        """
        Initialize the storage.
        
        Args:
            db_path: Path to ChromaDB persistent storage
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError("ChromaDB is required. Run: pip install chromadb")
        
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False),
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        
        logger.info(f"Initialized ChromaDB at {self.db_path} with {self.collection.count()} records")
    
    def get_existing_uris(self) -> set[str]:
        """Get all URIs currently in storage."""
        # ChromaDB doesn't have a great way to list all IDs efficiently
        # but we can query with a large limit
        try:
            result = self.collection.get(
                include=[],  # Don't include embeddings/documents
                limit=100000,
            )
            return set(result.get('ids', []))
        except Exception as e:
            logger.warning(f"Error getting existing URIs: {e}")
            return set()
    
    def upsert(self, records: list[dict], embeddings: list[list[float]]) -> int:
        """
        Insert or update records with embeddings.
        
        Args:
            records: List of record dicts with 'uri', 'text', 'platform', etc.
            embeddings: Corresponding embedding vectors
            
        Returns:
            Number of records upserted
        """
        if not records or not embeddings:
            return 0
        
        if len(records) != len(embeddings):
            raise ValueError(f"Record/embedding count mismatch: {len(records)} vs {len(embeddings)}")
        
        # Prepare data for ChromaDB
        ids = []
        documents = []
        metadatas = []
        
        for record in records:
            ids.append(record['uri'])
            documents.append(record['text'])
            
            # Prepare metadata (ChromaDB requires simple types)
            metadata = {
                'collection': record.get('collection', ''),
                'platform': record.get('platform', ''),
                'word_count': record.get('word_count', 0),
            }
            
            # Store created_at as ISO string
            created_at = record.get('created_at')
            if created_at:
                if isinstance(created_at, datetime):
                    metadata['created_at'] = created_at.isoformat()
                else:
                    metadata['created_at'] = str(created_at)
            
            metadatas.append(metadata)
        
        # Upsert to ChromaDB
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        
        logger.info(f"Upserted {len(records)} records to ChromaDB")
        return len(records)
    
    def get_recent(self, days: int = 7) -> list[dict]:
        """
        Get records from the recent time period.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of dicts with 'uri', 'text', 'embedding', 'metadata'
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        # Query all records and filter by date
        # ChromaDB's where clause is limited, so we fetch all and filter
        try:
            result = self.collection.get(
                include=['embeddings', 'documents', 'metadatas'],
                limit=100000,
            )
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {e}")
            return []
        
        records = []
        ids = result.get('ids', [])
        embeddings = result.get('embeddings', [])
        documents = result.get('documents', [])
        metadatas = result.get('metadatas', [])
        
        for i, uri in enumerate(ids):
            metadata = metadatas[i] if i < len(metadatas) else {}
            created_at_str = metadata.get('created_at', '')
            
            # Filter by date if we have timestamp
            if created_at_str:
                try:
                    # Parse and compare
                    if created_at_str < cutoff_str:
                        continue
                except (ValueError, TypeError):
                    pass
            
            records.append({
                'uri': uri,
                'text': documents[i] if i < len(documents) else '',
                'embedding': embeddings[i] if i < len(embeddings) else None,
                'metadata': metadata,
                'created_at': created_at_str,
            })
        
        logger.info(f"Retrieved {len(records)} records from last {days} days")
        return records
    
    def query_similar(
        self,
        embedding: list[float],
        n: int = 10,
        filter_platform: Optional[str] = None,
    ) -> list[dict]:
        """
        Find similar records by embedding.
        
        Args:
            embedding: Query embedding vector
            n: Number of results
            filter_platform: Optional platform filter
            
        Returns:
            List of similar records with distances
        """
        where = None
        if filter_platform:
            where = {"platform": filter_platform}
        
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=n,
            where=where,
            include=['embeddings', 'documents', 'metadatas', 'distances'],
        )
        
        records = []
        ids = result.get('ids', [[]])[0]
        distances = result.get('distances', [[]])[0]
        documents = result.get('documents', [[]])[0]
        metadatas = result.get('metadatas', [[]])[0]
        embeddings = result.get('embeddings', [[]])[0]
        
        for i, uri in enumerate(ids):
            records.append({
                'uri': uri,
                'text': documents[i] if i < len(documents) else '',
                'embedding': embeddings[i] if i < len(embeddings) else None,
                'metadata': metadatas[i] if i < len(metadatas) else {},
                'distance': distances[i] if i < len(distances) else None,
            })
        
        return records
    
    def get_stats(self) -> dict:
        """Get storage statistics."""
        total = self.collection.count()
        
        # Get platform breakdown
        try:
            result = self.collection.get(
                include=['metadatas'],
                limit=100000,
            )
            metadatas = result.get('metadatas', [])
            
            platforms = {}
            collections = {}
            for m in metadatas:
                p = m.get('platform', 'unknown')
                c = m.get('collection', 'unknown')
                platforms[p] = platforms.get(p, 0) + 1
                collections[c] = collections.get(c, 0) + 1
                
        except Exception:
            platforms = {}
            collections = {}
        
        return {
            'total_records': total,
            'platforms': platforms,
            'collections': collections,
            'db_path': str(self.db_path),
        }
    
    def clear(self) -> int:
        """Clear all records. Returns count of deleted records."""
        count = self.collection.count()
        if count > 0:
            # Delete the collection and recreate
            self.client.delete_collection(self.COLLECTION_NAME)
            self.collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        logger.info(f"Cleared {count} records from ChromaDB")
        return count
