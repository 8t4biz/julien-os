"""
Mémoire conversationnelle Telegram — session 4h glissante, cap dur 20 messages.

Étape 1 V1 Niveau 2 : socle pour permettre à Julien d'écrire en texte libre
dans Telegram. Une session = fenêtre 4h depuis le dernier message du chat.
Si dépassement → nouvelle session. /reset force aussi un nouveau session_id.

API synchrone (sqlite3), volontairement minimaliste — pas de résumé auto en V1,
les messages au-delà de 20 sont tronqués FIFO côté lecture.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta

DB_PATH = "/root/memoire.db"
SESSION_WINDOW_HOURS = 4
HARD_CAP_MESSAGES = 20


class ConversationSession:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_schema()

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.execute("PRAGMA foreign_keys = ON")
        return c

    def _ensure_schema(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_call_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation_messages(session_id, created_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_conv_chat ON conversation_messages(chat_id, created_at DESC)")
            c.execute("""
                CREATE TABLE IF NOT EXISTS conversation_resets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    reset_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_resets_chat ON conversation_resets(chat_id, reset_at DESC)")
            c.commit()

    @staticmethod
    def _parse_ts(ts: str) -> datetime:
        # SQLite CURRENT_TIMESTAMP -> 'YYYY-MM-DD HH:MM:SS' ; on accepte aussi ISO
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")

    def get_or_create_session(self, chat_id: str) -> str:
        chat_id = str(chat_id)
        with self._conn() as c:
            cur = c.execute(
                "SELECT session_id, created_at FROM conversation_messages "
                "WHERE chat_id = ? ORDER BY datetime(created_at) DESC LIMIT 1",
                (chat_id,),
            )
            row = cur.fetchone()
            if not row:
                return str(uuid.uuid4())

            last_session_id, last_created = row
            last_dt = self._parse_ts(last_created)

            cur = c.execute(
                "SELECT reset_at FROM conversation_resets WHERE chat_id = ? "
                "ORDER BY datetime(reset_at) DESC LIMIT 1",
                (chat_id,),
            )
            reset_row = cur.fetchone()
            if reset_row:
                reset_dt = self._parse_ts(reset_row[0])
                if reset_dt >= last_dt:
                    return str(uuid.uuid4())

            if datetime.now() - last_dt >= timedelta(hours=SESSION_WINDOW_HOURS):
                return str(uuid.uuid4())

            return last_session_id

    def add_message(self, chat_id: str, role: str, content, tool_call_id: str = None):
        chat_id = str(chat_id)
        if role not in ("user", "assistant", "tool"):
            raise ValueError(f"role invalide: {role!r} (attendu user|assistant|tool)")

        if isinstance(content, str):
            content_str = content
        else:
            content_str = json.dumps(content, ensure_ascii=False)

        session_id = self.get_or_create_session(chat_id)
        with self._conn() as c:
            c.execute(
                "INSERT INTO conversation_messages (chat_id, session_id, role, content, tool_call_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (chat_id, session_id, role, content_str, tool_call_id),
            )
            c.commit()

    def get_messages(self, chat_id: str) -> list[dict]:
        chat_id = str(chat_id)
        session_id = self.get_or_create_session(chat_id)
        with self._conn() as c:
            cur = c.execute(
                "SELECT role, content, tool_call_id FROM conversation_messages "
                "WHERE chat_id = ? AND session_id = ? "
                "ORDER BY datetime(created_at) DESC, id DESC LIMIT ?",
                (chat_id, session_id, HARD_CAP_MESSAGES),
            )
            rows = cur.fetchall()

        rows.reverse()
        messages = []
        for role, content, tool_call_id in rows:
            try:
                parsed = json.loads(content)
                content_value = parsed if isinstance(parsed, (list, dict)) else content
            except (json.JSONDecodeError, TypeError):
                content_value = content
            msg = {"role": role, "content": content_value}
            if tool_call_id:
                msg["tool_call_id"] = tool_call_id
            messages.append(msg)
        return messages

    def reset(self, chat_id: str):
        chat_id = str(chat_id)
        with self._conn() as c:
            c.execute(
                "INSERT INTO conversation_resets (chat_id, reset_at) VALUES (?, ?)",
                (chat_id, datetime.now().isoformat(sep=" ", timespec="seconds")),
            )
            c.commit()
