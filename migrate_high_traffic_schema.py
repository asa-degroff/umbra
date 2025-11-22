#!/usr/bin/env python3
"""Migration script to add high-traffic thread detection fields to notification database."""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def migrate_database(db_path: str = "queue/notifications.db"):
    """Add high-traffic detection columns to existing notifications table."""

    db_file = Path(db_path)
    if not db_file.exists():
        logger.info(f"Database not found at {db_path}. No migration needed.")
        return

    logger.info(f"Starting high-traffic migration for {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(notifications)")
    columns = {row[1] for row in cursor.fetchall()}

    columns_to_add = []
    if 'auto_debounced' not in columns:
        columns_to_add.append('auto_debounced INTEGER DEFAULT 0')
    if 'high_traffic_thread' not in columns:
        columns_to_add.append('high_traffic_thread INTEGER DEFAULT 0')

    if not columns_to_add:
        logger.info("Database already has high-traffic columns. No migration needed.")
    else:
        # Add missing columns
        for column_def in columns_to_add:
            column_name = column_def.split()[0]
            logger.info(f"Adding column: {column_name}")
            try:
                cursor.execute(f"ALTER TABLE notifications ADD COLUMN {column_def}")
            except sqlite3.OperationalError as e:
                logger.warning(f"Column {column_name} may already exist: {e}")

    # Create composite index for efficient thread counting
    logger.info("Creating indexes...")

    indexes = [
        ("idx_root_uri_indexed_at", "root_uri, indexed_at"),
        ("idx_auto_debounced", "auto_debounced"),
        ("idx_high_traffic_thread", "high_traffic_thread"),
    ]

    for index_name, column_spec in indexes:
        try:
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS {index_name}
                ON notifications({column_spec})
            """)
            logger.info(f"Created index: {index_name}")
        except sqlite3.OperationalError as e:
            logger.warning(f"Index {index_name} may already exist: {e}")

    conn.commit()
    conn.close()

    logger.info("High-traffic migration completed successfully!")

if __name__ == "__main__":
    migrate_database()
