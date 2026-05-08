"""Wrappers Anthropic Tool API pour gérer les emails Proton via LLM conversationnel.

Wrappers async natifs : conçus pour être awaités depuis le handler Telegram async
(qui tourne dans une boucle déjà active — d'où l'interdiction d'asyncio.run).

NOREPLY_PATTERNS DOIT rester aligné avec /root/julien_os/main.py _executer_action ;
toute modification du blocage SMTP doit être faite des deux côtés.
"""
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = "/root/memoire.db"

# Synchronisé avec main.py:195 _executer_action — 6 patterns no-reply.
NOREPLY_PATTERNS = (
    "noreply",
    "no-reply",
    "automated",
    "do-not-reply",
    "donotreply",
    "do_not_reply",
)


# ── Définitions outils Anthropic Messages API ─────────────────────────────────

EMAIL_TOOLS = [
    {
        "name": "read_emails",
        "description": (
            "Liste les emails Proton en attente (pendings actifs). Chaque entrée commence par "
            "#N où N est l'identifiant pending stable affiché à Julien dans Telegram. "
            "Utilise quand Julien demande à voir sa liste, ou pour identifier le bon #N "
            "avant de cibler un email."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10},
                "sender_filter": {
                    "type": "string",
                    "description": "Recherche partielle dans l'expéditeur. Ex: 'zohra'.",
                },
            },
        },
    },
    {
        "name": "get_email_details",
        "description": (
            "Affiche le contenu complet d'un email (intent READ). À appeler quand Julien dit "
            "« ouvre #N », « lis #N », « montre #N », « contenu de #N », « affiche #N ». "
            "Le paramètre email_id est la valeur N (ex: '12' pour #12). NE génère PAS de "
            "réponse, n'appelle PAS suggest_email_reply après — c'est une lecture seule."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"email_id": {"type": "string", "description": "L'identifiant N de #N."}},
            "required": ["email_id"],
        },
    },
    {
        "name": "suggest_email_reply",
        "description": (
            "Génère un brouillon de réponse pour un email (intent REPLY). À appeler quand Julien "
            "dit « réponds à #N », « rédige une réponse à #N », « propose une réponse pour #N ». "
            "tone_hint optionnel : 'direct', 'amical', 'formel', 'court'. Affiche toujours le "
            "draft à Julien et demande confirmation OUI explicite avant d'envoyer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string", "description": "L'identifiant N de #N."},
                "tone_hint": {"type": "string"},
            },
            "required": ["email_id"],
        },
    },
    {
        "name": "send_email_reply",
        "description": (
            "Envoie effectivement une réponse à un email. NE JAMAIS appeler sans confirmation "
            "OUI explicite de Julien dans le tour de conversation précédent. Refuse "
            "automatiquement si le destinataire est un noreply."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string", "description": "L'identifiant N de #N."},
                "body": {"type": "string"},
            },
            "required": ["email_id", "body"],
        },
    },
]


# ── Helpers — adaptateurs vers les fonctions métier existantes ────────────────

async def _fetch_pendings():
    """Async. get_tous_pending_actifs est déjà `async def` (aiosqlite) → await direct."""
    from julien_os.memory.pending import get_tous_pending_actifs
    return [p for p in await get_tous_pending_actifs() if p["source"] == "protonmail"]


def _fetch_pending_by_pending_id(email_id):
    """Sync. Lecture SQLite locale unique par PK — quelques µs, pas de besoin async/to_thread.

    Pas de fonction métier équivalente existante (get_pending_by_item_id veut un Message-ID),
    on lit directement la table — schéma identique à memory/pending.py.
    """
    try:
        pid = int(email_id)
    except (TypeError, ValueError):
        return None
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "SELECT id, source, item_id, item_data, options, statut, created_at "
            "FROM pending_actions WHERE id = ?",
            (pid,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "source": row[1],
        "item_id": row[2],
        "item_data": json.loads(row[3]),
        "options": json.loads(row[4]),
        "statut": row[5],
        "created_at": row[6],
    }


async def _analyse_with_llm(item_data):
    """Async. analyser_et_generer est déjà `async def` → await direct."""
    from julien_os.agents.protonmail_agent import analyser_et_generer
    return await analyser_et_generer(item_data)


