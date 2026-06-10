"""SQLite database layer for LLMNotes"""

import sqlite3
import os
import json
from datetime import datetime
from config import DB_PATH


class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                filename TEXT NOT NULL UNIQUE,
                source_filename TEXT,
                source_type TEXT DEFAULT 'md',
                content TEXT,
                content_preview TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT,
                reasoning TEXT,
                notes_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS note_search_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding TEXT,
                FOREIGN KEY (note_id) REFERENCES notes(id)
            );

            CREATE INDEX IF NOT EXISTS idx_notes_title ON notes(title);
            CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at);
            CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        self.conn.commit()

    def get_setting(self, key, default=None):
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else default

    def set_setting(self, key, value):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()

    def add_note(self, title, filename, source_filename=None, source_type="md", content=""):
        cursor = self.conn.cursor()
        preview = content[:200] if content else ""
        cursor.execute(
            """INSERT OR REPLACE INTO notes (title, filename, source_filename, source_type, content, content_preview)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, filename, source_filename, source_type, content, preview)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_note(self, note_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
        return cursor.fetchone()

    def get_note_by_filename(self, filename):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM notes WHERE filename = ?", (filename,))
        return cursor.fetchone()

    def get_all_notes(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM notes ORDER BY updated_at DESC")
        return cursor.fetchall()

    def update_note_content(self, note_id, content):
        cursor = self.conn.cursor()
        preview = content[:200] if content else ""
        cursor.execute(
            "UPDATE notes SET content = ?, content_preview = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (content, preview, note_id)
        )
        self.conn.commit()

    def delete_note(self, note_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        cursor.execute("DELETE FROM note_search_cache WHERE note_id = ?", (note_id,))
        self.conn.commit()

    def add_conversation(self, question, answer, reasoning="", notes_used=None):
        cursor = self.conn.cursor()
        notes_used_json = json.dumps(notes_used) if notes_used else "[]"
        cursor.execute(
            "INSERT INTO conversations (question, answer, reasoning, notes_used) VALUES (?, ?, ?, ?)",
            (question, answer, reasoning, notes_used_json)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_conversations(self, limit=50):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM conversations ORDER BY created_at DESC LIMIT ?", (limit,))
        return cursor.fetchall()

    def store_chunks(self, note_id, chunks):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM note_search_cache WHERE note_id = ?", (note_id,))
        for i, chunk in enumerate(chunks):
            cursor.execute(
                "INSERT INTO note_search_cache (note_id, chunk_index, chunk_text) VALUES (?, ?, ?)",
                (note_id, i, chunk)
            )
        self.conn.commit()

    def get_all_chunks(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT nsc.*, n.title as note_title, n.filename as note_filename
            FROM note_search_cache nsc
            JOIN notes n ON n.id = nsc.note_id
            ORDER BY nsc.note_id, nsc.chunk_index
        """)
        return cursor.fetchall()

    def search_notes(self, query):
        """Simple full-text search across notes"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM notes WHERE content LIKE ? OR title LIKE ? ORDER BY updated_at DESC",
            (f"%{query}%", f"%{query}%")
        )
        return cursor.fetchall()