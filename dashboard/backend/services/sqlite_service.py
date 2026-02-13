"""
SQLite Service

Provides access to Umbra's notifications database.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger('dashboard.sqlite')


class SQLiteService:
    """Service for accessing the notifications SQLite database."""
    
    def __init__(self, db_path: str = "./queue/notifications.db"):
        """
        Initialize the SQLite service.
        
        Args:
            db_path: Path to notifications database
        """
        self.db_path = Path(db_path)
    
    @property
    def is_available(self) -> bool:
        """Check if the database exists."""
        return self.db_path.exists()
    
    def _get_connection(self) -> Optional[sqlite3.Connection]:
        """Get a database connection."""
        if not self.is_available:
            return None
        
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_stats(self) -> dict:
        """Get database statistics."""
        conn = self._get_connection()
        if not conn:
            return {"available": False, "error": "Database not found"}
        
        try:
            cursor = conn.cursor()
            
            # Get table counts
            stats = {
                "available": True,
                "db_path": str(self.db_path),
                "tables": {},
            }
            
            # List tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                stats["tables"][table] = count
            
            return stats
        except Exception as e:
            return {"available": False, "error": str(e)}
        finally:
            conn.close()
    
    def get_notifications(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> dict:
        """
        Get notifications from the database.
        
        Args:
            limit: Maximum notifications to return
            offset: Offset for pagination
            status: Filter by status
            
        Returns:
            Dict with notifications and metadata
        """
        conn = self._get_connection()
        if not conn:
            return {"notifications": [], "total": 0, "error": "Database not found"}
        
        try:
            cursor = conn.cursor()
            
            # Check if processed_notifications table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='processed_notifications'
            """)
            if not cursor.fetchone():
                return {"notifications": [], "total": 0, "error": "Table not found"}
            
            # Get total count
            cursor.execute("SELECT COUNT(*) FROM processed_notifications")
            total = cursor.fetchone()[0]
            
            # Get notifications
            cursor.execute("""
                SELECT * FROM processed_notifications
                ORDER BY processed_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            notifications = [dict(row) for row in cursor.fetchall()]
            
            return {
                "notifications": notifications,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        except Exception as e:
            return {"notifications": [], "total": 0, "error": str(e)}
        finally:
            conn.close()
    
    def get_scheduled_tasks(self) -> dict:
        """Get scheduled tasks from the database."""
        conn = self._get_connection()
        if not conn:
            return {"tasks": [], "error": "Database not found"}
        
        try:
            cursor = conn.cursor()
            
            # Check if scheduled_tasks table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='scheduled_tasks'
            """)
            if not cursor.fetchone():
                return {"tasks": [], "error": "Table not found"}
            
            cursor.execute("""
                SELECT * FROM scheduled_tasks
                ORDER BY next_run ASC
            """)
            
            tasks = [dict(row) for row in cursor.fetchall()]
            
            return {"tasks": tasks}
        except Exception as e:
            return {"tasks": [], "error": str(e)}
        finally:
            conn.close()
    
    def get_thread_states(self, limit: int = 50) -> dict:
        """Get thread states from the database."""
        conn = self._get_connection()
        if not conn:
            return {"threads": [], "error": "Database not found"}
        
        try:
            cursor = conn.cursor()
            
            # Check if thread_states table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='thread_states'
            """)
            if not cursor.fetchone():
                return {"threads": [], "error": "Table not found"}
            
            cursor.execute("""
                SELECT * FROM thread_states
                ORDER BY updated_at DESC
                LIMIT ?
            """, (limit,))
            
            threads = [dict(row) for row in cursor.fetchall()]
            
            return {"threads": threads}
        except Exception as e:
            return {"threads": [], "error": str(e)}
        finally:
            conn.close()