async def _send_smtp_reply(item_data, body):
    """Async. ProtonMailClient.reply_to_email est `async def` → await direct.

    Note : reply_to_email utilise encore imaplib/smtplib bloquants en interne (code
    smell existant hors scope). Si en V2 ça devient un goulot, l'envelopper ici
    avec asyncio.to_thread sans toucher à protonmail.py.

    Retourne (ok: bool, err: str | None).
    """
    from julien_os.config import PROTONMAIL_BRIDGE_PASSWORD, PROTONMAIL_EMAIL
    from julien_os.tools.protonmail import ProtonMailClient

    client = ProtonMailClient(
        email_addr=PROTONMAIL_EMAIL,
        bridge_password=PROTONMAIL_BRIDGE_PASSWORD,
    )
    folder = item_data.get("folder") or "INBOX"
    try:
        ok = await client.reply_to_email(
            email_id=item_data.get("id", ""),
            reply_text=body,
            uid=item_data.get("uid", ""),
            folder=folder,
        )
    except Exception as e:
        return False, f"exception SMTP : {e}"
    return ok, None


def _format_pending_summary(p):
    item = p["item_data"]
    snippet = (item.get("snippet") or item.get("body", "") or "").strip().replace("\n", " ")
    return (
        f"#{p['id']} De: {item.get('from', '?')}\n"
        f"    Sujet: {item.get('subject', '?')}\n"
        f"    Date: {item.get('date', '?')}\n"
        f"    Résumé: {snippet[:200]}"
    )


# ── Handlers async exposés au LLM ─────────────────────────────────────────────

async def execute_read_emails(limit: int = 10, sender_filter: str = None) -> str:
    """Stratégie : await _fetch_pendings (helper async sur get_tous_pending_actifs)."""
    pendings = await _fetch_pendings()
    if sender_filter:
        f = sender_filter.lower()
        pendings = [p for p in pendings if f in p["item_data"].get("from", "").lower()]
    try:
        n = max(1, int(limit))
    except (TypeError, ValueError):
        n = 10
    pendings = pendings[:n]
    if not pendings:
        if sender_filter:
            return f"Aucun email en attente correspondant à '{sender_filter}'."
        return "Aucun email en attente."
    return "\n\n".join(_format_pending_summary(p) for p in pendings)


async def execute_get_email_details(email_id: str) -> str:
    """Stratégie : appel sync direct de _fetch_pending_by_pending_id (lecture SQLite locale rapide).
    Pas de SMTP/IMAP ici : le corps est cache dans item_data['body'] par le watcher.
    """
    p = _fetch_pending_by_pending_id(email_id)
    if not p:
        return f"Erreur : email_id {email_id} introuvable."
    item = p["item_data"]
    body = item.get("body") or item.get("snippet") or "(corps vide)"
    return (
        f"De: {item.get('from', '?')}\n"
        f"Sujet: {item.get('subject', '?')}\n"
        f"Date: {item.get('date', '?')}\n\n"
        f"{body}"
    )


async def execute_suggest_email_reply(email_id: str, tone_hint: str = None) -> str:
    """Stratégie : sync local (_fetch_pending_by_pending_id) + await LLM (_analyse_with_llm).

    Limitation : analyser_et_generer n'accepte pas tone_hint. On l'ajoute en suffixe pour
    que le LLM appelant l'applique avant validation. À refactor proprement plus tard.
    """
    p = _fetch_pending_by_pending_id(email_id)
    if not p:
        return f"Erreur : email_id {email_id} introuvable."
    result = await _analyse_with_llm(p["item_data"])
    courte = result.get("option_courte", "(option courte indisponible)")
    complete = result.get("option_complete", "(option complète indisponible)")
    suffix = ""
    if tone_hint:
        suffix = (
            f"\n\n(Tonalité demandée: {tone_hint} — l'agent existant ne l'applique pas "
            "automatiquement, à ajuster côté LLM avant validation.)"
        )
    return (
        "Suggestion COURTE :\n"
        f"{courte}\n\n"
        "Suggestion COMPLÈTE :\n"
        f"{complete}"
        f"{suffix}"
    )


async def execute_send_email_reply(email_id: str, body: str) -> str:
    """Stratégie : sync local (_fetch_pending_by_pending_id + check noreply) puis await SMTP.

    Le check noreply doit rester AVANT tout await SMTP — préserve le contrat de _executer_action.
    """
    p = _fetch_pending_by_pending_id(email_id)
    if not p:
        return f"Erreur : email_id {email_id} introuvable."
    item = p["item_data"]
    expediteur = item.get("from", "").lower()
    if any(pat in expediteur for pat in NOREPLY_PATTERNS):
        return (
            f"Envoi bloqué : {item.get('from', '?')} est une adresse no-reply. "
            "SMTP refusé conformément au filtre _executer_action."
        )
    ok, err = await _send_smtp_reply(item, body)
    if err:
        return f"Erreur envoi : {err}"
    return "Envoyé." if ok else "Échec SMTP."


EMAIL_HANDLERS = {
    "read_emails": execute_read_emails,
    "get_email_details": execute_get_email_details,
    "suggest_email_reply": execute_suggest_email_reply,
    "send_email_reply": execute_send_email_reply,
}
