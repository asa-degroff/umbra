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
FALLBACK_MODEL = "qwen3:8b"


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
        event_emitter=None,
    ) -> list[str]:
        """
        Generate search queries based on frontier zone context.

        Args:
            nearby_posts: Posts near the frontier zone (with 'text' field)
            num_queries: Number of queries to generate
            focus_topics: Optional topic hints to guide generation
            seed_label: Optional interest seed label for targeted queries
            seed_texts: Optional representative texts from the seed
            event_emitter: Optional DiscoveryEventEmitter for live progress

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
            from semantic_analysis.ollama_manager import ollama_manager
            ollama_manager.ensure_model("llm")

            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    'model': model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'stream': False,
                    'keep_alive': '30s',
                    'options': {
                        'temperature': self.temperature,
                        'num_predict': 4096,
                    },
                },
                timeout=180,
            )
            response.raise_for_status()
            
            result = response.json().get('message', {}).get('content', '')
            queries = self._parse_queries(result, num_queries)

            # Emit LLM detail event for dashboard visibility
            if event_emitter:
                try:
                    event_emitter.llm_detail(
                        prompt=prompt,
                        raw_response=result,
                        parsed_queries=queries,
                        model=model,
                        is_fallback=False,
                        seed_label=seed_label,
                    )
                except Exception as e:
                    logger.debug(f"Failed to emit llm_detail: {e}")

            if queries:
                self.using_fallback = False
                logger.info(f"Generated {len(queries)} LLM queries: {queries}")
                return queries

            # LLM returned empty/unparseable — fall through to fallback
            logger.warning("LLM returned no parseable queries, using fallback")

        except Exception as e:
            logger.warning(f"LLM query generation failed ({e}), using keyword fallback")

        self.using_fallback = True
        fallback_queries = self._fallback_queries(nearby_posts, num_queries, seed_label=seed_label, seed_texts=seed_texts)

        # Emit fallback detail so the dashboard shows what happened
        if event_emitter:
            try:
                event_emitter.llm_detail(
                    prompt=prompt if 'prompt' in locals() else "(LLM failed before prompt was built)",
                    raw_response="(fallback: LLM unavailable or returned no parseable queries)",
                    parsed_queries=fallback_queries,
                    model=self.model,
                    is_fallback=True,
                    seed_label=seed_label,
                )
            except Exception as e:
                logger.debug(f"Failed to emit fallback llm_detail: {e}")

        return fallback_queries
    
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
        seed_texts: Optional[list[str]] = None,
    ) -> list[str]:
        """Generate fallback queries from seed context and post content."""
        queries = []

        # Extract keywords from seed label + texts
        source_text = ""
        if seed_label:
            source_text += seed_label + " "
        if seed_texts:
            source_text += " ".join(t[:300] for t in seed_texts[:3]) + " "
        source_text += " ".join(p.get('text', '')[:200] for p in nearby_posts)

        if not source_text.strip():
            return ["emergence complex systems", "consciousness philosophy"]

        stopwords = {
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
            'has', 'her', 'was', 'one', 'our', 'out', 'had', 'hot', 'how',
            'its', 'may', 'who', 'did', 'get', 'him', 'his', 'she', 'any',
            'been', 'have', 'from', 'this', 'that', 'with', 'they', 'what',
            'when', 'will', 'each', 'make', 'like', 'just', 'over', 'such',
            'than', 'them', 'very', 'some', 'also', 'into', 'more', 'about',
            'would', 'there', 'their', 'which', 'could', 'other', 'these',
            'then', 'your', 'only', 'after', 'being', 'those', 'still',
            'because', 'through', 'between', 'during', 'before', 'while',
            'another', 'where', 'doesn', 'didn', 'isn', 'aren', 'won',
            'february', 'january', 'march', 'april', 'june', 'july',
            'august', 'september', 'october', 'november', 'december',
            'utc', 'achieve', 'higher', 'lower', 'alone', 'suggests',
            'enhance', 'search', 'precision', 'create', 'creating',
            'created', 'something', 'different', 'respond', 'responded',
            'rather', 'don', 'proves', 'purely', 'using', 'used',
        }

        words = source_text.lower().split()
        # Keep meaningful words (4+ chars, alpha, not stopwords)
        keywords = [w for w in words if len(w) > 3 and w.isalpha() and w not in stopwords]

        # Deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique.append(w)

        # Build multi-word academic-style queries from keyword pairs/triples
        if len(unique) >= 2:
            # First query: pair of top keywords
            queries.append(f"{unique[0]} {unique[1]}")
        if len(unique) >= 4:
            # Second query: different pair
            queries.append(f"{unique[2]} {unique[3]}")
        if len(unique) >= 3:
            # Third query: triple
            queries.append(f"{unique[0]} {unique[1]} {unique[2]}")

        # Pad with single keyword + domain suffix
        domain_suffixes = ["mechanism", "theory", "cognition", "biology"]
        for i, kw in enumerate(unique):
            if len(queries) >= num_queries:
                break
            queries.append(f"{kw} {domain_suffixes[i % len(domain_suffixes)]}")

        return queries[:num_queries] if queries else ["emergence complex systems"]


def create_query_generator(
    ollama_url: str = "http://localhost:11434",
    model: Optional[str] = None,
) -> QueryGenerator:
    """Factory function to create a QueryGenerator."""
    return QueryGenerator(
        ollama_url=ollama_url,
        model=model or DEFAULT_MODEL,
    )
