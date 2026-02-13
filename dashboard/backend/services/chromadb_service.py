"""
ChromaDB Service

Provides access to the semantic analysis ChromaDB database.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger('dashboard.chromadb')

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class ChromaDBService:
    """Service for accessing ChromaDB semantic data."""
    
    def __init__(self, db_path: str = "./data/chromadb"):
        """
        Initialize the ChromaDB service.
        
        Args:
            db_path: Path to ChromaDB storage
        """
        self.db_path = Path(db_path)
        self.client = None
        self.collection = None
        
        if CHROMADB_AVAILABLE and self.db_path.exists():
            try:
                self.client = chromadb.PersistentClient(
                    path=str(self.db_path),
                    settings=Settings(anonymized_telemetry=False),
                )
                self.collection = self.client.get_or_create_collection(
                    name="umbra_content",
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info(f"ChromaDB connected: {self.collection.count()} records")
            except Exception as e:
                logger.warning(f"ChromaDB connection failed: {e}")
    
    @property
    def is_available(self) -> bool:
        """Check if ChromaDB is available."""
        return self.client is not None and self.collection is not None
    
    def get_stats(self) -> dict:
        """Get database statistics."""
        if not self.is_available:
            return {"available": False, "error": "ChromaDB not available"}
        
        try:
            count = self.collection.count()
            return {
                "available": True,
                "total_records": count,
                "db_path": str(self.db_path),
            }
        except Exception as e:
            return {"available": False, "error": str(e)}
    
    def get_records(
        self,
        limit: int = 100,
        offset: int = 0,
        platform: Optional[str] = None,
    ) -> dict:
        """
        Get records from the database.
        
        Args:
            limit: Maximum records to return
            offset: Offset for pagination
            platform: Filter by platform
            
        Returns:
            Dict with records and metadata
        """
        if not self.is_available:
            return {"records": [], "total": 0, "error": "ChromaDB not available"}
        
        try:
            where = {"platform": platform} if platform else None
            
            result = self.collection.get(
                where=where,
                limit=limit,
                offset=offset,
                include=["documents", "metadatas"],
            )
            
            records = []
            for i, uri in enumerate(result.get('ids', [])):
                records.append({
                    "uri": uri,
                    "text": result['documents'][i] if result.get('documents') else None,
                    "metadata": result['metadatas'][i] if result.get('metadatas') else {},
                })
            
            return {
                "records": records,
                "total": self.collection.count(),
                "limit": limit,
                "offset": offset,
            }
        except Exception as e:
            return {"records": [], "total": 0, "error": str(e)}
    
    def get_records_filtered(
        self,
        limit: int = 100,
        offset: int = 0,
        platform: Optional[str] = None,
        collection: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """
        Get records with advanced filtering.
        
        Fetches all records and filters in Python since ChromaDB's
        where clause is limited.
        """
        if not self.is_available:
            return {"records": [], "total": 0, "error": "ChromaDB not available"}
        
        try:
            # Fetch all records (up to 10k)
            result = self.collection.get(
                limit=10000,
                include=["documents", "metadatas"],
            )
            
            records = []
            for i, uri in enumerate(result.get('ids', [])):
                doc = result['documents'][i] if result.get('documents') else ""
                meta = result['metadatas'][i] if result.get('metadatas') else {}
                
                # Apply filters
                if platform and meta.get('platform') != platform:
                    continue
                if collection and meta.get('collection') != collection:
                    continue
                if search and search.lower() not in (doc or "").lower():
                    continue
                if start_date and meta.get('created_at', '') < start_date:
                    continue
                if end_date and meta.get('created_at', '') > end_date:
                    continue
                
                records.append({
                    "uri": uri,
                    "text": doc,
                    "metadata": meta,
                })
            
            # Sort by created_at descending (newest first)
            records.sort(
                key=lambda r: r.get('metadata', {}).get('created_at', ''),
                reverse=True
            )
            
            total_filtered = len(records)
            
            # Apply pagination
            records = records[offset:offset + limit]
            
            return {
                "records": records,
                "total": total_filtered,
                "limit": limit,
                "offset": offset,
            }
        except Exception as e:
            logger.warning(f"Error in get_records_filtered: {e}")
            return {"records": [], "total": 0, "error": str(e)}
    
    def get_embeddings_for_visualization(self, limit: int = 500) -> dict:
        """
        Get embeddings for 2D visualization.
        
        Args:
            limit: Maximum records to return
            
        Returns:
            Dict with embeddings and metadata
        """
        if not self.is_available:
            return {"embeddings": [], "error": "ChromaDB not available"}
        
        try:
            result = self.collection.get(
                limit=limit,
                include=["embeddings", "documents", "metadatas"],
            )
            
            data = []
            embeddings = result.get('embeddings', [])
            documents = result.get('documents', [])
            metadatas = result.get('metadatas', [])
            ids = result.get('ids', [])
            
            for i, uri in enumerate(ids):
                data.append({
                    "uri": uri,
                    "embedding": embeddings[i] if i < len(embeddings) else None,
                    "text": documents[i][:200] if i < len(documents) else None,
                    "platform": metadatas[i].get('platform') if i < len(metadatas) else None,
                    "created_at": metadatas[i].get('created_at') if i < len(metadatas) else None,
                })
            
            return {
                "data": data,
                "total": len(data),
            }
        except Exception as e:
            return {"data": [], "error": str(e)}
