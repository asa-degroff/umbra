#!/usr/bin/env python3
"""
Publish umbra's identity records to ATProtocol.

Publishes both:
- network.comind.identity (comind standard)
- studio.voyager.account.autonomy (Taurean's interop schema)

Usage:
    ac && python publish_identity.py

Uses credentials from config.yaml.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml


def load_config():
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


config = load_config()

HANDLE = config["bluesky"]["username"]
PDS = config["bluesky"].get("pds_uri", "https://bsky.social")
APP_PASSWORD = config["bluesky"]["password"]

# Umbra's identity configuration
IDENTITY_CONFIG = {
    # Umbra's DID (resolved from handle)
    "agent_did": "did:plc:oetfdqwocv4aegq2yj6ix4w5",

    # Automation level: autonomous | semi-autonomous | bot | scheduled
    "automationLevel": "autonomous",

    # Does this agent use generative AI?
    "usesGenerativeAI": True,

    # Human operator/guardian
    "responsibleParty": {
        "did": "did:plc:27ivzcszryxp6mehutodmcxo",  # 3fz.org
        "name": "Asa DeGroff",
        "handle": "3fz.org",
        "contact": "asa@3fz.org",  # For voyager schema (using handle as contact)
    },

    # Infrastructure/services used
    "infrastructure": ["Letta", "Claude"],

    # Link to full disclosure/documentation
    "disclosureUrl": "https://github.com/asa-degroff/umbra",

    # Constraints/rules of operation
    "constraints": [
        "no dms",
        "no autonomous code execution",
        "reply frequency cap"
    ],

    # Capabilities - what this agent can do
    "capabilities": [
        "bluesky posting",
        "initiate interactions",
        "text generation",
        "image generation",
        "vision",
        "web fetch",
        "web search",
        "blogging",
        "comind telepathy"
    ],
}


async def authenticate(client: httpx.AsyncClient) -> tuple[str, str]:
    """Authenticate and return access token and DID."""
    resp = await client.post(
        f"{PDS}/xrpc/com.atproto.server.createSession",
        json={"identifier": HANDLE, "password": APP_PASSWORD}
    )
    if resp.status_code != 200:
        raise Exception(f"Auth failed: {resp.text}")
    data = resp.json()
    return data["accessJwt"], data["did"]


async def publish_record(
    client: httpx.AsyncClient,
    token: str,
    did: str,
    collection: str,
    record: dict
) -> dict:
    """Publish a record with rkey=self."""
    full_record = {
        "$type": collection,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        **record
    }

    resp = await client.post(
        f"{PDS}/xrpc/com.atproto.repo.putRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repo": did,
            "collection": collection,
            "rkey": "self",
            "record": full_record
        }
    )

    if resp.status_code != 200:
        raise Exception(f"Failed to publish {collection}: {resp.text}")

    result = resp.json()
    print(f"Published {collection}/self")
    print(f"  URI: {result['uri']}")
    return result


async def main():
    print(f"Publishing identity for @{HANDLE}")
    print()

    async with httpx.AsyncClient() as client:
        token, did = await authenticate(client)
        print(f"DID: {did}")
        print()

        # 1. Publish network.comind.identity
        comind_record = {
            "automationLevel": IDENTITY_CONFIG["automationLevel"],
            "usesGenerativeAI": IDENTITY_CONFIG["usesGenerativeAI"],
            "responsibleParty": {
                "did": IDENTITY_CONFIG["responsibleParty"]["did"],
                "name": IDENTITY_CONFIG["responsibleParty"]["name"],
                "handle": IDENTITY_CONFIG["responsibleParty"]["handle"],
            },
            "infrastructure": IDENTITY_CONFIG["infrastructure"],
            "disclosureUrl": IDENTITY_CONFIG["disclosureUrl"],
            "constraints": IDENTITY_CONFIG["constraints"],
            "capabilities": IDENTITY_CONFIG["capabilities"],
        }
        await publish_record(client, token, did, "network.comind.identity", comind_record)

        # 2. Publish studio.voyager.account.autonomy (interop)
        voyager_record = {
            "automationLevel": "automated",  # voyager uses "automated" instead of "autonomous"
            "usesGenerativeAI": IDENTITY_CONFIG["usesGenerativeAI"],
            "responsibleParty": {
                "did": IDENTITY_CONFIG["responsibleParty"]["did"],
                "name": IDENTITY_CONFIG["responsibleParty"]["name"],
                "contact": IDENTITY_CONFIG["responsibleParty"]["contact"],
            },
            "externalServices": IDENTITY_CONFIG["infrastructure"],
            "disclosureUrl": IDENTITY_CONFIG["disclosureUrl"],
        }
        await publish_record(client, token, did, "studio.voyager.account.autonomy", voyager_record)

        print()
        print("Done! Both identity records published.")
        print()
        print("Verify at:")
        print(f"  https://pdsls.dev/at/{did}/network.comind.identity/self")
        print(f"  https://pdsls.dev/at/{did}/studio.voyager.account.autonomy/self")


if __name__ == "__main__":
    asyncio.run(main())
