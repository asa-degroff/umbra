"""
Base classes and dataclasses for source discovery.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol
from abc import ABC, abstractmethod

# Sentence boundary regex: split after .!? followed by whitespace and
# an uppercase letter (avoids splitting on abbreviations like "Dr. Smith")
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')


@dataclass
class DiscoveredSource:
    """A source discovered through frontier exploration."""

    title: str
    url: str
    excerpt: str                          # Key passage for embedding
    full_text: str = ""                   # Complete text for reference
    source_type: str = "unknown"          # 'wikipedia', 'arxiv', etc.
    relevance_score: float = 0.0
    frontier_zone_id: Optional[str] = None  # None if pending
    seed_id: Optional[str] = None            # Which seed generated this source
    embedding: list[float] = field(default_factory=list)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "pending"               # 'frontier', 'pending', 'used', 'rejected'

    # Metadata
    query_used: str = ""                  # Query that found this source
    chunk_index: int = 0                  # If chunked, which chunk
    total_chunks: int = 1                 # Total chunks from this source

    # User feedback
    user_rating: int = 0                  # -1 = downranked, 0 = unrated, 1 = upranked
    rated_at: Optional[datetime] = None

    # DB tracking (set after persistence)
    id: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        d = {
            'title': self.title,
            'url': self.url,
            'excerpt': self.excerpt,
            'full_text': self.full_text,
            'source_type': self.source_type,
            'relevance_score': self.relevance_score,
            'frontier_zone_id': self.frontier_zone_id,
            'seed_id': self.seed_id,
            'embedding': self.embedding,
            'discovered_at': self.discovered_at.isoformat(),
            'status': self.status,
            'query_used': self.query_used,
            'chunk_index': self.chunk_index,
            'total_chunks': self.total_chunks,
            'user_rating': self.user_rating,
            'rated_at': self.rated_at.isoformat() if self.rated_at else None,
        }
        if self.id is not None:
            d['id'] = self.id
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'DiscoveredSource':
        """Create from dict, ignoring unknown keys."""
        import dataclasses
        known_fields = {f.name for f in dataclasses.fields(cls)}
        data = {k: v for k, v in data.items() if k in known_fields}
        if isinstance(data.get('discovered_at'), str):
            data['discovered_at'] = datetime.fromisoformat(data['discovered_at'])
        if isinstance(data.get('rated_at'), str):
            data['rated_at'] = datetime.fromisoformat(data['rated_at'])
        return cls(**data)


class SourceProvider(ABC):
    """Abstract base class for external source providers."""
    
    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier (e.g., 'wikipedia', 'arxiv')."""
        pass
    
    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[DiscoveredSource]:
        """
        Search for sources matching the query.
        
        Args:
            query: Search query string
            limit: Maximum results to return
            
        Returns:
            List of DiscoveredSource objects (without embeddings)
        """
        pass
    
    def search_with_chunks(self, query: str, limit: int = 5, chunk_size: int = 1500) -> list[DiscoveredSource]:
        """
        Search and return chunked sources for long articles.

        Each chunk becomes a separate DiscoveredSource for individual embedding.
        Subclasses can override for provider-specific chunking.
        """
        sources = self.search(query, limit)
        chunked_sources = []

        for source in sources:
            # Skip chunking when full text fits in a single chunk
            if len(source.full_text) <= chunk_size:
                chunked_sources.append(source)
                continue

            chunks = self.chunk_text(source.full_text, chunk_size)

            for i, chunk in enumerate(chunks):
                chunked = DiscoveredSource(
                    title=source.title,
                    url=source.url,
                    excerpt=chunk,
                    full_text=source.full_text,
                    source_type=source.source_type,
                    query_used=source.query_used,
                    chunk_index=i,
                    total_chunks=len(chunks),
                )
                chunked_sources.append(chunked)

        return chunked_sources

    def chunk_text(self, text: str, max_chars: int = 1500) -> list[str]:
        """
        Split long text into chunks for embedding.
        
        Args:
            text: Full text to chunk
            max_chars: Maximum characters per chunk
            
        Returns:
            List of text chunks
        """
        if len(text) <= max_chars:
            return [text]
        
        # Split on paragraph boundaries
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            if len(current_chunk) + len(para) + 2 <= max_chars:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                
                # If single paragraph is too long, split on sentence boundaries
                if len(para) > max_chars:
                    sentences = _SENTENCE_SPLIT_RE.split(para)
                    current_chunk = ""
                    for sent in sentences:
                        if len(current_chunk) + len(sent) + 1 <= max_chars:
                            if current_chunk:
                                current_chunk += " " + sent
                            else:
                                current_chunk = sent
                        else:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = sent
                else:
                    current_chunk = para
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [text[:max_chars]]


@dataclass
class DiscoveryResult:
    """Result of a source discovery run."""
    
    frontier_sources: list[DiscoveredSource] = field(default_factory=list)
    pending_sources: list[DiscoveredSource] = field(default_factory=list)
    rejected_sources: list[DiscoveredSource] = field(default_factory=list)
    zones_explored: int = 0
    rounds_completed: int = 0
    total_sources_found: int = 0
    capped: bool = False
    errors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            'frontier_sources': [s.to_dict() for s in self.frontier_sources],
            'pending_sources': [s.to_dict() for s in self.pending_sources],
            'rejected_sources': [s.to_dict() for s in self.rejected_sources],
            'zones_explored': self.zones_explored,
            'rounds_completed': self.rounds_completed,
            'total_sources_found': self.total_sources_found,
            'capped': self.capped,
            'errors': self.errors,
        }
