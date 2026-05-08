"""
Outil Notion — BDD_Notes_Inbox + Tableau de bord iA
Nécessite : pip install notion-client
Credentials : variable d'environnement NOTION_TOKEN (voir julien_os.config).
"""
import datetime
import logging

from julien_os.config import NOTION_TOKEN
from notion_client import AsyncClient

logger = logging.getLogger(__name__)

DATABASE_ID = "cdacef15-dfdd-457b-8a6c-f0eb83794237"

# Tableau de bord — Journal des réunions iA
TABLEAU_BORD_PAGE_ID = "33cfc1ded4cc818da2bbf542a4bcec0e"
# Divider juste après "Alimenté automatiquement par /cr dans Telegram"
# Les nouveaux CRs sont insérés après ce bloc → ordre antéchronologique
JOURNAL_AFTER_BLOCK_ID = "f882c695-f6d3-4964-b831-9bdae2921301"


def _get_token() -> str:
    return NOTION_TOKEN


async def creer_note(texte: str, titre: str = None, projet: str = None) -> str:
    """
    Crée une note dans BDD_Notes_Inbox.
    Retourne l'URL de la page créée.
    """
    notion = AsyncClient(auth=_get_token())
    today = datetime.date.today().isoformat()

    if not titre:
        first_line = texte.strip().split("\n")[0]
        titre = first_line[:80] if first_line else "Note"

    # Découpe le texte en blocs de 2000 chars max (limite Notion)
    blocs = []
    chunk_size = 2000
    for i in range(0, len(texte), chunk_size):
        blocs.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": texte[i:i + chunk_size]}
                }]
            }
        })

    page = await notion.pages.create(
        parent={"database_id": DATABASE_ID},
        properties={
            "Nom": {
                "title": [{"text": {"content": titre}}]
            },
            "Date": {
                "date": {"start": today}
            },
        },
        children=blocs or [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": []}
        }]
    )

    url = page.get("url", "")
    logger.info(f"Note créée : {url}")
    return url


async def lire_page(page_id: str) -> dict:
    """
    Lit une page Notion par ID.
    Retourne dict avec title, url, content (texte brut).
    """
    notion = AsyncClient(auth=_get_token())

    page = await notion.pages.retrieve(page_id=page_id)
    blocks_resp = await notion.blocks.children.list(block_id=page_id)

    # Titre
    title = ""
    for _key, val in page.get("properties", {}).items():
        if val.get("type") == "title":
            title = "".join(t.get("plain_text", "") for t in val.get("title", []))
            break

    # Contenu texte brut
    lines = []
    for block in blocks_resp.get("results", []):
        btype = block.get("type", "")
        rich = block.get(btype, {}).get("rich_text", [])
        text = "".join(r.get("plain_text", "") for r in rich)
        if text:
            lines.append(text)

    return {
        "id": page_id,
        "title": title,
        "url": page.get("url", ""),
        "content": "\n".join(lines),
    }


async def chercher(mot_cle: str, limit: int = 5) -> list[dict]:
    """
    Cherche dans le workspace Notion par mot-clé.
    Retourne une liste de dict {title, url, last_edited}.
    """
    notion = AsyncClient(auth=_get_token())
    resp = await notion.search(query=mot_cle, page_size=limit)

    results = []
    for r in resp.get("results", []):
        if r.get("object") not in ("page", "database"):
            continue

        title = ""
        props = r.get("properties", {})
        for val in props.values():
            if val.get("type") == "title":
                title = "".join(t.get("plain_text", "") for t in val.get("title", []))
                break

        if not title:
            # Fallback pour les databases
            title = r.get("title", [{}])[0].get("plain_text", "(sans titre)") if isinstance(r.get("title"), list) else "(sans titre)"

        results.append({
            "id": r["id"],
            "title": title or "(sans titre)",
            "url": r.get("url", ""),
            "last_edited": r.get("last_edited_time", "")[:10],
        })

    return results


async def ajouter_cr_ia(date_str: str, resume: str, plan_action: str) -> str:
    """
    Ajoute une entrée CR dans le Journal des réunions du tableau de bord iA.
    Insère après le divider du journal → ordre antéchronologique (le plus récent en haut).
    Retourne l'URL de la section journal.
    """
    notion = AsyncClient(auth=_get_token())

    def paragraphes(texte: str) -> list:
        """Découpe un texte long en blocs paragraphe de 2000 chars max."""
        blocs = []
        chunk = 2000
        for i in range(0, len(texte), chunk):
            blocs.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": texte[i:i + chunk]}}]
                }
            })
        return blocs

    blocks: list = [
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": f"CR — {date_str}"}}]
            }
        }
    ]

    if resume:
        blocks.extend(paragraphes(resume[:4000]))

    if plan_action:
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": plan_action[:2000]}}],
                "icon": {"type": "emoji", "emoji": "✅"},
                "color": "green_background",
            }
        })

    # Séparateur de fin d'entrée
    blocks.append({"object": "block", "type": "divider", "divider": {}})

    await notion.blocks.children.append(
        block_id=TABLEAU_BORD_PAGE_ID,
        children=blocks,
        after=JOURNAL_AFTER_BLOCK_ID,
    )

    url = f"https://www.notion.so/{TABLEAU_BORD_PAGE_ID.replace('-', '')}"
    logger.info(f"CR ajouté au journal Notion : {date_str}")
    return url
