"""
database.py  –  SQLite persistence layer for Auto-Citer.

Tables:
  - history       : processing runs
  - shared_results: public download tokens
  - preferences   : per-session settings

Usage:
  db = Database()
  db.init()
  entry_id = db.save_history(...)
  db.cleanup_expired()
"""

import sqlite3
import uuid
import secrets
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import os
_IS_VERCEL = os.environ.get('VERCEL') or os.environ.get('VERCEL_ENV')
_DEFAULT_DIR = '/tmp' if _IS_VERCEL else str(Path(__file__).parent)
DB_PATH = os.environ.get('DB_PATH', str(Path(_DEFAULT_DIR) / 'citation_app.db'))


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    # ── Init ──────────────────────────────────────────────────────────────────

    def init(self) -> None:
        """Create all tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS history (
                    id           TEXT PRIMARY KEY,
                    filename     TEXT NOT NULL,
                    style        TEXT NOT NULL,
                    total_refs   INTEGER DEFAULT 0,
                    cited_refs   INTEGER DEFAULT 0,
                    avg_conf     REAL DEFAULT 0,
                    result_path  TEXT,
                    output_name  TEXT,
                    created_at   TEXT DEFAULT (datetime('now')),
                    expires_at   TEXT
                );

                CREATE TABLE IF NOT EXISTS shared_results (
                    token        TEXT PRIMARY KEY,
                    history_id   TEXT NOT NULL,
                    created_at   TEXT DEFAULT (datetime('now')),
                    expires_at   TEXT NOT NULL,
                    downloads    INTEGER DEFAULT 0,
                    FOREIGN KEY (history_id) REFERENCES history(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS preferences (
                    session_id   TEXT PRIMARY KEY,
                    theme        TEXT DEFAULT 'dark',
                    default_style TEXT DEFAULT 'apa',
                    updated_at   TEXT DEFAULT (datetime('now'))
                );
            """)

    # ── History ───────────────────────────────────────────────────────────────

    def save_history(self, filename: str, style: str,
                     total_refs: int, cited_refs: int,
                     avg_conf: float, result_path: str,
                     output_name: str,
                     ttl_hours: int = 24) -> str:
        """Save a processing run. Returns the new ID."""
        entry_id  = str(uuid.uuid4())
        expires   = (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO history
                   (id, filename, style, total_refs, cited_refs, avg_conf,
                    result_path, output_name, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, filename, style, total_refs, cited_refs,
                 round(avg_conf, 1), result_path, output_name, expires)
            )
        return entry_id

    def get_history(self, entry_id: str) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute(
                'SELECT * FROM history WHERE id = ?', (entry_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_history(self, limit: int = 50) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT * FROM history ORDER BY created_at DESC LIMIT ?',
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_history(self, entry_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute('DELETE FROM history WHERE id = ?', (entry_id,))
        return cursor.rowcount > 0

    # ── Shared results ────────────────────────────────────────────────────────

    def create_share_token(self, history_id: str, ttl_hours: int = 24) -> str:
        """Create a short shareable download token. Returns the token."""
        token    = secrets.token_urlsafe(8)
        expires  = (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO shared_results (token, history_id, expires_at)
                   VALUES (?, ?, ?)""",
                (token, history_id, expires)
            )
        return token

    def get_by_token(self, token: str) -> Optional[Dict]:
        """Resolve a share token → history entry (if not expired)."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT h.*, s.token, s.expires_at AS token_expires, s.downloads
                   FROM shared_results s
                   JOIN history h ON h.id = s.history_id
                   WHERE s.token = ?
                     AND s.expires_at > datetime('now')""",
                (token,)
            ).fetchone()
        if row:
            with self._connect() as conn:
                conn.execute(
                    'UPDATE shared_results SET downloads = downloads + 1 WHERE token = ?',
                    (token,)
                )
        return dict(row) if row else None

    # ── Preferences ───────────────────────────────────────────────────────────

    def get_or_create_prefs(self, session_id: str) -> Dict:
        with self._connect() as conn:
            row = conn.execute(
                'SELECT * FROM preferences WHERE session_id = ?', (session_id,)
            ).fetchone()
            if not row:
                conn.execute(
                    'INSERT INTO preferences (session_id) VALUES (?)', (session_id,)
                )
                row = conn.execute(
                    'SELECT * FROM preferences WHERE session_id = ?', (session_id,)
                ).fetchone()
        return dict(row) if row else {}

    def update_prefs(self, session_id: str, **kwargs) -> None:
        allowed = {'theme', 'default_style'}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ', '.join(f'{k} = ?' for k in updates)
        values = list(updates.values()) + [session_id]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE preferences SET {set_clause}, updated_at = datetime('now') "
                f"WHERE session_id = ?",
                values
            )

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """Delete expired history entries and their temp files. Returns count deleted."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, result_path FROM history WHERE expires_at < datetime('now')"
            ).fetchall()
            count = 0
            for row in rows:
                try:
                    if row['result_path'] and os.path.exists(row['result_path']):
                        os.remove(row['result_path'])
                except OSError:
                    pass
                conn.execute('DELETE FROM history WHERE id = ?', (row['id'],))
                count += 1
            # Also clean expired share tokens
            conn.execute("DELETE FROM shared_results WHERE expires_at < datetime('now')")
        return count
