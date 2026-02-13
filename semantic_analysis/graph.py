"""
Social Graph Module

NetworkX-based graph for modeling AT Protocol social connections.
Supports follows, replies, quotes, and mentions as edge types.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Literal
from pathlib import Path
import json

logger = logging.getLogger('umbra.semantic_analysis.graph')

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    logger.warning("NetworkX not installed. Run: pip install networkx")


EdgeType = Literal['follows', 'reply', 'quote', 'mention']


class SocialGraph:
    """
    Graph representation of AT Protocol social connections.
    
    Nodes represent accounts (DIDs), edges represent relationships.
    Edge types: follows, reply, quote, mention
    """
    
    UMBRA_DID = "did:plc:oetfdqwocv4aegq2yj6ix4w5"
    
    def __init__(self, umbra_did: str = UMBRA_DID):
        """
        Initialize the social graph.
        
        Args:
            umbra_did: DID of the central account (Umbra)
        """
        if not NETWORKX_AVAILABLE:
            raise ImportError("NetworkX is required. Run: pip install networkx")
        
        self.umbra_did = umbra_did
        self.graph = nx.DiGraph()  # Directed graph for follows/replies
        
        # Add Umbra as the central node
        self.graph.add_node(
            umbra_did,
            handle="umbra.blue",
            display_name="Umbra",
            is_self=True,
            added_at=datetime.now(timezone.utc).isoformat(),
        )
    
    def add_account(
        self,
        did: str,
        handle: str = "",
        display_name: str = "",
        **metadata
    ) -> None:
        """
        Add an account node to the graph.
        
        Args:
            did: Account DID
            handle: Account handle (e.g., "user.bsky.social")
            display_name: Display name
            **metadata: Additional metadata
        """
        self.graph.add_node(
            did,
            handle=handle,
            display_name=display_name,
            added_at=datetime.now(timezone.utc).isoformat(),
            **metadata
        )
    
    def add_follow(self, follower_did: str, followed_did: str) -> None:
        """
        Add a follow relationship.
        
        Args:
            follower_did: DID of the account doing the following
            followed_did: DID of the account being followed
        """
        self.graph.add_edge(
            follower_did,
            followed_did,
            type='follows',
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    
    def add_interaction(
        self,
        from_did: str,
        to_did: str,
        interaction_type: EdgeType,
        uri: Optional[str] = None,
        **metadata
    ) -> None:
        """
        Add an interaction (reply, quote, mention) to the graph.
        
        Args:
            from_did: DID of the account initiating the interaction
            to_did: DID of the target account
            interaction_type: Type of interaction
            uri: URI of the post (for replies/quotes)
            **metadata: Additional metadata
        """
        # For multi-edges (multiple interactions between same accounts),
        # we store as edge attributes
        edge_key = f"{interaction_type}:{uri or datetime.now().isoformat()}"
        
        if self.graph.has_edge(from_did, to_did):
            # Add to existing edge's interaction list
            edge_data = self.graph.edges[from_did, to_did]
            interactions = edge_data.get('interactions', [])
            interactions.append({
                'type': interaction_type,
                'uri': uri,
                'created_at': datetime.now(timezone.utc).isoformat(),
                **metadata
            })
            self.graph.edges[from_did, to_did]['interactions'] = interactions
        else:
            # Create new edge
            self.graph.add_edge(
                from_did,
                to_did,
                type=interaction_type,
                interactions=[{
                    'type': interaction_type,
                    'uri': uri,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    **metadata
                }],
            )
    
    def get_follows(self, did: Optional[str] = None) -> list[str]:
        """
        Get DIDs of accounts that a given account follows.
        
        Args:
            did: Account DID (defaults to Umbra)
            
        Returns:
            List of followed DIDs
        """
        did = did or self.umbra_did
        return [
            target for target in self.graph.successors(did)
            if self.graph.edges[did, target].get('type') == 'follows'
        ]
    
    def get_followers(self, did: Optional[str] = None) -> list[str]:
        """
        Get DIDs of accounts that follow a given account.
        
        Args:
            did: Account DID (defaults to Umbra)
            
        Returns:
            List of follower DIDs
        """
        did = did or self.umbra_did
        return [
            source for source in self.graph.predecessors(did)
            if self.graph.edges[source, did].get('type') == 'follows'
        ]
    
    def get_account_info(self, did: str) -> Optional[dict]:
        """
        Get account information.
        
        Args:
            did: Account DID
            
        Returns:
            Account metadata dict or None
        """
        if did in self.graph.nodes:
            return dict(self.graph.nodes[did])
        return None
    
    def get_all_accounts(self) -> list[dict]:
        """
        Get all accounts in the graph.
        
        Returns:
            List of account dicts with DID and metadata
        """
        accounts = []
        for did in self.graph.nodes:
            info = dict(self.graph.nodes[did])
            info['did'] = did
            accounts.append(info)
        return accounts
    
    def get_interaction_partners(
        self,
        did: Optional[str] = None,
        interaction_type: Optional[EdgeType] = None,
    ) -> list[dict]:
        """
        Get accounts that a given account has interacted with.
        
        Args:
            did: Account DID (defaults to Umbra)
            interaction_type: Filter by interaction type
            
        Returns:
            List of dicts with target DID and interaction info
        """
        did = did or self.umbra_did
        partners = []
        
        for target in self.graph.successors(did):
            edge = self.graph.edges[did, target]
            edge_type = edge.get('type')
            
            if edge_type == 'follows':
                continue
            
            if interaction_type and edge_type != interaction_type:
                continue
            
            partners.append({
                'did': target,
                'type': edge_type,
                'interactions': edge.get('interactions', []),
                **self.graph.nodes.get(target, {}),
            })
        
        return partners
    
    def build_from_network_scraper(self, network_scraper) -> dict:
        """
        Build graph from NetworkScraper data.
        
        Args:
            network_scraper: NetworkScraper instance
            
        Returns:
            Stats about the build
        """
        # Get follows
        follows = network_scraper.get_follows()
        
        for profile in follows:
            did = profile.get('did')
            if not did:
                continue
            
            # Add account node
            self.add_account(
                did=did,
                handle=profile.get('handle', ''),
                display_name=profile.get('displayName', ''),
                avatar=profile.get('avatar'),
                description=profile.get('description', ''),
            )
            
            # Add follow edge (Umbra follows this account)
            self.add_follow(self.umbra_did, did)
        
        logger.info(f"Built graph with {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        
        return {
            'nodes': self.graph.number_of_nodes(),
            'edges': self.graph.number_of_edges(),
            'follows': len(follows),
        }
    
    def build_from_storage(self, storage) -> dict:
        """
        Build/augment graph from ChromaDB storage metadata.
        
        Extracts source_did from network content to identify unique accounts.
        
        Args:
            storage: SemanticStorage instance
            
        Returns:
            Stats about the build
        """
        network_content = storage.get_network_content(days=30)
        
        seen_dids = set()
        for record in network_content:
            source_did = record.get('source_did')
            source_handle = record.get('source_handle', '')
            
            if not source_did or source_did in seen_dids:
                continue
            
            seen_dids.add(source_did)
            
            # Add account if not exists
            if source_did not in self.graph.nodes:
                self.add_account(
                    did=source_did,
                    handle=source_handle,
                )
                # Assume Umbra follows them (since we have their content)
                self.add_follow(self.umbra_did, source_did)
        
        logger.info(f"Augmented graph from storage: {len(seen_dids)} unique accounts")
        
        return {
            'accounts_from_storage': len(seen_dids),
            'total_nodes': self.graph.number_of_nodes(),
            'total_edges': self.graph.number_of_edges(),
        }
    
    def get_stats(self) -> dict:
        """
        Get graph statistics.
        
        Returns:
            Dict with graph metrics
        """
        follow_edges = sum(
            1 for _, _, d in self.graph.edges(data=True)
            if d.get('type') == 'follows'
        )
        
        return {
            'total_nodes': self.graph.number_of_nodes(),
            'total_edges': self.graph.number_of_edges(),
            'follow_edges': follow_edges,
            'umbra_follows': len(self.get_follows()),
            'umbra_followers': len(self.get_followers()),
            'density': nx.density(self.graph),
        }
    
    def save(self, path: str) -> None:
        """
        Save graph to JSON file.
        
        Args:
            path: File path
        """
        data = nx.node_link_data(self.graph)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Saved graph to {path}")
    
    def load(self, path: str) -> None:
        """
        Load graph from JSON file.
        
        Args:
            path: File path
        """
        with open(path, 'r') as f:
            data = json.load(f)
        self.graph = nx.node_link_graph(data)
        logger.info(f"Loaded graph from {path}: {self.graph.number_of_nodes()} nodes")
    
    def get_content_by_account(self, storage, did: str, days: int = 7) -> list[dict]:
        """
        Get content from a specific account.
        
        Args:
            storage: SemanticStorage instance
            did: Account DID
            days: Look back period
            
        Returns:
            List of records from that account
        """
        network_content = storage.get_network_content(days=days)
        return [r for r in network_content if r.get('source_did') == did]
    
    def get_network_content_summary(self, storage, days: int = 7) -> dict:
        """
        Get summary of content from network accounts.
        
        Args:
            storage: SemanticStorage instance
            days: Look back period
            
        Returns:
            Dict with content counts per account
        """
        network_content = storage.get_network_content(days=days)
        
        by_account = {}
        for record in network_content:
            did = record.get('source_did', 'unknown')
            handle = record.get('source_handle', 'unknown')
            
            if did not in by_account:
                by_account[did] = {
                    'handle': handle,
                    'count': 0,
                    'total_words': 0,
                }
            
            by_account[did]['count'] += 1
            by_account[did]['total_words'] += record.get('metadata', {}).get('word_count', 0)
        
        return {
            'total_accounts': len(by_account),
            'total_posts': len(network_content),
            'by_account': by_account,
        }


def build_umbra_graph(
    network_scraper=None,
    storage=None,
    save_path: Optional[str] = None,
) -> SocialGraph:
    """
    Convenience function to build Umbra's social graph.
    
    Args:
        network_scraper: Optional NetworkScraper instance
        storage: Optional SemanticStorage instance
        save_path: Optional path to save the graph
        
    Returns:
        SocialGraph instance
    """
    graph = SocialGraph()
    
    if network_scraper:
        graph.build_from_network_scraper(network_scraper)
    
    if storage:
        graph.build_from_storage(storage)
    
    if save_path:
        graph.save(save_path)
    
    return graph
