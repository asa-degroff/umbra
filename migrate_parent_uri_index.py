#!/usr/bin/env python3
"""Migration script to add parent_uri index for improved deduplication."""

import sqlite3
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_db(db_path: str = "queue/notifications.db"):
    """Add index on parent_uri for efficient deduplication queries."""
    db_file = Path(db_path)

    if not db_file.exists():
        logger.error(f"Database not found at {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if index already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_parent_uri'
        """)

        if cursor.fetchone():
            logger.info("Index idx_parent_uri already exists, skipping migration")
            conn.close()
            return True

        # Create index on parent_uri
        logger.info("Creating index on parent_uri column...")
        cursor.execute("""
            CREATE INDEX idx_parent_uri
            ON notifications(parent_uri)
        """)

        conn.commit()
        logger.info("✓ Successfully created idx_parent_uri index")

        # Get count of notifications to verify
        cursor.execute("SELECT COUNT(*) FROM notifications WHERE parent_uri IS NOT NULL")
        count = cursor.fetchone()[0]
        logger.info(f"✓ Index covers {count} notifications with parent_uri")

        conn.close()
        return True

    except Exception as e:
        logger.error(f"Migration failed: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    logger.info("Starting parent_uri index migration...")
    success = migrate_db()

    if success:
        logger.info("Migration completed successfully!")
    else:
        logger.error("Migration failed!")
        exit(1)
