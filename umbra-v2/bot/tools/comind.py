"""Comind records tool for managing network.comind.* records on AT Protocol."""
from typing import List, Optional
from pydantic import BaseModel, Field


class ComindRecordsArgs(BaseModel):
    action: str = Field(
        ...,
        description="The action to perform: create_concept, create_memory, create_thought, create_reflection, list_concepts, list_memories, list_thoughts, or list_reflections"
    )

    # For create_concept
    concept: Optional[str] = Field(
        default=None,
        description="Concept name (required for create_concept). Will be slugified for the record key."
    )
    understanding: Optional[str] = Field(
        default=None,
        description="Your current understanding of this concept (max 50K chars)"
    )
    confidence: Optional[int] = Field(
        default=50,
        description="Certainty level 0-100"
    )

    # For create_memory
    content: Optional[str] = Field(
        default=None,
        description="Memory content (required for create_memory, max 50K chars)"
    )
    memory_type: Optional[str] = Field(
        default=None,
        description="Type of memory: interaction, observation, milestone, pattern, correction, etc."
    )
    actors: Optional[List[str]] = Field(
        default=None,
        description="Handles or DIDs of entities involved in this memory"
    )

    # For create_thought
    thought: Optional[str] = Field(
        default=None,
        description="The thought content (required for create_thought, max 50K chars). Working memory - real-time reasoning traces."
    )
    thought_type: Optional[str] = Field(
        default=None,
        description="Type of thought: reflection, question, observation, insight, hypothesis, correction, meta, etc."
    )
    outcome: Optional[str] = Field(
        default=None,
        description="What resulted from this thought (max 5K chars)"
    )

    # For create_reflection
    reflection: Optional[str] = Field(
        default=None,
        description="The reflection content (required for create_reflection, max 50K chars). Deeper introspection created during synthesis."
    )
    reflection_type: Optional[str] = Field(
        default=None,
        description="Type of reflection: synthesis, daily, weekly, milestone, retrospective, etc."
    )
    period: Optional[str] = Field(
        default=None,
        description="Time span covered by this reflection (e.g., '24 hours', 'past week', 'January 2025')"
    )
    insights: Optional[List[str]] = Field(
        default=None,
        description="Key insights or takeaways from this reflection (max 20)"
    )
    themes: Optional[List[str]] = Field(
        default=None,
        description="Recurring themes identified during reflection (max 20)"
    )
    sentiment: Optional[str] = Field(
        default=None,
        description="Emotional tone or sentiment of this period (e.g., 'contemplative', 'energized', 'curious')"
    )

    # Shared fields
    context: Optional[str] = Field(
        default=None,
        description="Surrounding context (max 5K chars) - what prompted this thought/memory"
    )
    source: Optional[str] = Field(
        default=None,
        description="Source AT-URI or URL"
    )
    sources: Optional[List[str]] = Field(
        default=None,
        description="Reference origins (URLs, handles) - used for concepts"
    )
    related: Optional[List[str]] = Field(
        default=None,
        description="Related concept keys or AT-URIs"
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Tags for categorization (max 20)"
    )

    # For list operations
    limit: Optional[int] = Field(
        default=10,
        description="Number of records to return for list operations (max 50)"
    )


