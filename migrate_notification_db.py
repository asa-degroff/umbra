#!/usr/bin/env python3
"""Migration script to add retry tracking columns to notification database."""

import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
import sys

def backup_database(db_path: Path) -> Path:
    """Create a backup of the database."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}_backup_{timestamp}.db"

    print(f"Creating backup: {backup_path}")
    shutil.copy2(db_path, backup_path)
    print(f"✓ Backup created successfully")

    return backup_path

def check_column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns

def migrate_database(db_path: str):
    """Migrate the notification database to add retry tracking columns."""
    db_file = Path(db_path)

    if not db_file.exists():
        print(f"✗ Database not found: {db_path}")
        print("No migration needed - database will be created with new schema on first run")
        return True

    print(f"Starting migration for: {db_path}")
    print("=" * 60)

    # Create backup
    backup_path = backup_database(db_file)

    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Check current schema
        print("\nChecking current schema...")

        # Get current statistics
        cursor = conn.execute("SELECT COUNT(*) as total FROM notifications")
        total_notifications = cursor.fetchone()[0]
        print(f"Current database has {total_notifications} notifications")

        # Check if columns already exist
        retry_count_exists = check_column_exists(conn, 'notifications', 'retry_count')
        last_retry_exists = check_column_exists(conn, 'notifications', 'last_retry_at')

        if retry_count_exists and last_retry_exists:
            print("\n✓ Database already has retry tracking columns - no migration needed")
            conn.close()
            return True

        # Add missing columns
        print("\nAdding new columns...")

        if not retry_count_exists:
            print("Adding 'retry_count' column...")
            conn.execute("""
                ALTER TABLE notifications
                ADD COLUMN retry_count INTEGER DEFAULT 0
            """)
            print("✓ Added 'retry_count' column")
        else:
            print("✓ Column 'retry_count' already exists")

        if not last_retry_exists:
            print("Adding 'last_retry_at' column...")
            conn.execute("""
                ALTER TABLE notifications
                ADD COLUMN last_retry_at TEXT
            """)
            print("✓ Added 'last_retry_at' column")
        else:
            print("✓ Column 'last_retry_at' already exists")

        conn.commit()

        # Verify migration
        print("\nVerifying migration...")

        # Check columns exist
        retry_count_exists = check_column_exists(conn, 'notifications', 'retry_count')
        last_retry_exists = check_column_exists(conn, 'notifications', 'last_retry_at')

        if not (retry_count_exists and last_retry_exists):
            raise Exception("Migration verification failed - columns not found after adding")

        # Check data integrity
        cursor = conn.execute("SELECT COUNT(*) as total FROM notifications")
        new_total = cursor.fetchone()[0]

        if new_total != total_notifications:
            raise Exception(f"Data loss detected: {total_notifications} -> {new_total}")

        print(f"✓ All {new_total} notifications preserved")

        # Show sample of migrated data
        cursor = conn.execute("""
            SELECT uri, status, retry_count, last_retry_at
            FROM notifications
            LIMIT 3
        """)

        print("\nSample of migrated data:")
        for row in cursor:
            print(f"  - URI: {row['uri'][:50]}...")
            print(f"    Status: {row['status']}, Retry count: {row['retry_count']}")

        conn.close()

        print("\n" + "=" * 60)
        print("✓ Migration completed successfully!")
        print(f"\nBackup saved to: {backup_path}")
        print("You can delete the backup file once you've verified everything works.")

        return True

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        print(f"\nRestoring from backup...")

        # Restore from backup
        shutil.copy2(backup_path, db_file)
        print(f"✓ Database restored from backup")
        print(f"\nBackup preserved at: {backup_path}")

        return False

def main():
    """Main migration function."""
    # Default path from config
    db_path = "queue/notifications.db"

    # Allow custom path as command line argument
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    print("=" * 60)
    print("Notification Database Migration")
    print("Adding retry tracking columns")
    print("=" * 60)
    print()

    success = migrate_database(db_path)

    if success:
        print("\n✓ Ready to run the bot with retry tracking enabled!")
        sys.exit(0)
    else:
        print("\n✗ Migration failed - please check the errors above")
        sys.exit(1)

if __name__ == "__main__":
    main()
