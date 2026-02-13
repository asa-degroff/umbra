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

    def _get_all(self, include: list[str]) -> dict:
        """Fetch all records by paginating in batches of 10,000."""
        all_ids = []
        all_embeddings = []
        all_documents = []
        all_metadatas = []
        batch_size = 10000
        offset = 0

        while True:
            result = self.collection.get(
                include=include,
                limit=batch_size,
                offset=offset,
            )
            ids = result.get('ids', [])
            if not ids:
                break
            all_ids.extend(ids)
            if 'embeddings' in include:
                all_embeddings.extend(result.get('embeddings', []))
            if 'documents' in include:
                all_documents.extend(result.get('documents', []))
            if 'metadatas' in include:
                all_metadatas.extend(result.get('metadatas', []))
            if len(ids) < batch_size:
                break
            offset += batch_size

        out: dict = {'ids': all_ids}
        if 'embeddings' in include:
            out['embeddings'] = all_embeddings
        if 'documents' in include:
            out['documents'] = all_documents
        if 'metadatas' in include:
            out['metadatas'] = all_metadatas
        return out

    def get_existing_uris(self) -> set[str]:
        """Get all URIs currently in storage."""
        # ChromaDB doesn't have a great way to list all IDs efficiently
        # but we can query with a large limit
        try:
            result = self._get_all(include=[])
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
            
            # Network content metadata
            if record.get('source_did'):
                metadata['source_did'] = record['source_did']
            if record.get('source_handle'):
                metadata['source_handle'] = record['source_handle']
            if record.get('is_network'):
                metadata['is_network'] = 1  # ChromaDB needs int, not bool
            
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
            result = self._get_all(include=['embeddings', 'documents', 'metadatas'])
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
    
    def query_batch_neighbors(
        self,
        embeddings: list[list[float]],
        k: int = 5,
    ) -> list[list[float]]:
        """
        Find k-nearest neighbor distances for a batch of embeddings using ChromaDB's native ANN.
        
        This leverages ChromaDB's HNSW index for efficient similarity search instead of
        manual O(n²) pairwise computation.
        
        Args:
            embeddings: List of embedding vectors to query
            k: Number of nearest neighbors per query
            
        Returns:
            List of distance lists (one per embedding). Distances are cosine distances (0=identical, 2=opposite).
        """
        if embeddings is None or len(embeddings) == 0:
            return []
        
        # ChromaDB query supports batch queries
        # Note: Results include self-match at distance 0, so we request k+1
        result = self.collection.query(
            query_embeddings=embeddings,
            n_results=min(k + 1, self.collection.count()),
            include=['distances'],
        )
        
        # Extract distances, excluding self-match (distance ~= 0)
        all_distances = []
        for distances in result.get('distances', []):
            # Filter out self-match (distance < 0.001 for cosine)
            neighbor_distances = [d for d in distances if d > 0.001][:k]
            all_distances.append(neighbor_distances)
        
        return all_distances
    
    def compute_diversity_metrics_ann(
        self,
        sample_size: int = 200,
        k_neighbors: int = 10,
    ) -> dict:
        """
        Compute diversity metrics using ChromaDB's native ANN search.
        
        This is more efficient than manual pairwise computation for large datasets.
        
        Args:
            sample_size: Number of records to sample for analysis
            k_neighbors: Number of neighbors to consider per record
            
        Returns:
            Dict with diversity metrics
        """
        import numpy as np
        
        total_count = self.collection.count()
        if total_count == 0:
            return {'error': 'No records in database'}
        
        # Get a sample of records with embeddings
        actual_sample = min(sample_size, total_count)
        result = self.collection.get(
            limit=actual_sample,
            include=['embeddings', 'metadatas'],
        )
        
        embeddings = result.get('embeddings', [])
        metadatas = result.get('metadatas', [])
        
        if embeddings is None or len(embeddings) == 0:
            return {'error': 'No embeddings found'}
        
        # Query for nearest neighbors using ANN
        neighbor_distances = self.query_batch_neighbors(embeddings, k=k_neighbors)
        
        # Calculate metrics from neighbor distances
        all_neighbor_dists = []
        for dists in neighbor_distances:
            all_neighbor_dists.extend(dists)
        
        if not all_neighbor_dists:
            return {'error': 'Could not compute neighbor distances'}
        
        all_neighbor_dists = np.array(all_neighbor_dists)
        
        # Diversity = average distance to nearest neighbors
        # Higher = more diverse (records are more spread out)
        avg_neighbor_distance = float(np.mean(all_neighbor_dists))
        
        # Local density = inverse of average nearest neighbor distance
        # Lower avg distance = higher density = less diverse locally
        avg_nearest_distance = float(np.mean([dists[0] if dists else 0 for dists in neighbor_distances]))
        
        # Platform distribution
        platforms = {}
        for m in metadatas:
            p = m.get('platform', 'unknown')
            platforms[p] = platforms.get(p, 0) + 1
        
        return {
            'total_records': total_count,
            'sample_size': actual_sample,
            'avg_neighbor_distance': avg_neighbor_distance,
            'avg_nearest_distance': avg_nearest_distance,
            'diversity_score': avg_neighbor_distance,  # Alias for clarity
            'platforms': platforms,
            'k_neighbors': k_neighbors,
            'method': 'ann',
        }
    
    def get_stats(self) -> dict:
        """Get storage statistics."""
        total = self.collection.count()
        
        # Get platform breakdown
        try:
            result = self._get_all(include=['metadatas'])
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
    
    def get_network_content(self, days: int = 7) -> list[dict]:
        """
        Get network content (posts from followed accounts).
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of records where is_network=1
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        try:
            # Query with is_network filter
            result = self.collection.get(
                where={"is_network": 1},
                include=['embeddings', 'documents', 'metadatas'],
                limit=100000,
            )
        except Exception as e:
            logger.error(f"Error querying network content: {e}")
            return []
        
        records = []
        ids = result.get('ids', [])
        embeddings = result.get('embeddings', [])
        documents = result.get('documents', [])
        metadatas = result.get('metadatas', [])
        
        for i, uri in enumerate(ids):
            metadata = metadatas[i] if i < len(metadatas) else {}
            created_at_str = metadata.get('created_at', '')
            
            # Filter by date
            if created_at_str and created_at_str < cutoff_str:
                continue
            
            records.append({
                'uri': uri,
                'text': documents[i] if i < len(documents) else '',
                'embedding': embeddings[i] if i < len(embeddings) else None,
                'metadata': metadata,
                'created_at': created_at_str,
                'source_did': metadata.get('source_did', ''),
                'source_handle': metadata.get('source_handle', ''),
            })
        
        logger.info(f"Retrieved {len(records)} network records from last {days} days")
        return records
    
    def get_umbra_content(self, days: int = 7) -> list[dict]:
        """
        Get Umbra's own content (not network content).
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of records where is_network is not set or is 0
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        try:
            result = self._get_all(include=['embeddings', 'documents', 'metadatas'])
        except Exception as e:
            logger.error(f"Error querying Umbra content: {e}")
            return []
        
        records = []
        ids = result.get('ids', [])
        embeddings = result.get('embeddings', [])
        documents = result.get('documents', [])
        metadatas = result.get('metadatas', [])
        
        for i, uri in enumerate(ids):
            metadata = metadatas[i] if i < len(metadatas) else {}
            
            # Skip network content
            if metadata.get('is_network'):
                continue
            
            created_at_str = metadata.get('created_at', '')
            
            # Filter by date
            if created_at_str and created_at_str < cutoff_str:
                continue
            
            records.append({
                'uri': uri,
                'text': documents[i] if i < len(documents) else '',
                'embedding': embeddings[i] if i < len(embeddings) else None,
                'metadata': metadata,
                'created_at': created_at_str,
            })
        
        logger.info(f"Retrieved {len(records)} Umbra records from last {days} days")
        return records
    
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
