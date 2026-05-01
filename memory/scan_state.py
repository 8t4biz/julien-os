"""V1.0.3 — Persistance du dernier scan watcher pour /synthese."""
import aiosqlite
from datetime import datetime

DB_PATH = "/root/memoire.db"


async def init_scan_state_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scan_state (
                source TEXT PRIMARY KEY,
                last_at TEXT NOT NULL,
                total INTEGER NOT NULL,
                actionable INTEGER NOT NULL,
                bruit INTEGER NOT NULL
            )
        """)
        await db.commit()


async def enregistrer_scan(source: str, total: int, actionable: int, bruit: int):
    """Upsert de l'état du dernier scan pour une source donnée."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO scan_state (source, last_at, total, actionable, bruit)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(source) DO UPDATE SET
                   last_at = excluded.last_at,
                   total = excluded.total,
                   actionable = excluded.actionable,
                   bruit = excluded.bruit""",
            (source, datetime.now().isoformat(), total, actionable, bruit),
        )
        await db.commit()


async def get_dernier_scan(source: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT last_at, total, actionable, bruit FROM scan_state WHERE source = ?",
            (source,),
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return {
        "at": row[0],
        "total": row[1],
        "actionable": row[2],
        "bruit": row[3],
    }
