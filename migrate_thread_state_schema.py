#!/usr/bin/env python3
"""Migration script to add thread_state table for debounce state machine."""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def migrate_database(db_path: str = "queue/notifications.db"):
    """Add thread_state table and indexes to existing database."""

    db_file = Path(db_path)
    if not db_file.exists():
        logger.info(f"Database not found at {db_path}. No migration needed.")
        return

    logger.info(f"Starting thread_state migration for {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if thread_state table already exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='thread_state'")
    table_exists = cursor.fetchone() is not None

    if table_exists:
        logger.info("thread_state table already exists. No migration needed.")
    else:
        # Create thread_state table
        logger.info("Creating thread_state table...")
        cursor.execute("""
            CREATE TABLE thread_state (
                root_uri TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                debounce_until TEXT,
                cooldown_until TEXT,
                notification_count INTEGER DEFAULT 0,
                last_notification_at TEXT,
                updated_at TEXT
            )
        """)
        logger.info("Created thread_state table")

    # Create indexes
    logger.info("Creating indexes...")

    indexes = [
        ("idx_thread_state_debounce", "state, debounce_until"),
        ("idx_thread_state_cooldown", "state, cooldown_until"),
    ]

    for index_name, column_spec in indexes:
        try:
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS {index_name}
                ON thread_state({column_spec})
            """)
            logger.info(f"Created index: {index_name}")
        except sqlite3.OperationalError as e:
            logger.warning(f"Index {index_name} may already exist: {e}")

    conn.commit()
    conn.close()

    logger.info("Thread state migration completed successfully!")

if __name__ == "__main__":
    migrate_database()
