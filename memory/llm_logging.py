"""Logging des appels LLM conversationnel — table dédiée + calcul de coût.

Étape 3 V1 Niveau 2. Réutilise la DB principale `/root/memoire.db` (même fichier que
ConversationSession et pending_actions). Schéma idempotent.
"""
from datetime import datetime

import aiosqlite

DB_PATH = "/root/memoire.db"

# Pricing Claude Sonnet 4.5 (USD per token).
SONNET_45_INPUT_PRICE = 3.0 / 1_000_000   # $3 / 1M input tokens
SONNET_45_OUTPUT_PRICE = 15.0 / 1_000_000  # $15 / 1M output tokens


async def init_llm_logging_schema(db_path: str = DB_PATH):
    """Crée la table conversation_llm_calls + index si absents. Idempotent."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversation_llm_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                chat_id TEXT,
                session_id TEXT,
                model TEXT,
                iteration INTEGER,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd REAL,
                stop_reason TEXT
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_llm_calls_date "
            "ON conversation_llm_calls(created_at DESC)"
        )
        await db.commit()


async def log_llm_call(
    chat_id: str,
    session_id: str,
    model: str,
    iteration: int,
    tokens_in: int,
    tokens_out: int,
    stop_reason: str,
    db_path: str = DB_PATH,
):
    """Logue un appel LLM avec calcul du coût Sonnet 4.5."""
    cost = tokens_in * SONNET_45_INPUT_PRICE + tokens_out * SONNET_45_OUTPUT_PRICE
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO conversation_llm_calls "
            "(chat_id, session_id, model, iteration, tokens_in, tokens_out, cost_usd, stop_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(chat_id), session_id, model, iteration, tokens_in, tokens_out, cost, stop_reason),
        )
        await db.commit()


async def get_daily_cost(date_str: str = None, db_path: str = DB_PATH) -> float:
    """Coût total d'une journée (par défaut aujourd'hui, format 'YYYY-MM-DD').

    Utile pour le seuil de garde-fou ($3/jour côté V1).
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM conversation_llm_calls "
            "WHERE DATE(created_at) = ?",
            (date_str,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0.0
