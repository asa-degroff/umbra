"""
SQLite persistence for discovered sources.

Follows the same patterns as notification_db.py for consistency.
"""

import json
import sqlite3
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from .base import DiscoveredSource

logger = logging.getLogger('umbra.source_discovery.source_db')


class SourceDB:
    """SQLite database for persisting discovered sources."""

    def __init__(self, db_path: str = "data/source_discovery.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True, parents=True)
        self.conn = None
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS discovered_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                excerpt TEXT NOT NULL,
                full_text TEXT,
                source_type TEXT NOT NULL DEFAULT 'unknown',
                relevance_score REAL DEFAULT 0.0,
                frontier_zone_id TEXT,
                embedding TEXT,
                discovered_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                query_used TEXT,
                chunk_index INTEGER DEFAULT 0,
                total_chunks INTEGER DEFAULT 1
            )
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_url
            ON discovered_sources(url)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_status
            ON discovered_sources(status)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_frontier_zone
            ON discovered_sources(frontier_zone_id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_discovered_at
            ON discovered_sources(discovered_at DESC)
        """)
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_source_url_chunk
            ON discovered_sources(url, chunk_index)
        """)

        self.conn.commit()

    def save_sources(self, sources: list[DiscoveredSource]) -> int:
        """
        Bulk insert sources, deduplicating by URL + chunk_index.

        Returns:
            Number of newly inserted sources.
        """
        inserted = 0
        with self._lock:
            for source in sources:
                embedding_json = json.dumps(source.embedding) if source.embedding else None
                discovered_at = source.discovered_at.isoformat()

                try:
                    cursor = self.conn.execute("""
                        INSERT OR IGNORE INTO discovered_sources
                        (title, url, excerpt, full_text, source_type, relevance_score,
                         frontier_zone_id, embedding, discovered_at, status,
                         query_used, chunk_index, total_chunks)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        source.title, source.url, source.excerpt, source.full_text,
                        source.source_type, source.relevance_score,
                        source.frontier_zone_id, embedding_json, discovered_at,
                        source.status, source.query_used,
                        source.chunk_index, source.total_chunks,
                    ))
                    if cursor.rowcount > 0:
                        inserted += 1
                except sqlite3.Error as e:
                    logger.error(f"Error saving source {source.url}: {e}")

            self.conn.commit()
        logger.info(f"Saved {inserted}/{len(sources)} new sources to DB")
        return inserted

    def get_sources(
        self,
        status: Optional[str] = None,
        frontier_zone_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DiscoveredSource]:
        """
        Load sources with optional filters.

        Args:
            status: Filter by status (frontier/pending/used/rejected)
            frontier_zone_id: Filter by zone
            limit: Max results
            offset: Pagination offset
        """
        query = "SELECT * FROM discovered_sources"
        params: list = []
        conditions = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if frontier_zone_id is not None:
            conditions.append("frontier_zone_id = ?")
            params.append(frontier_zone_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY discovered_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_source(row) for row in rows]

    def update_status(self, source_id: int, status: str):
        """Change status of a source."""
        with self._lock:
            self.conn.execute(
                "UPDATE discovered_sources SET status = ? WHERE id = ?",
                (status, source_id),
            )
            self.conn.commit()

    def get_by_url(self, url: str) -> list[DiscoveredSource]:
        """Check if a URL has already been discovered."""
        rows = self.conn.execute(
            "SELECT * FROM discovered_sources WHERE url = ? ORDER BY chunk_index",
            (url,),
        ).fetchall()
        return [self._row_to_source(row) for row in rows]

    def get_stats(self) -> dict:
        """Get counts by status."""
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as cnt FROM discovered_sources GROUP BY status"
        ).fetchall()
        stats = {row['status']: row['cnt'] for row in rows}
        total = sum(stats.values())
        stats['total'] = total
        return stats

    def _row_to_source(self, row: sqlite3.Row) -> DiscoveredSource:
        """Convert a database row to a DiscoveredSource."""
        embedding = json.loads(row['embedding']) if row['embedding'] else []
        discovered_at = datetime.fromisoformat(row['discovered_at'])

        source = DiscoveredSource(
            title=row['title'],
            url=row['url'],
            excerpt=row['excerpt'],
            full_text=row['full_text'] or "",
            source_type=row['source_type'],
            relevance_score=row['relevance_score'],
            frontier_zone_id=row['frontier_zone_id'],
            embedding=embedding,
            discovered_at=discovered_at,
            status=row['status'],
            query_used=row['query_used'] or "",
            chunk_index=row['chunk_index'],
            total_chunks=row['total_chunks'],
        )
        source.id = row['id']
        return source

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
