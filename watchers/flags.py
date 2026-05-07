"""
Flags persistants pour les watchers — stockés en SQLite.
Survit aux redémarrages du bot. Partagé entre airbnb_watcher et protonmail_watcher.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)

_DB_PATH = "/root/memoire.db"

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS watcher_flags (
    cle  TEXT PRIMARY KEY,
    val  INTEGER NOT NULL DEFAULT 0
);
"""


def _conn():
    c = sqlite3.connect(_DB_PATH, timeout=5)
    c.execute(_INIT_SQL)
    return c


def alerte_deja_envoyee(cle: str) -> bool:
    """Retourne True si le flag 'cle' est posé."""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT val FROM watcher_flags WHERE cle = ?", (cle,)
            ).fetchone()
            return bool(row and row[0])
    except Exception as e:
        logger.warning(f"flags.alerte_deja_envoyee({cle}) error: {e}")
        return False


def marquer_alerte(cle: str):
    """Pose le flag 'cle'."""
    try:
        with _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO watcher_flags (cle, val) VALUES (?, 1)",
                (cle,)
            )
    except Exception as e:
        logger.warning(f"flags.marquer_alerte({cle}) error: {e}")


def reset_alerte(cle: str):
    """Supprime le flag 'cle'."""
    try:
        with _conn() as c:
            c.execute("DELETE FROM watcher_flags WHERE cle = ?", (cle,))
    except Exception as e:
        logger.warning(f"flags.reset_alerte({cle}) error: {e}")
