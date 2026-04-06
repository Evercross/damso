"""
Damso - History Manager
Stores transcription history in local SQLite database.
"""
import logging
import sqlite3
import os
from datetime import datetime, timedelta
from config import DB_PATH

log = logging.getLogger("damso")


class HistoryManager:
    """Manages transcription history with SQLite."""

    def __init__(self, retention_days: int = 30):
        self.db_path = DB_PATH
        self.retention_days = retention_days
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database and create tables if needed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                processed_text TEXT NOT NULL,
                language TEXT,
                duration_seconds REAL,
                app_name TEXT
            )
        """)
        conn.commit()
        conn.close()

    def add_entry(
        self,
        raw_text: str,
        processed_text: str,
        language: str | None = None,
        duration: float | None = None,
        app_name: str | None = None,
    ) -> None:
        """Add a new history entry."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO history (timestamp, raw_text, processed_text, language, duration_seconds, app_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                raw_text,
                processed_text,
                language,
                duration,
                app_name,
            ),
        )
        conn.commit()
        conn.close()

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Get recent history entries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, timestamp, raw_text, processed_text, language, app_name FROM history ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "timestamp": r[1],
                "raw_text": r[2],
                "processed_text": r[3],
                "language": r[4],
                "app_name": r[5],
            }
            for r in rows
        ]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Search history by text content."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, timestamp, raw_text, processed_text, language, app_name
               FROM history
               WHERE raw_text LIKE ? OR processed_text LIKE ?
               ORDER BY id DESC LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit),
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "timestamp": r[1],
                "raw_text": r[2],
                "processed_text": r[3],
                "language": r[4],
                "app_name": r[5],
            }
            for r in rows
        ]

    def cleanup_old(self) -> int:
        """Remove entries older than retention period."""
        if self.retention_days is None or self.retention_days <= 0:
            # 0 means keep forever.
            return 0

        cutoff = (datetime.now() - timedelta(days=self.retention_days)).isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            log.info("[History] Cleaned up %d old entries.", deleted)
        return deleted

    def clear_all(self) -> None:
        """Clear all history."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history")
        conn.commit()
        conn.close()
        log.info("[History] All history cleared.")

    def count(self) -> int:
        """Get total number of entries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM history")
        count = cursor.fetchone()[0]
        conn.close()
        return count
