"""
Embedding Generator

Generates text embeddings using Ollama with Qwen3-Embedding-8B.
"""

import logging
from typing import Optional
import requests

logger = logging.getLogger('umbra.semantic_analysis')

DEFAULT_MODEL = "qwen3-embedding:4b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"


class EmbeddingGenerator:
    """Generates embeddings using Ollama."""
    
    def __init__(
        self,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_MODEL,
        batch_size: int = 32,
        timeout: int = 120,
    ):
        """
        Initialize the embedding generator.
        
        Args:
            ollama_url: URL for the Ollama API
            model: Model name for embeddings
            batch_size: Maximum texts per batch request
            timeout: Request timeout in seconds
        """
        self.ollama_url = ollama_url.rstrip('/')
        self.model = model
        self.batch_size = batch_size
        self.timeout = timeout
        self.session = requests.Session()
        self._embedding_dim = None
    
    @property
    def embedding_dim(self) -> int:
        """Get the embedding dimension (cached after first call)."""
        if self._embedding_dim is None:
            # Generate a test embedding to get dimension
            test = self.embed_single("test")
            self._embedding_dim = len(test)
        return self._embedding_dim
    
    def embed_single(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: The text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        try:
            resp = self.session.post(
                f"{self.ollama_url}/api/embed",
                json={
                    "model": self.model,
                    "input": text,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            
            # Ollama returns embeddings in 'embeddings' key as list of lists
            embeddings = data.get('embeddings', [])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            
            raise ValueError(f"No embeddings returned: {data}")
            
        except requests.RequestException as e:
            logger.error(f"Embedding request failed: {e}")
            raise
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_embeddings = self._embed_batch_internal(batch)
            embeddings.extend(batch_embeddings)
            
            if i > 0 and i % (self.batch_size * 5) == 0:
                logger.info(f"Embedded {i}/{len(texts)} texts")
        
        logger.info(f"Generated {len(embeddings)} embeddings")
        return embeddings
    
    def _embed_batch_internal(self, texts: list[str]) -> list[list[float]]:
        """
        Internal batch embedding (single API call).
        
        Ollama's /api/embed supports batch input.
        """
        try:
            resp = self.session.post(
                f"{self.ollama_url}/api/embed",
                json={
                    "model": self.model,
                    "input": texts,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            
            embeddings = data.get('embeddings', [])
            if len(embeddings) != len(texts):
                raise ValueError(
                    f"Embedding count mismatch: got {len(embeddings)}, expected {len(texts)}"
                )

            return embeddings
            
        except requests.RequestException as e:
            logger.error(f"Batch embedding request failed: {e}")
            # Fall back to individual requests
            logger.info("Falling back to individual embedding requests")
            return [self.embed_single(t) for t in texts]
    
    def is_available(self) -> bool:
        """Check if the Ollama server and model are available."""
        try:
            # Check if server is up
            resp = self.session.get(
                f"{self.ollama_url}/api/tags",
                timeout=5,
            )
            resp.raise_for_status()
            
            # Check if our model is loaded
            data = resp.json()
            models = [m.get('name', '') for m in data.get('models', [])]
            
            # Model names might include tags
            model_base = self.model.split(':')[0]
            for m in models:
                if model_base in m:
                    return True
            
            logger.warning(f"Model {self.model} not found in available models: {models}")
            return False
            
        except requests.RequestException as e:
            logger.error(f"Ollama availability check failed: {e}")
            return False


def get_embedder(
    ollama_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_MODEL,
) -> EmbeddingGenerator:
    """
    Get an embedding generator instance.
    
    Args:
        ollama_url: URL for the Ollama API
        model: Model name for embeddings
        
    Returns:
        EmbeddingGenerator instance
    """
    return EmbeddingGenerator(ollama_url, model)
