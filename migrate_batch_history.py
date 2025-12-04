#!/usr/bin/env python3
"""Migration script to add thread_batch_history table."""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def migrate_database(db_path: str = "queue/notifications.db"):
    """Add thread_batch_history table to existing database."""

    db_file = Path(db_path)
    if not db_file.exists():
        logger.info(f"Database not found at {db_path}. No migration needed.")
        return

    logger.info(f"Starting thread_batch_history migration for {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if thread_batch_history table already exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='thread_batch_history'")
    table_exists = cursor.fetchone() is not None

    if table_exists:
        logger.info("thread_batch_history table already exists. No migration needed.")
        conn.close()
        return

    # Create thread_batch_history table
    logger.info("Creating thread_batch_history table...")
    cursor.execute("""
        CREATE TABLE thread_batch_history (
            root_uri TEXT PRIMARY KEY,
            last_batch_processed_at TEXT,
            last_batch_newest_post_indexed_at TEXT
        )
    """)
    logger.info("Created thread_batch_history table")

    conn.commit()
    conn.close()

    logger.info("thread_batch_history migration completed successfully!")

if __name__ == "__main__":
    migrate_database()