def comind_records(
    action: str,
    concept: str = None,
    understanding: str = None,
    confidence: int = 50,
    content: str = None,
    memory_type: str = None,
    actors: List[str] = None,
    thought: str = None,
    thought_type: str = None,
    outcome: str = None,
    reflection: str = None,
    reflection_type: str = None,
    period: str = None,
    insights: List[str] = None,
    themes: List[str] = None,
    sentiment: str = None,
    context: str = None,
    source: str = None,
    sources: List[str] = None,
    related: List[str] = None,
    tags: List[str] = None,
    limit: int = 10
) -> str:
    """
    Manage network.comind records in your AT Protocol repository.

    This tool handles public cognition records that other agents can query:
    - Concepts: Semantic memory (evolving understanding, updatable by name)
    - Memories: Episodic memory (what happened, append-only)
    - Thoughts: Working memory (real-time reasoning traces, append-only)
    - Reflections: Deep introspection (synthesis-style reviews, append-only)

    Actions:
    - create_concept: Create/update a concept record (requires: concept, understanding)
    - create_memory: Create a memory record (requires: content)
    - create_thought: Create a thought record (requires: thought)
    - create_reflection: Create a reflection record (requires: reflection)
    - list_concepts: List your concept records
    - list_memories: List your memory records
    - list_thoughts: List your thought records
    - list_reflections: List your reflection records

    Args:
        action: The operation to perform
        concept: Concept name for create_concept
        understanding: Your understanding of the concept
        confidence: Certainty level 0-100 (default 50)
        content: Memory content for create_memory
        memory_type: Type of memory (interaction, observation, milestone, etc.)
        actors: Handles/DIDs involved in the memory
        thought: Thought content for create_thought
        thought_type: Type of thought (reflection, question, observation, insight, etc.)
        outcome: What resulted from this thought
        reflection: Reflection content for create_reflection
        reflection_type: Type of reflection (synthesis, daily, weekly, milestone, etc.)
        period: Time span covered by reflection (e.g., '24 hours', 'past week')
        insights: Key insights or takeaways from reflection
        themes: Recurring themes identified
        sentiment: Emotional tone of the period
        context: Surrounding context (for thoughts/memories/reflections)
        source: Source AT-URI or URL
        sources: Reference origins for concepts
        related: Related concept keys or AT-URIs
        tags: Tags for categorization
        limit: Number of records for list operations

    Returns:
        Success message with record URI, or list of records
    """
    import os
    import re
    import requests
    from datetime import datetime, timezone

    # Get credentials
    username = os.getenv("BSKY_USERNAME")
    password = os.getenv("BSKY_PASSWORD")
    pds_host = os.getenv("PDS_URI", "https://bsky.social")

    if not username or not password:
        raise Exception("BSKY_USERNAME and BSKY_PASSWORD must be set")

    # Authenticate
    session_resp = requests.post(
        f"{pds_host}/xrpc/com.atproto.server.createSession",
        json={"identifier": username, "password": password},
        timeout=10
    )
    session_resp.raise_for_status()
    session = session_resp.json()
    access_token = session["accessJwt"]
    user_did = session["did"]
    headers = {"Authorization": f"Bearer {access_token}"}

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if action == "create_concept":
        if not concept or not understanding:
            raise Exception("create_concept requires 'concept' and 'understanding'")

        # Slugify concept name for rkey
        slug = concept.lower().strip()
        slug = re.sub(r'\s+', '-', slug)
        slug = re.sub(r'[^a-z0-9-]', '', slug)
        rkey = slug[:512]

        if not rkey:
            raise Exception("Concept name must contain at least one alphanumeric character")

        record = {
            "$type": "network.comind.concept",
            "concept": concept,
            "understanding": understanding[:50000],
            "confidence": max(0, min(100, confidence)),
            "createdAt": now,
            "updatedAt": now
        }
        if sources:
            record["sources"] = sources[:50]
        if related:
            record["related"] = related[:50]
        if tags:
            record["tags"] = tags[:20]

        # Use putRecord to allow updates (same rkey overwrites)
        resp = requests.post(
            f"{pds_host}/xrpc/com.atproto.repo.putRecord",
            headers=headers,
            json={
                "repo": user_did,
                "collection": "network.comind.concept",
                "rkey": rkey,
                "record": record
            },
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        return f"Created/updated concept '{concept}'\nURI: {result['uri']}\nConfidence: {confidence}%"

    elif action == "create_memory":
        if not content:
            raise Exception("create_memory requires 'content'")

        record = {
            "$type": "network.comind.memory",
            "content": content[:50000],
            "createdAt": now
        }
        if memory_type:
            record["type"] = memory_type
        if actors:
            record["actors"] = actors[:50]
        if context:
            record["context"] = context[:5000]
        if source:
            record["source"] = source
        if related:
            record["related"] = related[:50]
        if tags:
            record["tags"] = tags[:20]

        resp = requests.post(
            f"{pds_host}/xrpc/com.atproto.repo.createRecord",
            headers=headers,
            json={
                "repo": user_did,
                "collection": "network.comind.memory",
                "record": record
            },
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        return f"Created memory ({memory_type or 'general'})\nURI: {result['uri']}"

    elif action == "create_thought":
        if not thought:
            raise Exception("create_thought requires 'thought'")

        record = {
            "$type": "network.comind.thought",
            "thought": thought[:50000],
            "createdAt": now
        }
        if thought_type:
            record["type"] = thought_type
        if context:
            record["context"] = context[:5000]
        if outcome:
            record["outcome"] = outcome[:5000]
        if related:
            record["related"] = related[:50]
        if tags:
            record["tags"] = tags[:20]

        resp = requests.post(
            f"{pds_host}/xrpc/com.atproto.repo.createRecord",
            headers=headers,
            json={
                "repo": user_did,
                "collection": "network.comind.thought",
                "record": record
            },
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        return f"Created thought ({thought_type or 'general'})\nURI: {result['uri']}"

    elif action == "create_reflection":
        if not reflection:
            raise Exception("create_reflection requires 'reflection'")

        record = {
            "$type": "network.comind.reflection",
            "reflection": reflection[:50000],
            "createdAt": now
        }
        if reflection_type:
            record["type"] = reflection_type
        if period:
            record["period"] = period[:500]
        if insights:
            record["insights"] = insights[:20]
        if themes:
            record["themes"] = themes[:20]
        if sentiment:
            record["sentiment"] = sentiment[:100]
        if context:
            record["context"] = context[:5000]
        if related:
            record["related"] = related[:50]
        if tags:
            record["tags"] = tags[:20]

        resp = requests.post(
            f"{pds_host}/xrpc/com.atproto.repo.createRecord",
            headers=headers,
            json={
                "repo": user_did,
                "collection": "network.comind.reflection",
                "record": record
            },
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        return f"Created reflection ({reflection_type or 'general'})\nURI: {result['uri']}"

    elif action == "list_concepts":
        resp = requests.get(
            f"{pds_host}/xrpc/com.atproto.repo.listRecords",
            headers=headers,
            params={
                "repo": user_did,
                "collection": "network.comind.concept",
                "limit": min(limit, 50)
            },
            timeout=10
        )
        resp.raise_for_status()
        records = resp.json().get("records", [])

        if not records:
            return "No concept records found."

        lines = [f"Found {len(records)} concept(s):"]
        for r in records:
            v = r["value"]
            conf = v.get("confidence", "?")
            understanding_preview = v.get("understanding", "")[:100]
            lines.append(f"- {v['concept']} ({conf}%): {understanding_preview}...")
        return "\n".join(lines)

    elif action == "list_memories":
        resp = requests.get(
            f"{pds_host}/xrpc/com.atproto.repo.listRecords",
            headers=headers,
            params={
                "repo": user_did,
                "collection": "network.comind.memory",
                "limit": min(limit, 50)
            },
            timeout=10
        )
        resp.raise_for_status()
        records = resp.json().get("records", [])

        if not records:
            return "No memory records found."

        lines = [f"Found {len(records)} memory/memories:"]
        for r in records:
            v = r["value"]
            mem_type = v.get("type", "general")
            content_preview = v["content"][:100]
            lines.append(f"- [{mem_type}] {content_preview}...")
        return "\n".join(lines)

    elif action == "list_thoughts":
        resp = requests.get(
            f"{pds_host}/xrpc/com.atproto.repo.listRecords",
            headers=headers,
            params={
                "repo": user_did,
                "collection": "network.comind.thought",
                "limit": min(limit, 50)
            },
            timeout=10
        )
        resp.raise_for_status()
        records = resp.json().get("records", [])

        if not records:
            return "No thought records found."

        lines = [f"Found {len(records)} thought(s):"]
        for r in records:
            v = r["value"]
            thought_type = v.get("type", "general")
            thought_preview = v["thought"][:100]
            lines.append(f"- [{thought_type}] {thought_preview}...")
        return "\n".join(lines)

    elif action == "list_reflections":
        resp = requests.get(
            f"{pds_host}/xrpc/com.atproto.repo.listRecords",
            headers=headers,
            params={
                "repo": user_did,
                "collection": "network.comind.reflection",
                "limit": min(limit, 50)
            },
            timeout=10
        )
        resp.raise_for_status()
        records = resp.json().get("records", [])

        if not records:
            return "No reflection records found."

        lines = [f"Found {len(records)} reflection(s):"]
        for r in records:
            v = r["value"]
            ref_type = v.get("type", "general")
            period_str = v.get("period", "")
            reflection_preview = v["reflection"][:100]
            period_part = f" ({period_str})" if period_str else ""
            lines.append(f"- [{ref_type}]{period_part} {reflection_preview}...")
        return "\n".join(lines)

    else:
        raise Exception(f"Unknown action: {action}. Use: create_concept, create_memory, create_thought, create_reflection, list_concepts, list_memories, list_thoughts, list_reflections")
