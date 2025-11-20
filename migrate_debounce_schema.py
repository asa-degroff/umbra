#!/usr/bin/env python3
"""Migration script to add debounce fields to existing notification database."""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def migrate_database(db_path: str = "queue/notifications.db"):
    """Add debounce columns to existing notifications table."""

    db_file = Path(db_path)
    if not db_file.exists():
        logger.info(f"Database not found at {db_path}. No migration needed.")
        return

    logger.info(f"Starting migration for {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(notifications)")
    columns = {row[1] for row in cursor.fetchall()}

    columns_to_add = []
    if 'debounce_until' not in columns:
        columns_to_add.append('debounce_until TEXT')
    if 'debounce_reason' not in columns:
        columns_to_add.append('debounce_reason TEXT')
    if 'thread_chain_id' not in columns:
        columns_to_add.append('thread_chain_id TEXT')

    if not columns_to_add:
        logger.info("Database already has debounce columns. No migration needed.")
        conn.close()
        return

    # Add missing columns
    for column_def in columns_to_add:
        column_name = column_def.split()[0]
        logger.info(f"Adding column: {column_name}")
        try:
            cursor.execute(f"ALTER TABLE notifications ADD COLUMN {column_def}")
        except sqlite3.OperationalError as e:
            logger.warning(f"Column {column_name} may already exist: {e}")

    # Create indexes for new columns
    logger.info("Creating indexes...")

    indexes = [
        ("idx_debounce_until", "debounce_until"),
        ("idx_root_uri", "root_uri"),
        ("idx_thread_chain_id", "thread_chain_id"),
    ]

    for index_name, column_name in indexes:
        try:
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS {index_name}
                ON notifications({column_name})
            """)
            logger.info(f"Created index: {index_name}")
        except sqlite3.OperationalError as e:
            logger.warning(f"Index {index_name} may already exist: {e}")

    conn.commit()
    conn.close()

    logger.info("Migration completed successfully!")

if __name__ == "__main__":
    migrate_database()
