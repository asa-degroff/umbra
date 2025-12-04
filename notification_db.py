#!/usr/bin/env python3
"""SQLite database for robust notification tracking."""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Set, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class NotificationDB:
    """Database for tracking notification processing state."""
    
    def __init__(self, db_path: str = "queue/notifications.db"):
        """Initialize the notification database."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True, parents=True)
        self.conn = None
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        # Create main notifications table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                uri TEXT PRIMARY KEY,
                indexed_at TEXT NOT NULL,
                processed_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                reason TEXT,
                author_handle TEXT,
                author_did TEXT,
                text TEXT,
                parent_uri TEXT,
                root_uri TEXT,
                error TEXT,
                metadata TEXT,
                retry_count INTEGER DEFAULT 0,
                last_retry_at TEXT,
                debounce_until TEXT,
                debounce_reason TEXT,
                thread_chain_id TEXT,
                auto_debounced INTEGER DEFAULT 0,
                high_traffic_thread INTEGER DEFAULT 0
            )
        """)
        
        # Create indexes for faster lookups
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_indexed_at 
            ON notifications(indexed_at DESC)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_status 
            ON notifications(status)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_author_handle
            ON notifications(author_handle)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_debounce_until
            ON notifications(debounce_until)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_root_uri
            ON notifications(root_uri)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_parent_uri
            ON notifications(parent_uri)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_thread_chain_id
            ON notifications(thread_chain_id)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_root_uri_indexed_at
            ON notifications(root_uri, indexed_at)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_auto_debounced
            ON notifications(auto_debounced)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_high_traffic_thread
            ON notifications(high_traffic_thread)
        """)

        # Create session tracking table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                last_seen_at TEXT,
                notifications_processed INTEGER DEFAULT 0,
                notifications_skipped INTEGER DEFAULT 0,
                notifications_error INTEGER DEFAULT 0
            )
        """)

        # Create thread state table for debounce state machine
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS thread_state (
                root_uri TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                debounce_until TEXT,
                debounce_started_at TEXT,
                cooldown_until TEXT,
                notification_count INTEGER DEFAULT 0,
                last_notification_at TEXT,
                updated_at TEXT
            )
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_thread_state_debounce
            ON thread_state(state, debounce_until)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_thread_state_cooldown
            ON thread_state(state, cooldown_until)
        """)

        # Create thread batch history table (persists independently of thread_state)
        # This tracks what posts were sent to the agent in previous batches
        # so subsequent batches only include NEW posts
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS thread_batch_history (
                root_uri TEXT PRIMARY KEY,
                last_batch_processed_at TEXT,
                last_batch_newest_post_indexed_at TEXT
            )
        """)

        self.conn.commit()
    
    def add_notification(self, notif_dict: Dict) -> str:
        """
        Add a notification to the database atomically.

        Returns:
            "added" - Successfully added new notification
            "duplicate" - Notification already exists in database
            "error" - Failed to add due to error
        """
        try:
            # Handle None input
            if not notif_dict:
                logger.error("add_notification called with empty notif_dict")
                return "error"

            # Extract key fields
            uri = notif_dict.get('uri', '')
            if not uri:
                logger.error("add_notification called with missing URI")
                return "error"

            # Use BEGIN IMMEDIATE to acquire write lock immediately
            # This prevents race conditions when checking and inserting
            self.conn.execute("BEGIN IMMEDIATE")

            try:
                # Check if already exists (within the transaction)
                cursor = self.conn.execute("""
                    SELECT uri FROM notifications WHERE uri = ?
                """, (uri,))
                if cursor.fetchone():
                    self.conn.rollback()
                    logger.debug(f"Notification already in database: {uri}")
                    return "duplicate"

                indexed_at = notif_dict.get('indexed_at', '')
                reason = notif_dict.get('reason', '')
                author = notif_dict.get('author', {}) if notif_dict.get('author') else {}
                author_handle = author.get('handle', '') if author else ''
                author_did = author.get('did', '') if author else ''

                # Extract text from record if available (handle None records)
                record = notif_dict.get('record') or {}
                text = record.get('text', '')[:500] if record else ''

                # Extract thread info
                parent_uri = None
                root_uri = None
                if record and 'reply' in record and record['reply']:
                    reply_info = record['reply']
                    if reply_info and isinstance(reply_info, dict):
                        parent_info = reply_info.get('parent', {})
                        root_info = reply_info.get('root', {})
                        if parent_info:
                            parent_uri = parent_info.get('uri')
                        if root_info:
                            root_uri = root_info.get('uri')

                # If no root_uri in reply info, this notification IS the root
                # This matches the logic in save_notification_to_queue() for deduplication
                if not root_uri:
                    root_uri = uri

                # Store additional metadata as JSON
                metadata = {
                    'cid': notif_dict.get('cid'),
                    'labels': notif_dict.get('labels', []),
                    'is_read': notif_dict.get('is_read', False)
                }

                self.conn.execute("""
                    INSERT INTO notifications
                    (uri, indexed_at, reason, author_handle, author_did, text,
                     parent_uri, root_uri, status, metadata, retry_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, 0)
                """, (uri, indexed_at, reason, author_handle, author_did, text,
                      parent_uri, root_uri, json.dumps(metadata)))

                self.conn.commit()
                return "added"

            except Exception as e:
                self.conn.rollback()
                raise

        except Exception as e:
            logger.error(f"Error adding notification to DB ({uri if 'uri' in locals() else 'unknown'}): {type(e).__name__}: {e}")
            return "error"

    def get_notification(self, uri: str) -> Optional[Dict]:
        """
        Get a notification by URI.

        Args:
            uri: Notification URI to look up

        Returns:
            Dict with notification data if found, None otherwise
        """
        try:
            cursor = self.conn.execute("""
                SELECT * FROM notifications WHERE uri = ?
            """, (uri,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting notification from DB: {e}")
            return None

    def is_processed(self, uri: str) -> bool:
        """Check if a notification has been processed."""
        cursor = self.conn.execute("""
            SELECT status FROM notifications WHERE uri = ?
        """, (uri,))
        row = cursor.fetchone()

        if row:
            return row['status'] in ['processed', 'ignored', 'no_reply', 'in_progress']
        return False

    def has_notification_for_root(self, root_uri: str) -> Optional[Dict]:
        """
        Check if there's already a notification for the same thread root.

        Returns the existing notification dict if found, None otherwise.
        Prioritizes 'mention' notifications over 'reply' notifications.
        """
        if not root_uri:
            return None

        cursor = self.conn.execute("""
            SELECT uri, reason, status, indexed_at
            FROM notifications
            WHERE (root_uri = ? OR uri = ?)
            AND status IN ('pending', 'processed', 'ignored', 'no_reply')
            ORDER BY
                CASE reason
                    WHEN 'mention' THEN 1
                    WHEN 'reply' THEN 2
                    ELSE 3
                END,
                indexed_at ASC
            LIMIT 1
        """, (root_uri, root_uri))

        row = cursor.fetchone()
        return dict(row) if row else None

    def has_notification_for_parent(self, parent_uri: str) -> Optional[Dict]:
        """
        Check if there's already a notification for the same parent post.

        This is used for deduplication to avoid processing multiple notifications
        about the same post. Unlike has_notification_for_root(), this only checks
        for notifications that are direct replies to the same parent post.

        Returns the existing notification dict if found, None otherwise.
        Prioritizes 'mention' notifications over 'reply' notifications.
        """
        if not parent_uri:
            return None

        cursor = self.conn.execute("""
            SELECT uri, reason, status, indexed_at
            FROM notifications
            WHERE (parent_uri = ? OR uri = ?)
            AND status IN ('pending', 'processed', 'ignored', 'no_reply')
            ORDER BY
                CASE reason
                    WHEN 'mention' THEN 1
                    WHEN 'reply' THEN 2
                    ELSE 3
                END,
                indexed_at ASC
            LIMIT 1
        """, (parent_uri, parent_uri))

        row = cursor.fetchone()
        return dict(row) if row else None

    def mark_processed(self, uri: str, status: str = 'processed', error: str = None):
        """Mark a notification as processed."""
        try:
            self.conn.execute("""
                UPDATE notifications
                SET status = ?, processed_at = ?, error = ?
                WHERE uri = ?
            """, (status, datetime.now().isoformat(), error, uri))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error marking notification processed: {e}")

    def mark_in_progress(self, uri: str):
        """
        Mark a notification as currently being processed.

        This prevents the notification from being re-queued if Bluesky re-surfaces
        it during processing (e.g., when replying to a thread updates the notification).
        """
        try:
            self.conn.execute("""
                UPDATE notifications
                SET status = 'in_progress'
                WHERE uri = ? AND status = 'pending'
            """, (uri,))
            self.conn.commit()
            logger.debug(f"Marked notification as in_progress: {uri}")
        except Exception as e:
            logger.error(f"Error marking notification in_progress: {e}")

    def increment_retry(self, uri: str) -> int:
        """Increment retry count for a notification and return new count."""
        try:
            cursor = self.conn.execute("""
                UPDATE notifications
                SET retry_count = retry_count + 1, last_retry_at = ?
                WHERE uri = ?
                RETURNING retry_count
            """, (datetime.now().isoformat(), uri))
            result = cursor.fetchone()
            self.conn.commit()
            return result['retry_count'] if result else 0
        except Exception as e:
            logger.error(f"Error incrementing retry count: {e}")
            return 0

    def get_retry_count(self, uri: str) -> int:
        """Get the retry count for a notification."""
        try:
            cursor = self.conn.execute("""
                SELECT retry_count FROM notifications WHERE uri = ?
            """, (uri,))
            row = cursor.fetchone()
            return row['retry_count'] if row else 0
        except Exception as e:
            logger.error(f"Error getting retry count: {e}")
            return 0
    
    def get_unprocessed(self, limit: int = 100) -> List[Dict]:
        """Get unprocessed notifications."""
        cursor = self.conn.execute("""
            SELECT * FROM notifications 
            WHERE status = 'pending'
            ORDER BY indexed_at ASC
            LIMIT ?
        """, (limit,))
        
        return [dict(row) for row in cursor]
    
    def get_latest_processed_time(self) -> Optional[str]:
        """Get the timestamp of the most recently processed notification."""
        cursor = self.conn.execute("""
            SELECT MAX(indexed_at) as latest 
            FROM notifications 
            WHERE status IN ('processed', 'ignored', 'no_reply')
        """)
        row = cursor.fetchone()
        return row['latest'] if row and row['latest'] else None
    
    def cleanup_old_records(self, days: int = 7):
        """Remove records older than specified days."""
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        deleted = self.conn.execute("""
            DELETE FROM notifications 
            WHERE indexed_at < ? 
            AND status IN ('processed', 'ignored', 'no_reply', 'error')
        """, (cutoff_date,)).rowcount
        
        self.conn.commit()
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old notification records")
            # Vacuum to reclaim space
            self.conn.execute("VACUUM")
    
    def get_stats(self) -> Dict:
        """Get database statistics."""
        stats = {}
        
        # Count by status
        cursor = self.conn.execute("""
            SELECT status, COUNT(*) as count 
            FROM notifications 
            GROUP BY status
        """)
        
        for row in cursor:
            stats[f"status_{row['status']}"] = row['count']
        
        # Total count
        cursor = self.conn.execute("SELECT COUNT(*) as total FROM notifications")
        stats['total'] = cursor.fetchone()['total']
        
        # Recent activity (last 24h)
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        cursor = self.conn.execute("""
            SELECT COUNT(*) as recent 
            FROM notifications 
            WHERE indexed_at > ?
        """, (yesterday,))
        stats['recent_24h'] = cursor.fetchone()['recent']
        
        return stats
    
    def start_session(self) -> int:
        """Start a new processing session."""
        cursor = self.conn.execute("""
            INSERT INTO sessions (started_at, last_seen_at)
            VALUES (?, ?)
        """, (datetime.now().isoformat(), datetime.now().isoformat()))
        self.conn.commit()
        return cursor.lastrowid
    
    def update_session(self, session_id: int, processed: int = 0, skipped: int = 0, error: int = 0):
        """Update session statistics."""
        self.conn.execute("""
            UPDATE sessions 
            SET last_seen_at = ?,
                notifications_processed = notifications_processed + ?,
                notifications_skipped = notifications_skipped + ?,
                notifications_error = notifications_error + ?
            WHERE id = ?
        """, (datetime.now().isoformat(), processed, skipped, error, session_id))
        self.conn.commit()
    
    def end_session(self, session_id: int):
        """End a processing session."""
        self.conn.execute("""
            UPDATE sessions 
            SET ended_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), session_id))
        self.conn.commit()
    
    def get_processed_uris(self, limit: int = 10000) -> Set[str]:
        """Get set of processed URIs for compatibility with existing code."""
        cursor = self.conn.execute("""
            SELECT uri FROM notifications
            WHERE status IN ('processed', 'ignored', 'no_reply', 'in_progress')
            ORDER BY processed_at DESC
            LIMIT ?
        """, (limit,))
        
        return {row['uri'] for row in cursor}
    
    def migrate_from_json(self, json_path: str = "queue/processed_notifications.json"):
        """Migrate data from the old JSON format."""
        json_file = Path(json_path)
        if not json_file.exists():
            return
        
        try:
            with open(json_file, 'r') as f:
                uris = json.load(f)
            
            migrated = 0
            for uri in uris:
                # Add as processed with unknown timestamp
                self.conn.execute("""
                    INSERT OR IGNORE INTO notifications 
                    (uri, indexed_at, status, processed_at)
                    VALUES (?, ?, 'processed', ?)
                """, (uri, datetime.now().isoformat(), datetime.now().isoformat()))
                migrated += 1
            
            self.conn.commit()
            logger.info(f"Migrated {migrated} URIs from JSON to database")
            
            # Rename old file to backup
            backup_path = json_file.with_suffix('.json.backup')
            json_file.rename(backup_path)
            logger.info(f"Renamed old JSON file to {backup_path}")
            
        except Exception as e:
            logger.error(f"Error migrating from JSON: {e}")
    
    def set_debounce(self, uri: str, debounce_until: str, reason: str = None, thread_chain_id: str = None):
        """Set debounce information for a notification."""
        try:
            self.conn.execute("""
                UPDATE notifications
                SET debounce_until = ?, debounce_reason = ?, thread_chain_id = ?
                WHERE uri = ?
            """, (debounce_until, reason, thread_chain_id, uri))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error setting debounce for notification: {e}")

    def clear_debounce(self, uri: str):
        """Clear debounce information for a notification."""
        try:
            self.conn.execute("""
                UPDATE notifications
                SET debounce_until = NULL, debounce_reason = NULL
                WHERE uri = ?
            """, (uri,))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error clearing debounce: {e}")

    def get_debounced_notifications(self, current_time: str = None) -> List[Dict]:
        """Get notifications whose debounce period has expired."""
        if current_time is None:
            current_time = datetime.now().isoformat()

        cursor = self.conn.execute("""
            SELECT * FROM notifications
            WHERE debounce_until IS NOT NULL
            AND debounce_until <= ?
            AND status = 'pending'
            ORDER BY indexed_at ASC
        """, (current_time,))

        return [dict(row) for row in cursor]

    def get_pending_debounced_notifications(self, current_time: str = None) -> List[Dict]:
        """Get notifications still within debounce period (not yet ready for processing)."""
        if current_time is None:
            current_time = datetime.now().isoformat()

        cursor = self.conn.execute("""
            SELECT * FROM notifications
            WHERE debounce_until IS NOT NULL
            AND debounce_until > ?
            AND status = 'pending'
            ORDER BY debounce_until ASC
        """, (current_time,))

        return [dict(row) for row in cursor]

    def get_thread_notifications(self, root_uri: str, author_did: str = None) -> List[Dict]:
        """Get all notifications from a thread chain, optionally filtered by author."""
        if author_did:
            cursor = self.conn.execute("""
                SELECT * FROM notifications
                WHERE root_uri = ? AND author_did = ?
                ORDER BY indexed_at ASC
            """, (root_uri, author_did))
        else:
            cursor = self.conn.execute("""
                SELECT * FROM notifications
                WHERE root_uri = ?
                ORDER BY indexed_at ASC
            """, (root_uri,))

        return [dict(row) for row in cursor]

    def get_thread_chain_notifications(self, thread_chain_id: str) -> List[Dict]:
        """Get all notifications belonging to a specific thread chain."""
        cursor = self.conn.execute("""
            SELECT * FROM notifications
            WHERE thread_chain_id = ?
            ORDER BY indexed_at ASC
        """, (thread_chain_id,))

        return [dict(row) for row in cursor]

    def get_thread_notification_count(self, root_uri: str, minutes: int = 60) -> int:
        """
        Get count of notifications for a thread within time window.

        Args:
            root_uri: The root URI of the thread
            minutes: Time window in minutes (default: 60)

        Returns:
            Count of notifications for this thread in the time window
        """
        cutoff_time = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        cursor = self.conn.execute("""
            SELECT COUNT(*) as count
            FROM notifications
            WHERE root_uri = ? AND indexed_at > ?
        """, (root_uri, cutoff_time))

        result = cursor.fetchone()
        return result['count'] if result else 0

    def get_thread_debounced_notifications(self, root_uri: str) -> List[Dict]:
        """
        Get all debounced notifications for a specific thread.

        Args:
            root_uri: The root URI of the thread

        Returns:
            List of debounced notification dicts for this thread
        """
        cursor = self.conn.execute("""
            SELECT * FROM notifications
            WHERE root_uri = ?
            AND debounce_until IS NOT NULL
            AND status = 'pending'
            ORDER BY indexed_at ASC
        """, (root_uri,))

        return [dict(row) for row in cursor]

    def get_thread_earliest_debounce(self, root_uri: str) -> Optional[Dict]:
        """
        Get the earliest debounce timer for a thread (if any).

        This is used to implement single-timer-per-thread behavior for high-traffic
        debouncing. When a new notification arrives for a thread that already has
        a debounce timer, we reuse the existing timer instead of creating a new one.

        Args:
            root_uri: The root URI of the thread

        Returns:
            Dict with notification data (including debounce_until) if found, None otherwise
        """
        cursor = self.conn.execute("""
            SELECT * FROM notifications
            WHERE root_uri = ?
            AND debounce_until IS NOT NULL
            AND status = 'pending'
            ORDER BY debounce_until ASC
            LIMIT 1
        """, (root_uri,))

        row = cursor.fetchone()
        return dict(row) if row else None

    def set_auto_debounce(self, uri: str, debounce_until: str, is_high_traffic: bool = True,
                          reason: str = None, thread_chain_id: str = None):
        """
        Set automatic debounce for high-traffic thread detection.

        Args:
            uri: Notification URI
            debounce_until: ISO timestamp when debounce expires
            is_high_traffic: Whether this is a high-traffic thread (default: True)
            reason: Reason for debouncing
            thread_chain_id: Thread chain identifier
        """
        try:
            self.conn.execute("""
                UPDATE notifications
                SET debounce_until = ?,
                    debounce_reason = ?,
                    thread_chain_id = ?,
                    auto_debounced = ?,
                    high_traffic_thread = ?
                WHERE uri = ?
            """, (debounce_until, reason, thread_chain_id,
                  1 if debounce_until else 0,
                  1 if is_high_traffic else 0,
                  uri))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error setting auto-debounce for notification: {e}")

    def clear_batch_debounce(self, root_uri: str) -> int:
        """
        Clear debounce for all notifications in a thread batch.

        Args:
            root_uri: The root URI of the thread

        Returns:
            Number of notifications cleared
        """
        try:
            cursor = self.conn.execute("""
                UPDATE notifications
                SET debounce_until = NULL,
                    debounce_reason = NULL,
                    auto_debounced = 0
                WHERE root_uri = ?
                AND debounce_until IS NOT NULL
            """, (root_uri,))
            self.conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Error clearing batch debounce: {e}")
            return 0

    def clear_high_traffic_flags(self, uri: str):
        """
        Clear high-traffic flags for a notification so it can be processed normally.

        This is used when a high-traffic batch contains only 1 notification,
        allowing it to fall back to normal processing instead of batch processing.
        """
        try:
            self.conn.execute("""
                UPDATE notifications
                SET auto_debounced = 0,
                    high_traffic_thread = 0,
                    debounce_until = NULL,
                    debounce_reason = NULL
                WHERE uri = ?
            """, (uri,))
            self.conn.commit()
            logger.debug(f"Cleared high-traffic flags for: {uri}")
        except Exception as e:
            logger.error(f"Error clearing high-traffic flags: {e}")

    def calculate_variable_debounce(self, thread_count: int, is_mention: bool, config: Dict) -> int:
        """
        Calculate variable debounce time based on thread activity level.

        Args:
            thread_count: Number of notifications in the thread
            is_mention: True if this is a direct mention, False if reply
            config: High-traffic detection config dict

        Returns:
            Debounce time in seconds
        """
        if is_mention:
            min_minutes = config.get('mention_debounce_min', 15)
            max_minutes = config.get('mention_debounce_max', 30)
            min_seconds = min_minutes * 60
            max_seconds = max_minutes * 60
            logger.debug(f"Mention debounce config: min={min_minutes}min ({min_seconds}s), max={max_minutes}min ({max_seconds}s)")
        else:
            min_minutes = config.get('reply_debounce_min', 30)
            max_minutes = config.get('reply_debounce_max', 120)
            min_seconds = min_minutes * 60
            max_seconds = max_minutes * 60
            logger.debug(f"Reply debounce config: min={min_minutes}min ({min_seconds}s), max={max_minutes}min ({max_seconds}s)")

        # Get threshold for scaling
        threshold = config.get('notification_threshold', 10)
        logger.debug(f"Debounce calculation: thread_count={thread_count}, threshold={threshold}")

        # Linear scaling: more activity = longer debounce
        # If at threshold, use min_seconds
        # If 3x threshold or more, use max_seconds
        if thread_count <= threshold:
            result_seconds = min_seconds
            logger.debug(f"Using minimum debounce: {result_seconds}s ({result_seconds/60:.1f}min)")
            return result_seconds
        elif thread_count >= threshold * 3:
            result_seconds = max_seconds
            logger.debug(f"Using maximum debounce: {result_seconds}s ({result_seconds/60:.1f}min)")
            return result_seconds
        else:
            # Linear interpolation between min and max
            ratio = (thread_count - threshold) / threshold
            result_seconds = int(min_seconds + (max_seconds - min_seconds) * ratio)
            logger.debug(f"Using interpolated debounce (ratio={ratio:.2f}): {result_seconds}s ({result_seconds/60:.1f}min)")
            return result_seconds

    # ============================================================
    # Thread State Management (for debounce state machine)
    # ============================================================

    def get_thread_state(self, root_uri: str) -> Optional[Dict]:
        """
        Get current state for a thread.

        Args:
            root_uri: The root URI of the thread

        Returns:
            Dict with state info or None if thread has no state
        """
        try:
            cursor = self.conn.execute("""
                SELECT root_uri, state, debounce_until, debounce_started_at,
                       cooldown_until, notification_count, last_notification_at, updated_at
                FROM thread_state
                WHERE root_uri = ?
            """, (root_uri,))
            row = cursor.fetchone()
            if row:
                return {
                    'root_uri': row[0],
                    'state': row[1],
                    'debounce_until': row[2],
                    'debounce_started_at': row[3],
                    'cooldown_until': row[4],
                    'notification_count': row[5],
                    'last_notification_at': row[6],
                    'updated_at': row[7]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting thread state: {e}")
            return None

    def set_thread_debouncing(self, root_uri: str, debounce_until: str, notification_count: int):
        """
        Set thread to DEBOUNCING state with timer.

        Args:
            root_uri: The root URI of the thread
            debounce_until: ISO timestamp when debounce expires
            notification_count: Current notification count for this thread
        """
        try:
            now = datetime.now().isoformat()
            self.conn.execute("""
                INSERT INTO thread_state (root_uri, state, debounce_until, debounce_started_at,
                                         cooldown_until, notification_count, last_notification_at, updated_at)
                VALUES (?, 'debouncing', ?, ?, NULL, ?, ?, ?)
                ON CONFLICT(root_uri) DO UPDATE SET
                    state = 'debouncing',
                    debounce_until = excluded.debounce_until,
                    debounce_started_at = excluded.debounce_started_at,
                    cooldown_until = NULL,
                    notification_count = excluded.notification_count,
                    last_notification_at = excluded.last_notification_at,
                    updated_at = excluded.updated_at
            """, (root_uri, debounce_until, now, notification_count, now, now))
            self.conn.commit()
            logger.debug(f"Set thread {root_uri} to DEBOUNCING until {debounce_until} (count={notification_count})")
        except Exception as e:
            logger.error(f"Error setting thread debouncing state: {e}")

    def extend_thread_debounce(self, root_uri: str, debounce_seconds: int, notification_count: int,
                                debounce_started_at: str) -> Optional[str]:
        """
        Extend existing debounce timer for a thread.

        The new expiry is calculated from the original debounce start time, NOT from now.
        This prevents infinite deferral when a thread remains active - the debounce will
        always expire at most `debounce_seconds` after it first started.

        This updates both the thread_state table AND all pending notifications
        in the thread to ensure they all use the extended timer.

        Args:
            root_uri: The root URI of the thread
            debounce_seconds: Duration in seconds from start time
            notification_count: Updated notification count
            debounce_started_at: ISO timestamp when debouncing first started

        Returns:
            The new debounce_until timestamp, or None on error
        """
        try:
            now = datetime.now()
            now_str = now.isoformat()

            # Calculate expiry from when debouncing STARTED, not from now
            start_time = datetime.fromisoformat(debounce_started_at)
            new_debounce_until = (start_time + timedelta(seconds=debounce_seconds)).isoformat()

            # If the calculated expiry is already in the past, set it to a minimum
            # of 1 minute from now to give the batch a chance to process
            if new_debounce_until <= now_str:
                new_debounce_until = (now + timedelta(minutes=1)).isoformat()
                logger.debug(f"Debounce expiry was in past, setting to {new_debounce_until}")

            # Update thread state
            self.conn.execute("""
                UPDATE thread_state
                SET debounce_until = ?,
                    notification_count = ?,
                    last_notification_at = ?,
                    updated_at = ?
                WHERE root_uri = ? AND state = 'debouncing'
            """, (new_debounce_until, notification_count, now_str, now_str, root_uri))

            # Also update all pending notifications in this thread to use the new timer
            cursor = self.conn.execute("""
                UPDATE notifications
                SET debounce_until = ?
                WHERE root_uri = ?
                AND status = 'pending'
                AND debounce_until IS NOT NULL
            """, (new_debounce_until, root_uri))
            updated_count = cursor.rowcount

            self.conn.commit()
            logger.debug(f"Extended thread {root_uri} debounce to {new_debounce_until} (from start {debounce_started_at}, count={notification_count}, updated {updated_count} notifications)")
            return new_debounce_until
        except Exception as e:
            logger.error(f"Error extending thread debounce: {e}")
            return None

    def set_thread_cooldown(self, root_uri: str, cooldown_until: str):
        """
        Transition thread from DEBOUNCING to COOLDOWN after batch processing.

        Args:
            root_uri: The root URI of the thread
            cooldown_until: ISO timestamp when cooldown expires
        """
        try:
            now = datetime.now().isoformat()
            self.conn.execute("""
                UPDATE thread_state
                SET state = 'cooldown',
                    debounce_until = NULL,
                    cooldown_until = ?,
                    updated_at = ?
                WHERE root_uri = ?
            """, (cooldown_until, now, root_uri))
            self.conn.commit()
            logger.debug(f"Set thread {root_uri} to COOLDOWN until {cooldown_until}")
        except Exception as e:
            logger.error(f"Error setting thread cooldown state: {e}")

    def clear_thread_state(self, root_uri: str):
        """
        Full reset - remove thread from state table.

        Args:
            root_uri: The root URI of the thread
        """
        try:
            self.conn.execute("""
                DELETE FROM thread_state WHERE root_uri = ?
            """, (root_uri,))
            self.conn.commit()
            logger.debug(f"Cleared thread state for {root_uri}")
        except Exception as e:
            logger.error(f"Error clearing thread state: {e}")

    def get_expired_cooldowns(self) -> List[Dict]:
        """
        Find threads in COOLDOWN where cooldown_until < now.

        Returns:
            List of thread state dicts with expired cooldowns
        """
        try:
            now = datetime.now().isoformat()
            cursor = self.conn.execute("""
                SELECT root_uri, state, debounce_until, debounce_started_at,
                       cooldown_until, notification_count, last_notification_at, updated_at
                FROM thread_state
                WHERE state = 'cooldown' AND cooldown_until < ?
            """, (now,))
            rows = cursor.fetchall()
            return [
                {
                    'root_uri': row[0],
                    'state': row[1],
                    'debounce_until': row[2],
                    'debounce_started_at': row[3],
                    'cooldown_until': row[4],
                    'notification_count': row[5],
                    'last_notification_at': row[6],
                    'updated_at': row[7]
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Error getting expired cooldowns: {e}")
            return []

    def cleanup_expired_cooldowns(self) -> int:
        """
        Remove threads with expired cooldowns (full reset).

        Returns:
            Number of threads reset
        """
        try:
            now = datetime.now().isoformat()
            cursor = self.conn.execute("""
                DELETE FROM thread_state
                WHERE state = 'cooldown' AND cooldown_until < ?
            """, (now,))
            self.conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Error cleaning up expired cooldowns: {e}")
            return 0

    # ============================================================
    # Thread Batch History (persists independently of thread_state)
    # ============================================================

    def get_thread_batch_history(self, root_uri: str) -> Optional[Dict]:
        """
        Get batch history for a thread.

        This persists across thread_state resets (cooldown expiry) so umbra
        remembers what posts it has already seen even after long gaps.

        Args:
            root_uri: The root URI of the thread

        Returns:
            Dict with batch history or None if no history exists
        """
        try:
            cursor = self.conn.execute("""
                SELECT root_uri, last_batch_processed_at, last_batch_newest_post_indexed_at
                FROM thread_batch_history
                WHERE root_uri = ?
            """, (root_uri,))
            row = cursor.fetchone()
            if row:
                return {
                    'root_uri': row[0],
                    'last_batch_processed_at': row[1],
                    'last_batch_newest_post_indexed_at': row[2]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting thread batch history: {e}")
            return None

    def update_thread_batch_history(self, root_uri: str, processed_at: str, newest_post_indexed_at: str):
        """
        Update batch history after processing a high-traffic batch.

        Uses upsert to create or update the record.

        Args:
            root_uri: The root URI of the thread
            processed_at: ISO timestamp when the batch was processed
            newest_post_indexed_at: ISO timestamp (createdAt) of the newest post in the batch
        """
        try:
            self.conn.execute("""
                INSERT INTO thread_batch_history (root_uri, last_batch_processed_at, last_batch_newest_post_indexed_at)
                VALUES (?, ?, ?)
                ON CONFLICT(root_uri) DO UPDATE SET
                    last_batch_processed_at = excluded.last_batch_processed_at,
                    last_batch_newest_post_indexed_at = excluded.last_batch_newest_post_indexed_at
            """, (root_uri, processed_at, newest_post_indexed_at))
            self.conn.commit()
            logger.debug(f"Updated batch history for {root_uri}: processed_at={processed_at}, newest_post={newest_post_indexed_at}")
        except Exception as e:
            logger.error(f"Error updating thread batch history: {e}")

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()