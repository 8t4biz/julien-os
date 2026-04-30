import aiosqlite
from datetime import datetime
from anthropic import Anthropic
import sys
sys.path.insert(0, "/root")
from config import ANTHROPIC_API_KEY

client = Anthropic(api_key=ANTHROPIC_API_KEY)
DB_PATH = "/root/memoire.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS memoire (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                type_agent TEXT,
                input TEXT,
                output TEXT,
                resume TEXT,
                projet TEXT
            )
        """)
        try:
            await db.execute("ALTER TABLE memoire ADD COLUMN resume TEXT")
        except Exception:
            pass
        # Table alertes personnalisées par projet
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alertes_custom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                projet TEXT NOT NULL,
                mot_cle TEXT NOT NULL,
                UNIQUE(projet, mot_cle)
            )
        """)
        # Table pour stocker le chat_id Telegram de Julien
        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                cle TEXT PRIMARY KEY,
                valeur TEXT
            )
        """)
        await db.commit()


async def generer_resume(type_agent: str, input_text: str, output_text: str) -> str:
    prompt = (
        "Resume cet echange en 4-5 phrases cles, en gardant les informations essentielles : "
        "noms, decisions, actions, risques, dates.\n\n"
        f"Type d'echange : {type_agent}\n\n"
        f"Input :\n{input_text[:2000]}\n\n"
        f"Output :\n{output_text[:3000]}\n\n"
        "Resume concis et factuel :"
    )
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


async def sauvegarder(type_agent: str, input_text: str, output_text: str, projet: str = "general"):
    resume = await generer_resume(type_agent, input_text, output_text)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO memoire (date, type_agent, input, output, resume, projet) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), type_agent, input_text[:3000], output_text[:5000], resume, projet)
        )
        await db.commit()


async def recuperer_contexte(projet: str = None, limite: int = 5) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        if projet and projet != "general":
            cursor = await db.execute(
                "SELECT date, type_agent, resume FROM memoire WHERE projet = ? ORDER BY date DESC LIMIT ?",
                (projet, limite)
            )
        else:
            cursor = await db.execute(
                "SELECT date, type_agent, resume FROM memoire ORDER BY date DESC LIMIT ?",
                (limite,)
            )
        rows = await cursor.fetchall()
    if not rows:
        return ""
    contexte = "Historique recent :\n"
    for row in reversed(rows):
        date, type_agent, resume = row
        contexte += f"\n[{date[:10]} - {type_agent}]\n{resume or '(pas de resume)'}\n"
    return contexte


async def recuperer_tout_historique(projet: str, jours: int = 90) -> list[dict]:
    """Retourne tous les enregistrements d'un projet sur N jours."""
    from datetime import timedelta
    date_limite = (datetime.now() - timedelta(days=jours)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT date, type_agent, input, output, resume FROM memoire "
            "WHERE projet = ? AND date >= ? ORDER BY date ASC",
            (projet, date_limite)
        )
        rows = await cursor.fetchall()
    return [
        {"date": r[0], "type_agent": r[1], "input": r[2], "output": r[3], "resume": r[4]}
        for r in rows
    ]


async def lister_projets():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT projet, COUNT(*) as nb, MAX(date) as derniere FROM memoire GROUP BY projet ORDER BY derniere DESC"
        )
        return await cursor.fetchall()


def normaliser_projet(projet: str) -> str:
    projet = projet.lower().strip()
    if projet in ["ia", "industrial alliance", "i.a.", "industrielle alliance", "industriel alliance", "ia groupe", "ia financier"]:
        return "iA"
    if projet in ["vacances", "france", "pays basque", "limoges", "voyage"]:
        return "vacances-france"
    if projet in ["airbnb", "locataire", "voyageur"]:
        return "airbnb"
    if projet in ["linkedin", "prospect", "prospection"]:
        return "prospection"
    return "general"


# ── Alertes personnalisées ────────────────────────────────────────────────────

async def ajouter_alerte(projet: str, mot_cle: str) -> bool:
    """Ajoute un mot-clé d'alerte pour un projet. Retourne True si ajouté, False si déjà existant."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO alertes_custom (projet, mot_cle) VALUES (?, ?)",
                (projet, mot_cle.lower().strip())
            )
            await db.commit()
        return True
    except Exception:
        return False


async def supprimer_alerte(projet: str, mot_cle: str) -> bool:
    """Supprime un mot-clé d'alerte. Retourne True si supprimé."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM alertes_custom WHERE projet = ? AND mot_cle = ?",
            (projet, mot_cle.lower().strip())
        )
        await db.commit()
        return cursor.rowcount > 0


async def lister_alertes(projet: str) -> list[str]:
    """Retourne les mots-clés custom d'un projet."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT mot_cle FROM alertes_custom WHERE projet = ? ORDER BY mot_cle",
            (projet,)
        )
        rows = await cursor.fetchall()
    return [r[0] for r in rows]


async def recuperer_alertes_projet(projet: str) -> list[str]:
    """Retourne les mots-clés custom pour un projet donné."""
    return await lister_alertes(projet)


# ── Config / chat_id ─────────────────────────────────────────────────────────

async def sauvegarder_chat_id(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO config (cle, valeur) VALUES ('chat_id', ?)",
            (str(chat_id),)
        )
        await db.commit()


async def recuperer_chat_id() -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT valeur FROM config WHERE cle = 'chat_id'")
        row = await cursor.fetchone()
    return int(row[0]) if row else None
