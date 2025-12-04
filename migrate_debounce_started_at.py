#!/usr/bin/env python3
"""Migration script to add debounce_started_at column to thread_state table."""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def migrate_database(db_path: str = "queue/notifications.db"):
    """Add debounce_started_at column to thread_state table."""

    db_file = Path(db_path)
    if not db_file.exists():
        logger.info(f"Database not found at {db_path}. No migration needed.")
        return

    logger.info(f"Starting debounce_started_at migration for {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if thread_state table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='thread_state'")
    table_exists = cursor.fetchone() is not None

    if not table_exists:
        logger.info("thread_state table does not exist. Run migrate_thread_state_schema.py first.")
        conn.close()
        return

    # Check if debounce_started_at column already exists
    cursor.execute("PRAGMA table_info(thread_state)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'debounce_started_at' in columns:
        logger.info("debounce_started_at column already exists. No migration needed.")
        conn.close()
        return

    # Add the new column
    logger.info("Adding debounce_started_at column to thread_state table...")
    cursor.execute("""
        ALTER TABLE thread_state
        ADD COLUMN debounce_started_at TEXT
    """)

    # For existing rows in debouncing state, set debounce_started_at to updated_at
    # (best approximation we have for when debouncing started)
    cursor.execute("""
        UPDATE thread_state
        SET debounce_started_at = updated_at
        WHERE state = 'debouncing' AND debounce_started_at IS NULL
    """)
    updated = cursor.rowcount
    if updated > 0:
        logger.info(f"Backfilled debounce_started_at for {updated} existing debouncing threads")

    conn.commit()
    conn.close()

    logger.info("debounce_started_at migration completed successfully!")

if __name__ == "__main__":
    migrate_database()
