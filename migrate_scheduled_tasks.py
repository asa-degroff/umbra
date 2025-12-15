#!/usr/bin/env python3
"""Migration script to add scheduled_tasks table to notification database."""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def migrate_database(db_path: str = "queue/notifications.db"):
    """Add scheduled_tasks table to existing database."""

    db_file = Path(db_path)
    if not db_file.exists():
        logger.info(f"Database not found at {db_path}. No migration needed.")
        return

    logger.info(f"Starting scheduled_tasks migration for {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if table already exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='scheduled_tasks'
    """)
    if cursor.fetchone():
        logger.info("scheduled_tasks table already exists. No migration needed.")
        conn.close()
        return

    # Create the table
    logger.info("Creating scheduled_tasks table...")
    cursor.execute("""
        CREATE TABLE scheduled_tasks (
            task_name TEXT PRIMARY KEY,
            next_run_at TEXT NOT NULL,
            last_run_at TEXT,
            interval_seconds INTEGER,
            is_random_window INTEGER DEFAULT 0,
            window_seconds INTEGER,
            enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Create index for efficient lookup of due tasks
    logger.info("Creating index for scheduled_tasks...")
    cursor.execute("""
        CREATE INDEX idx_scheduled_tasks_next_run
        ON scheduled_tasks(next_run_at, enabled)
    """)

    conn.commit()
    conn.close()

    logger.info("Scheduled tasks migration completed successfully!")

if __name__ == "__main__":
    migrate_database()
