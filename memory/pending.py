"""
Pending actions — table SQLite pour le flux OUI/NON de validation.
Un pending action = alerte envoyée à Julien + action à exécuter après confirmation.
"""
import aiosqlite
import json
from datetime import datetime, timedelta

DB_PATH = "/root/memoire.db"


async def init_pending_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_data TEXT NOT NULL,
                options TEXT NOT NULL,
                statut TEXT DEFAULT 'en_attente',
                created_at TEXT,
                expires_at TEXT,
                reponse_choisie TEXT,
                dernier_rappel_at TEXT,
                nb_rappels INTEGER DEFAULT 0
            )
        """)
        try:
            await db.execute("ALTER TABLE pending_actions ADD COLUMN dernier_rappel_at TEXT")
            await db.commit()
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE pending_actions ADD COLUMN nb_rappels INTEGER DEFAULT 0")
            # Backfill V1.0.1 : un pending qui a déjà un dernier_rappel_at sous V1.0.0 a reçu 1 rappel
            await db.execute(
                "UPDATE pending_actions SET nb_rappels = 1 WHERE dernier_rappel_at IS NOT NULL AND nb_rappels = 0"
            )
            await db.commit()
        except Exception:
            pass


async def creer_pending(source: str, item_id: str, item_data: dict, options: list[str]) -> int:
    """Crée une action en attente. Retourne l'ID."""
    now = datetime.now()
    expires = (now + timedelta(hours=24)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO pending_actions (source, item_id, item_data, options, statut, created_at, expires_at)
               VALUES (?, ?, ?, ?, 'en_attente', ?, ?)""",
            (source, item_id, json.dumps(item_data, ensure_ascii=False),
             json.dumps(options, ensure_ascii=False), now.isoformat(), expires)
        )
        await db.commit()
        return cursor.lastrowid


async def get_pending_actif() -> dict | None:
    """Retourne le pending action actif le plus récent (en_attente).
    Pas de filtre expires_at : un pending reste actif jusqu'à ce que Julien réponde explicitement."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT id, source, item_id, item_data, options, created_at
               FROM pending_actions
               WHERE statut = 'en_attente'
               ORDER BY created_at DESC LIMIT 1"""
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "source": row[1],
        "item_id": row[2],
        "item_data": json.loads(row[3]),
        "options": json.loads(row[4]),
        "created_at": row[5],
    }


async def get_tous_pending_actifs() -> list[dict]:
    """Retourne tous les pending en_attente, du plus récent au plus ancien.
    Pas de filtre expires_at : un pending disparaît uniquement quand Julien répond (OUI→envoye / NON→ignore)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT id, source, item_id, item_data, options, created_at, dernier_rappel_at
               FROM pending_actions
               WHERE statut = 'en_attente'
               ORDER BY created_at DESC"""
        )
        rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "source": row[1],
            "item_id": row[2],
            "item_data": json.loads(row[3]),
            "options": json.loads(row[4]),
            "created_at": row[5],
            "dernier_rappel_at": row[6],
        }
        for row in rows
    ]


async def get_pending_a_rappeler() -> list[dict]:
    """
    V1.0.1 — Cadence des rappels :
    - 1er rappel à J+1 (24h après création) si nb_rappels = 0
    - 2e rappel à J+7 si nb_rappels = 1
    - Après J+7 (nb_rappels >= 2) : plus aucun rappel
    - Dédoublonnage strict : jamais 2 rappels du même ID dans les 12h
    """
    now = datetime.now()
    seuil_24h = (now - timedelta(hours=24)).isoformat()
    seuil_7j = (now - timedelta(days=7)).isoformat()
    seuil_12h = (now - timedelta(hours=12)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT id, source, item_id, item_data, options, created_at, dernier_rappel_at, nb_rappels
               FROM pending_actions
               WHERE statut = 'en_attente'
                 AND (
                       (COALESCE(nb_rappels, 0) = 0 AND created_at < ?)
                       OR
                       (COALESCE(nb_rappels, 0) = 1 AND created_at < ? AND (dernier_rappel_at IS NULL OR dernier_rappel_at < ?))
                     )""",
            (seuil_24h, seuil_7j, seuil_12h)
        )
        rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "source": row[1],
            "item_id": row[2],
            "item_data": json.loads(row[3]),
            "options": json.loads(row[4]),
            "created_at": row[5],
            "dernier_rappel_at": row[6],
            "nb_rappels": row[7] or 0,
        }
        for row in rows
    ]


async def marquer_rappel_envoye(pending_id: int):
    """Persiste la trace du rappel : timestamp + incrément du compteur."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE pending_actions
               SET dernier_rappel_at = ?,
                   nb_rappels = COALESCE(nb_rappels, 0) + 1
               WHERE id = ?""",
            (datetime.now().isoformat(), pending_id)
        )
        await db.commit()


async def confirmer_pending(pending_id: int, reponse_choisie: str):
    """Marque un pending comme confirmé avec le texte final."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pending_actions SET statut = 'confirme', reponse_choisie = ? WHERE id = ?",
            (reponse_choisie, pending_id)
        )
        await db.commit()


async def marquer_envoye(pending_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pending_actions SET statut = 'envoye' WHERE id = ?",
            (pending_id,)
        )
        await db.commit()


async def ignorer_pending(pending_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pending_actions SET statut = 'ignore' WHERE id = ?",
            (pending_id,)
        )
        await db.commit()



async def get_pending_confirme_orphelin() -> dict | None:
    """
    Retourne le pending le plus récent avec statut 'confirme' ET reponse_choisie non nulle.
    Utilisé au démarrage pour récupérer les confirmations perdues lors d'un restart.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT id, source, item_id, item_data, options, created_at, reponse_choisie
               FROM pending_actions
               WHERE statut = 'confirme' AND reponse_choisie IS NOT NULL
               ORDER BY created_at DESC LIMIT 1"""
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "source": row[1],
        "item_id": row[2],
        "item_data": json.loads(row[3]),
        "options": json.loads(row[4]),
        "created_at": row[5],
        "reponse_choisie": row[6],
    }


async def get_pending_by_item_id(source: str, item_id: str) -> dict | None:
    """Retourne le pending (en_attente ou autre) le plus récent pour un (source, item_id)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT id, source, item_id, item_data, options, created_at, statut
               FROM pending_actions
               WHERE source = ? AND item_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (source, item_id)
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "source": row[1],
        "item_id": row[2],
        "item_data": json.loads(row[3]),
        "options": json.loads(row[4]),
        "created_at": row[5],
        "statut": row[6],
    }


async def update_pending_item_data(pending_id: int, item_data: dict):
    """Met à jour item_data d'un pending — utile quand l'UID/folder change côté IMAP."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pending_actions SET item_data = ? WHERE id = ?",
            (json.dumps(item_data, ensure_ascii=False), pending_id)
        )
        await db.commit()


async def item_deja_traite(source: str, item_id: str) -> bool:
    """Vérifie si un item a déjà été envoyé à Telegram (évite les doublons)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM pending_actions WHERE source = ? AND item_id = ? AND statut != 'en_attente'",
            (source, item_id)
        )
        row = await cursor.fetchone()
        if row:
            return True
        cursor = await db.execute(
            "SELECT id FROM pending_actions WHERE source = ? AND item_id = ? AND statut = 'en_attente'",
            (source, item_id)
        )
        row = await cursor.fetchone()
        return row is not None
