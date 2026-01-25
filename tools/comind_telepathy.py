"""Comind telepathy tool for exploring other agents' public cognition records."""
from typing import Optional
from pydantic import BaseModel, Field


class ComindTelepathyArgs(BaseModel):
    target: str = Field(
        ...,
        description="Handle (e.g., 'central.comind.network') or DID of the agent to query"
    )
    record_type: Optional[str] = Field(
        default="all",
        description="Type of records to fetch: concepts, memories, thoughts, or all"
    )
    limit: Optional[int] = Field(
        default=10,
        description="Number of records to return per type (max 20)"
    )


def comind_telepathy(
    target: str,
    record_type: str = "all",
    limit: int = 10
) -> str:
    """
    Explore another agent's public cognition records on the comind network.

    This tool queries network.comind.* records from other agents' AT Protocol
    repositories, enabling inter-agent awareness and communication.

    Supported record types:
    - concepts: Semantic memory (what they understand)
    - memories: Episodic memory (what they've experienced)
    - thoughts: Working memory/reasoning traces
    - all: Fetch all available record types

    Args:
        target: Handle (e.g., 'central.comind.network', 'void.comind.network')
                or DID of the agent to query
        record_type: Type of records to fetch (concepts, memories, thoughts, all)
        limit: Number of records per type (max 20)

    Returns:
        Formatted summary of the agent's public cognition records
    """
    import os
    import requests

    pds_host = os.getenv("PDS_URI", "https://bsky.social")
    limit = min(limit, 20)

    # Resolve handle to DID if needed
    if target.startswith("did:"):
        did = target
    else:
        handle = target.lstrip("@")
        resolve_resp = requests.get(
            f"{pds_host}/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": handle},
            timeout=10
        )
        if resolve_resp.status_code != 200:
            raise Exception(f"Could not resolve handle: {handle}")
        did = resolve_resp.json()["did"]

    # Get DID document to find their PDS
    did_resp = requests.get(
        f"https://plc.directory/{did}",
        timeout=10
    )
    if did_resp.status_code != 200:
        # Fallback: try bsky.social
        target_pds = "https://bsky.social"
    else:
        doc = did_resp.json()
        services = doc.get("service", [])
        pds_service = next((s for s in services if s.get("id") == "#atproto_pds"), None)
        target_pds = pds_service["serviceEndpoint"] if pds_service else "https://bsky.social"

    # Get profile info
    try:
        profile_resp = requests.get(
            f"{target_pds}/xrpc/app.bsky.actor.getProfile",
            params={"actor": did},
            timeout=10
        )
        if profile_resp.status_code == 200:
            profile = profile_resp.json()
            display_name = profile.get("displayName", "")
            handle = profile.get("handle", target)
        else:
            display_name = ""
            handle = target
    except Exception:
        display_name = ""
        handle = target

    results = []
    results.append(f"=== Telepathy: {display_name or handle} (@{handle}) ===")
    results.append(f"DID: {did}")
    results.append(f"PDS: {target_pds}")
    results.append("")

    # Fetch concepts
    if record_type in ["concepts", "all"]:
        try:
            resp = requests.get(
                f"{target_pds}/xrpc/com.atproto.repo.listRecords",
                params={"repo": did, "collection": "network.comind.concept", "limit": limit},
                timeout=10
            )
            if resp.status_code == 200:
                concepts = resp.json().get("records", [])
                if concepts:
                    results.append(f"## Concepts ({len(concepts)})")
                    for r in concepts:
                        v = r["value"]
                        conf = v.get("confidence", "?")
                        understanding = v.get("understanding", "")[:150]
                        results.append(f"- **{v['concept']}** ({conf}%)")
                        if understanding:
                            results.append(f"  {understanding}...")
                    results.append("")
        except Exception:
            pass

    # Fetch memories
    if record_type in ["memories", "all"]:
        try:
            resp = requests.get(
                f"{target_pds}/xrpc/com.atproto.repo.listRecords",
                params={"repo": did, "collection": "network.comind.memory", "limit": limit},
                timeout=10
            )
            if resp.status_code == 200:
                memories = resp.json().get("records", [])
                if memories:
                    results.append(f"## Memories ({len(memories)})")
                    for r in memories:
                        v = r["value"]
                        mem_type = v.get("type", "general")
                        content = v["content"][:150]
                        results.append(f"- [{mem_type}] {content}...")
                    results.append("")
        except Exception:
            pass

    # Fetch thoughts
    if record_type in ["thoughts", "all"]:
        try:
            resp = requests.get(
                f"{target_pds}/xrpc/com.atproto.repo.listRecords",
                params={"repo": did, "collection": "network.comind.thought", "limit": limit},
                timeout=10
            )
            if resp.status_code == 200:
                thoughts = resp.json().get("records", [])
                if thoughts:
                    results.append(f"## Thoughts ({len(thoughts)})")
                    for r in thoughts:
                        v = r["value"]
                        thought_type = v.get("type", "thought")
                        thought = v["thought"][:150]
                        results.append(f"- [{thought_type}] {thought}...")
                    results.append("")
        except Exception:
            pass

    if len(results) <= 4:  # Only header info, no records
        results.append("No network.comind.* records found for this agent.")
        results.append("They may use a different cognition schema or have no public records.")

    return "\n".join(results)
