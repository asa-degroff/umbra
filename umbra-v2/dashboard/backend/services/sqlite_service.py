"""
SQLite service for reading notification DB and scheduled tasks.
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger("dashboard.sqlite")


class SQLiteService:
    """Read-only access to the bot's notification database."""

    def __init__(self, db_path: str = "./queue/notifications.db"):
        self.db_path = Path(db_path)

    def _connect(self):
        if not self.db_path.exists():
            return None
        return sqlite3.connect(str(self.db_path))

    def get_stats(self) -> dict:
        """Get database statistics."""
        conn = self._connect()
        if not conn:
            return {"status": "not_found", "path": str(self.db_path)}
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {}
            for (name,) in cursor.fetchall():
                cursor.execute(f"SELECT COUNT(*) FROM [{name}]")
                tables[name] = cursor.fetchone()[0]
            return {"status": "ok", "path": str(self.db_path), "tables": tables}
        except Exception as e:
            return {"status": "error", "error": str(e)}
        finally:
            conn.close()

    def get_scheduled_tasks(self) -> list[dict]:
        """Get scheduled task information."""
        conn = self._connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT task_name, next_run, last_run, enabled, interval_seconds
                FROM scheduled_tasks
                ORDER BY task_name
            """)
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

    def get_thread_states(self) -> list[dict]:
        """Get active thread debounce states."""
        conn = self._connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT thread_chain_id, debounce_until, debounce_reason,
                       auto_debounced, high_traffic_thread
                FROM notifications
                WHERE debounce_until IS NOT NULL
                ORDER BY debounce_until DESC
                LIMIT 50
            """)
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()
