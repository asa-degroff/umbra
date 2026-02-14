"""
Relevance Analyzer Module

Cross-references Umbra's content with network content to find
relevant topics while filtering out off-topic content.

Key concepts:
- Umbra centroid: Weighted center of Umbra's embedding space
- Relevance score: How close network content is to Umbra's interests
- Negative exemplars: Known off-topic content to filter out
"""

import logging
import numpy as np
from typing import Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger('umbra.semantic_analysis.relevance')


class RelevanceAnalyzer:
    """
    Analyzes relevance of network content to Umbra's interests.
    
    Uses semantic similarity with constraints:
    - Distance from Umbra's centroid (must be close enough)
    - Distance from negative exemplars (must be far enough)
    """
    
    def __init__(
        self,
        storage,
        embedder=None,
        relevance_threshold: float = 0.3,
        negative_threshold: float = 0.85,
    ):
        """
        Initialize the relevance analyzer.
        
        Args:
            storage: SemanticStorage instance
            embedder: EmbeddingGenerator instance (optional, for negative exemplars)
            relevance_threshold: Minimum relevance score (0-1) to consider content relevant
            negative_threshold: Maximum similarity to negative exemplars before filtering
        """
        self.storage = storage
        self.embedder = embedder
        self.relevance_threshold = relevance_threshold
        self.negative_threshold = negative_threshold
        
        # Cache for computed values
        self._umbra_centroid = None
        self._umbra_embeddings = None
        self._negative_exemplars = []
        
    def compute_umbra_centroid(self, days: int = 30) -> np.ndarray:
        """
        Compute the centroid of Umbra's embedding space.
        
        Args:
            days: Look back period for computing centroid
            
        Returns:
            Centroid embedding vector
        """
        umbra_content = self.storage.get_umbra_content(days=days)
        
        if not umbra_content:
            logger.warning("No Umbra content found for centroid computation")
            return None
        
        # Get embeddings for Umbra's content
        uris = [r['uri'] for r in umbra_content]
        result = self.storage.collection.get(
            ids=uris,
            include=['embeddings']
        )
        
        embeddings = result.get('embeddings', [])
        if embeddings is None or len(embeddings) == 0:
            logger.warning("No embeddings found for Umbra content")
            return None
        
        # Compute centroid (mean of all embeddings)
        embeddings_array = np.array(embeddings)
        centroid = np.mean(embeddings_array, axis=0)
        
        # Normalize to unit vector
        centroid = centroid / np.linalg.norm(centroid)
        
        self._umbra_centroid = centroid
        self._umbra_embeddings = embeddings_array
        
        logger.info(f"Computed Umbra centroid from {len(embeddings)} posts")
        return centroid
    
    def add_negative_exemplar(self, text: str) -> None:
        """
        Add a negative exemplar (off-topic content to filter).
        
        Args:
            text: Text content that represents off-topic material
        """
        if not self.embedder:
            raise ValueError("Embedder required to add negative exemplars")
        
        embedding = self.embedder.embed(text)
        self._negative_exemplars.append({
            'text': text[:100],  # Store preview
            'embedding': np.array(embedding),
        })
        logger.info(f"Added negative exemplar: {text[:50]}...")
    
    def add_negative_exemplars_batch(self, texts: list[str]) -> None:
        """
        Add multiple negative exemplars at once.
        
        Args:
            texts: List of off-topic text samples
        """
        if not self.embedder:
            raise ValueError("Embedder required to add negative exemplars")
        
        embeddings = self.embedder.embed_batch(texts)
        for i, text in enumerate(texts):
            self._negative_exemplars.append({
                'text': text[:100],
                'embedding': np.array(embeddings[i]),
            })
        logger.info(f"Added {len(texts)} negative exemplars")
    
    def compute_relevance_score(self, embedding: np.ndarray) -> float:
        """
        Compute relevance score for an embedding.
        
        Score is based on cosine similarity to Umbra's centroid.
        
        Args:
            embedding: Embedding vector to score
            
        Returns:
            Relevance score (0-1), higher = more relevant
        """
        if self._umbra_centroid is None:
            self.compute_umbra_centroid()
        
        if self._umbra_centroid is None:
            return 0.0
        
        # Cosine similarity to centroid
        embedding = np.array(embedding)
        embedding_norm = embedding / np.linalg.norm(embedding)
        similarity = np.dot(embedding_norm, self._umbra_centroid)
        
        # Convert to 0-1 score (similarity ranges -1 to 1)
        score = (similarity + 1) / 2
        
        return float(score)
    
    def is_near_negative_exemplar(self, embedding: np.ndarray) -> bool:
        """
        Check if embedding is too close to any negative exemplar.
        
        Args:
            embedding: Embedding vector to check
            
        Returns:
            True if too close to negative exemplar (should filter)
        """
        if not self._negative_exemplars:
            return False
        
        embedding = np.array(embedding)
        embedding_norm = embedding / np.linalg.norm(embedding)
        
        for exemplar in self._negative_exemplars:
            exemplar_norm = exemplar['embedding'] / np.linalg.norm(exemplar['embedding'])
            similarity = np.dot(embedding_norm, exemplar_norm)
            
            if similarity > self.negative_threshold:
                return True
        
        return False
    
    def analyze_network_content(
        self,
        days: int = 14,
        min_relevance: Optional[float] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Analyze network content for relevance to Umbra's interests.
        
        Args:
            days: Look back period
            min_relevance: Minimum relevance score (defaults to self.relevance_threshold)
            limit: Maximum results to return
            
        Returns:
            List of relevant network posts with scores
        """
        if min_relevance is None:
            min_relevance = self.relevance_threshold
        
        # Ensure centroid is computed
        if self._umbra_centroid is None:
            self.compute_umbra_centroid()
        
        # Get network content
        network_content = self.storage.get_network_content(days=days)
        
        if not network_content:
            logger.warning("No network content found")
            return []
        
        # Get embeddings for network content
        uris = [r['uri'] for r in network_content]
        result = self.storage.collection.get(
            ids=uris,
            include=['embeddings', 'documents', 'metadatas']
        )
        
        embeddings = result.get('embeddings', [])
        documents = result.get('documents', [])
        metadatas = result.get('metadatas', [])
        ids = result.get('ids', [])
        
        # Score each piece of content
        scored_content = []
        for i, uri in enumerate(ids):
            if i >= len(embeddings):
                continue
            
            embedding = embeddings[i]
            relevance = self.compute_relevance_score(embedding)
            
            # Filter by relevance threshold
            if relevance < min_relevance:
                continue
            
            # Filter by negative exemplars
            if self.is_near_negative_exemplar(embedding):
                continue
            
            scored_content.append({
                'uri': uri,
                'text': documents[i] if i < len(documents) else '',
                'metadata': metadatas[i] if i < len(metadatas) else {},
                'relevance_score': relevance,
                'source_handle': metadatas[i].get('source_handle', '') if i < len(metadatas) else '',
            })
        
        # Sort by relevance (highest first)
        scored_content.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        logger.info(f"Found {len(scored_content)} relevant posts from {len(network_content)} network posts")
        
        return scored_content[:limit]
    
    def find_trending_topics(
        self,
        days: int = 7,
        min_relevance: float = 0.4,
        min_posts: int = 3,
    ) -> list[dict]:
        """
        Find trending topics in network content that are relevant to Umbra.
        
        Groups similar posts and identifies common themes.
        
        Args:
            days: Look back period
            min_relevance: Minimum relevance score
            min_posts: Minimum posts to consider a topic "trending"
            
        Returns:
            List of trending topics with representative posts
        """
        # Get relevant network content
        relevant = self.analyze_network_content(days=days, min_relevance=min_relevance, limit=500)
        
        if len(relevant) < min_posts:
            return []
        
        # Get embeddings for clustering
        uris = [r['uri'] for r in relevant]
        result = self.storage.collection.get(ids=uris, include=['embeddings'])
        embeddings = np.array(result.get('embeddings', []))
        
        if len(embeddings) < min_posts:
            return []
        
        # Simple clustering: group by high similarity
        # (More sophisticated clustering could use HDBSCAN)
        clusters = []
        used = set()
        
        for i, emb_i in enumerate(embeddings):
            if i in used:
                continue
            
            cluster = [i]
            used.add(i)
            emb_i_norm = emb_i / np.linalg.norm(emb_i)
            
            for j, emb_j in enumerate(embeddings):
                if j in used:
                    continue
                
                emb_j_norm = emb_j / np.linalg.norm(emb_j)
                similarity = np.dot(emb_i_norm, emb_j_norm)
                
                if similarity > 0.8:  # High similarity threshold for same topic
                    cluster.append(j)
                    used.add(j)
            
            if len(cluster) >= min_posts:
                clusters.append(cluster)
        
        # Build topic summaries
        topics = []
        for cluster in clusters:
            posts = [relevant[i] for i in cluster]
            handles = list(set(p['source_handle'] for p in posts if p['source_handle']))
            avg_relevance = np.mean([p['relevance_score'] for p in posts])
            
            topics.append({
                'post_count': len(posts),
                'avg_relevance': float(avg_relevance),
                'handles': handles[:5],  # Top 5 contributors
                'representative_posts': posts[:3],  # Sample posts
            })
        
        # Sort by post count (most discussed first)
        topics.sort(key=lambda x: x['post_count'], reverse=True)
        
        logger.info(f"Found {len(topics)} trending topics from {len(relevant)} relevant posts")
        
        return topics
    
    def find_relevant_by_account(
        self,
        days: int = 14,
        min_relevance: float = 0.4,
    ) -> dict[str, dict]:
        """
        Group relevant content by source account.
        
        Useful for finding which accounts share the most relevant content.
        
        Args:
            days: Look back period
            min_relevance: Minimum relevance score
            
        Returns:
            Dict mapping handle to account stats
        """
        relevant = self.analyze_network_content(days=days, min_relevance=min_relevance, limit=1000)
        
        by_account = {}
        for post in relevant:
            handle = post.get('source_handle', 'unknown')
            
            if handle not in by_account:
                by_account[handle] = {
                    'handle': handle,
                    'post_count': 0,
                    'total_relevance': 0,
                    'top_posts': [],
                }
            
            by_account[handle]['post_count'] += 1
            by_account[handle]['total_relevance'] += post['relevance_score']
            
            # Keep top 3 posts per account
            if len(by_account[handle]['top_posts']) < 3:
                by_account[handle]['top_posts'].append(post)
        
        # Calculate averages and sort
        for handle in by_account:
            count = by_account[handle]['post_count']
            by_account[handle]['avg_relevance'] = by_account[handle]['total_relevance'] / count
        
        # Sort by average relevance
        sorted_accounts = sorted(
            by_account.values(),
            key=lambda x: x['avg_relevance'],
            reverse=True
        )
        
        return {a['handle']: a for a in sorted_accounts}
    
    def get_stats(self) -> dict:
        """Get analyzer statistics."""
        return {
            'has_centroid': self._umbra_centroid is not None,
            'negative_exemplar_count': len(self._negative_exemplars),
            'relevance_threshold': self.relevance_threshold,
            'negative_threshold': self.negative_threshold,
        }


# Default negative exemplars for common off-topic content
DEFAULT_NEGATIVE_EXEMPLARS = [
    # Politics
    "Breaking news about the election results and political drama",
    "The president announced new policies today amid controversy",
    "Democrats and Republicans clash over the latest bill",
    
    # Personal drama
    "I can't believe my ex did this to me, I'm so upset",
    "Drama in my friend group, someone betrayed my trust",
    "Venting about my terrible day at work with my awful boss",
    
    # Celebrity gossip
    "Celebrity couple spotted together, fans speculate about relationship",
    "Famous actor responds to controversy on social media",
    
    # Sports scores
    "Final score: Team A defeats Team B in overtime thriller",
    "Player traded to new team in blockbuster deal",
    
    # Generic social media noise
    "Like and retweet if you agree! Share with your friends!",
    "Good morning everyone! Hope you have a great day!",
    "Can't believe it's already Friday, this week flew by",
]


def create_relevance_analyzer(
    storage,
    embedder=None,
    use_default_negatives: bool = True,
) -> RelevanceAnalyzer:
    """
    Factory function to create a configured RelevanceAnalyzer.
    
    Args:
        storage: SemanticStorage instance
        embedder: EmbeddingGenerator instance
        use_default_negatives: Whether to add default negative exemplars
        
    Returns:
        Configured RelevanceAnalyzer
    """
    analyzer = RelevanceAnalyzer(storage, embedder)
    
    if use_default_negatives and embedder:
        analyzer.add_negative_exemplars_batch(DEFAULT_NEGATIVE_EXEMPLARS)
    
    return analyzer
