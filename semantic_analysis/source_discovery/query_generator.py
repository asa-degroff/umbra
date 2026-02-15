"""
Query generator using LLM to create search queries from frontier context.

Uses Qwen 3 14B 4-bit via Ollama.
"""

import logging
import json
import requests
from typing import Optional

logger = logging.getLogger('umbra.source_discovery.query_generator')

DEFAULT_MODEL = "qwen3:14b-q4_K_M"
FALLBACK_MODEL = "qwen2.5:7b"


class QueryGenerator:
    """Generates search queries from frontier zone context using LLM."""
    
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
    ):
        """
        Initialize query generator.
        
        Args:
            ollama_url: Ollama API URL
            model: Model to use (default: qwen3:14b-q4_K_M)
            temperature: Generation temperature
        """
        self.ollama_url = ollama_url.rstrip('/')
        self.model = model
        self.temperature = temperature
        self._verified_model = None
        self.using_fallback = False  # True when LLM is unavailable
    
    def _verify_model(self) -> str:
        """Verify model is available, fall back if needed."""
        if self._verified_model:
            return self._verified_model
        
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.ok:
                models = [m['name'] for m in response.json().get('models', [])]
                
                # Check primary model
                if self.model in models or self.model.split(':')[0] in [m.split(':')[0] for m in models]:
                    self._verified_model = self.model
                    return self.model
                
                # Check fallback
                if FALLBACK_MODEL in models or FALLBACK_MODEL.split(':')[0] in [m.split(':')[0] for m in models]:
                    logger.warning(f"Model {self.model} not found, using fallback {FALLBACK_MODEL}")
                    self._verified_model = FALLBACK_MODEL
                    return FALLBACK_MODEL
                
                # Use first available qwen model
                qwen_models = [m for m in models if 'qwen' in m.lower()]
                if qwen_models:
                    self._verified_model = qwen_models[0]
                    logger.warning(f"Using available model: {self._verified_model}")
                    return self._verified_model
                    
        except Exception as e:
            logger.error(f"Error verifying model: {e}")
        
        # Default to configured model and hope for the best
        self._verified_model = self.model
        return self.model
    
    def generate_queries(
        self,
        nearby_posts: list[dict],
        num_queries: int = 3,
        focus_topics: Optional[list[str]] = None,
        seed_label: Optional[str] = None,
        seed_texts: Optional[list[str]] = None,
    ) -> list[str]:
        """
        Generate search queries based on frontier zone context.

        Args:
            nearby_posts: Posts near the frontier zone (with 'text' field)
            num_queries: Number of queries to generate
            focus_topics: Optional topic hints to guide generation
            seed_label: Optional interest seed label for targeted queries
            seed_texts: Optional representative texts from the seed

        Returns:
            List of search query strings
        """
        if not nearby_posts and not seed_texts:
            return []

        # Build context from nearby posts
        context_texts = []
        for post in nearby_posts[:5]:  # Use up to 5 posts
            text = post.get('text', '')[:300]  # Truncate long posts
            if text:
                context_texts.append(f"- {text}")

        if not context_texts and not seed_texts:
            return []

        context = "\n".join(context_texts) if context_texts else "(no nearby posts)"

        # Build seed context hint
        seed_hint = ""
        if seed_label or seed_texts:
            seed_hint = "\n"
            if seed_label:
                seed_hint += f"This zone is near the topic: {seed_label}\n"
            if seed_texts:
                seed_hint += "Related posts:\n"
                for t in seed_texts[:3]:
                    seed_hint += f"- {t[:300]}\n"

        # Build focus hint
        if focus_topics:
            focus_hint = f"\nFocus areas: {', '.join(focus_topics)}"
        else:
            focus_hint = "\nFocus areas: consciousness, AI systems, emergence, identity, protocols, cognition"

        prompt = f"""You are helping explore the boundaries of a knowledge space. Given these existing posts that represent the edge of explored territory:

{context}
{seed_hint}
Generate {num_queries} diverse search queries to find academic papers and reference articles that explore ADJACENT but UNEXPLORED topics. The queries should:
1. Bridge from the existing content to new but related areas
2. Be specific enough to find relevant results across Wikipedia, arXiv, and academic databases
3. Avoid generic or overly broad terms
4. Focus on concepts, theories, or phenomena (not news or current events)
5. Mix encyclopedic and technical/academic phrasing for broad coverage
{focus_hint}

Return ONLY a JSON array of query strings, no explanation. Example:
["embodied cognition theory", "autopoiesis systems biology", "phenomenal consciousness"]

Queries:"""

        try:
            model = self._verify_model()
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    'model': model,
                    'prompt': prompt,
                    'temperature': self.temperature,
                    'stream': False,
                },
                timeout=120,
            )
            response.raise_for_status()
            
            result = response.json().get('response', '')
            queries = self._parse_queries(result, num_queries)

            if queries:
                self.using_fallback = False
                logger.info(f"Generated {len(queries)} LLM queries: {queries}")
                return queries

            # LLM returned empty/unparseable — fall through to fallback
            logger.warning("LLM returned no parseable queries, using fallback")

        except Exception as e:
            logger.warning(f"LLM query generation failed ({e}), using keyword fallback")

        self.using_fallback = True
        return self._fallback_queries(nearby_posts, num_queries, seed_label=seed_label)
    
    def _parse_queries(self, response: str, expected: int) -> list[str]:
        """Parse LLM response to extract query strings."""
        # Try to find JSON array in response
        response = response.strip()
        
        # Look for JSON array
        start = response.find('[')
        end = response.rfind(']') + 1
        
        if start >= 0 and end > start:
            try:
                queries = json.loads(response[start:end])
                if isinstance(queries, list):
                    # Filter to strings only
                    return [q for q in queries if isinstance(q, str) and q.strip()][:expected]
            except json.JSONDecodeError:
                pass
        
        # Fallback: split by newlines and clean
        lines = response.split('\n')
        queries = []
        for line in lines:
            # Strip list markers and quotes
            line = line.strip()
            line = line.lstrip('0123456789.-•*)> ').strip().strip('"').strip("'").strip()
            if not line:
                continue
            # Reject lines that look like JSON, code, or explanations
            if line.startswith(('{', '[', '//', '#', 'Note', 'Here')):
                continue
            # Must be plausible query length (5-100 chars) with mostly alpha content
            alpha_ratio = sum(c.isalpha() or c.isspace() for c in line) / len(line) if line else 0
            if 5 <= len(line) <= 100 and alpha_ratio > 0.7:
                queries.append(line)

        return queries[:expected]
    
    def _fallback_queries(
        self,
        nearby_posts: list[dict],
        num_queries: int,
        seed_label: Optional[str] = None,
    ) -> list[str]:
        """Generate simple fallback queries from post content."""
        # If we have a seed label, use it directly as the first query
        if seed_label:
            queries = [seed_label]
            if num_queries > 1:
                queries.append(f"{seed_label} research")
            if num_queries > 2:
                queries.append(f"{seed_label} theory")
            return queries[:num_queries]

        # Extract potential keywords from posts
        all_text = " ".join(p.get('text', '')[:200] for p in nearby_posts)
        
        # Keyword extraction: keep words with 3+ chars, excluding stopwords
        stopwords = {
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
            'has', 'her', 'was', 'one', 'our', 'out', 'had', 'hot', 'how',
            'its', 'may', 'who', 'did', 'get', 'him', 'his', 'she', 'any',
            'been', 'have', 'from', 'this', 'that', 'with', 'they', 'what',
            'when', 'will', 'each', 'make', 'like', 'just', 'over', 'such',
            'than', 'them', 'very', 'some', 'also', 'into', 'more', 'about',
            'would', 'there', 'their', 'which', 'could', 'other', 'these',
            'then', 'your', 'only', 'after', 'being', 'those', 'still',
        }
        words = all_text.lower().split()
        keywords = [w for w in words if len(w) > 2 and w.isalpha() and w not in stopwords]
        
        # Take unique keywords
        seen = set()
        unique = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        
        # Create simple queries
        queries = []
        for kw in unique[:num_queries]:
            queries.append(f"{kw} theory")
        
        return queries if queries else ["emergence complex systems", "consciousness philosophy"]


def create_query_generator(
    ollama_url: str = "http://localhost:11434",
    model: Optional[str] = None,
) -> QueryGenerator:
    """Factory function to create a QueryGenerator."""
    return QueryGenerator(
        ollama_url=ollama_url,
        model=model or DEFAULT_MODEL,
    )
