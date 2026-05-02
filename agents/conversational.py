"""Agent conversationnel V1 Niveau 2 — Telegram texte libre, gestion email Proton.

V1.0.3.1 :
- Convention #N dans l'UI (où N = pending_actions.id)
- Distinction stricte intent read / intent reply
- Helper parse_pending_id_from_text + detect_intent (déterministes, exposés pour tests)
- Pas de fallback silencieux « premier pending »
- Plus aucun emoji, aucun **, aucun • dans les réponses

Reçoit un message texte de Julien, dialogue avec Claude Sonnet 4.5 en boucle tool_use,
loggue chaque appel LLM (tokens, coût), retourne le texte final à envoyer.

Async natif — conçu pour être awaité depuis le handler Telegram.
"""
import logging
import re

from anthropic import AsyncAnthropic
from config import ANTHROPIC_API_KEY

from ..memory.conversation import ConversationSession, DB_PATH as DEFAULT_DB_PATH
from ..memory.llm_logging import init_llm_logging_schema, log_llm_call
from ..tools import ALL_TOOLS, execute_tool

try:
    from ..profil import PROFIL as JULIEN_PROFILE_TEXT
except ImportError:  # pragma: no cover — sécurité, profil.py est censé exister
    JULIEN_PROFILE_TEXT = ""

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 2048
MAX_ITERATIONS = 5

# Mots-clés d'intent (français + un peu d'anglais usuel)
_INTENT_READ_KEYWORDS = (
    "ouvre", "ouvrir", "lis", "lire", "montre", "montrer",
    "affiche", "afficher", "détail", "detail", "contenu",
    "show", "open", "read",
)
_INTENT_REPLY_KEYWORDS = (
    "réponds", "repond", "réponse", "reponse", "rédige", "redige",
    "rédiger", "rediger", "propose", "draft",
    "reply", "respond", "answer",
)
_INTENT_SEND_KEYWORDS = ("envoie", "envoyer", "envois", "send")


def parse_pending_id_from_text(text: str) -> int | None:
    """Extrait le premier identifiant #N (ou nombre nu) du message.

    Tolère #12, # 12, ou un nombre seul après un mot-clé d'intent.
    Retourne None si aucun nombre clair n'est trouvé.
    """
    if not text:
        return None
    # Priorité au format explicite #N
    m = re.search(r"#\s*(\d+)", text)
    if m:
        return int(m.group(1))
    # Sinon : nombre nu après un mot-clé d'action (« ouvre 12 », « réponds à 5 »)
    keywords = _INTENT_READ_KEYWORDS + _INTENT_REPLY_KEYWORDS + _INTENT_SEND_KEYWORDS
    pattern = r"(?:" + "|".join(re.escape(k) for k in keywords) + r")\b[^\d]{0,15}(\d+)"
    m = re.search(pattern, text.lower())
    if m:
        return int(m.group(1))
    return None


def detect_intent(text: str) -> str | None:
    """Détecte l'intent dominant : 'read', 'reply', 'send', ou None si ambigu/inconnu.

    Si plusieurs intents sont présents, l'ordre de priorité est send > reply > read
    (un message « envoie » est plus engageant qu'un « rédige » qui est plus engageant
    qu'un « ouvre »).
    """
    if not text:
        return None
    low = text.lower()
    has_read = any(re.search(r"\b" + re.escape(k), low) for k in _INTENT_READ_KEYWORDS)
    has_reply = any(re.search(r"\b" + re.escape(k), low) for k in _INTENT_REPLY_KEYWORDS)
    has_send = any(re.search(r"\b" + re.escape(k), low) for k in _INTENT_SEND_KEYWORDS)
    if has_send:
        return "send"
    if has_reply:
        return "reply"
    if has_read:
        return "read"
    return None


# Consignes V1.0.3.1 — séparées du profil pour pouvoir tester l'absence d'emoji/markdown
# sans inclure le contenu (parfois enrichi en Markdown) du profil personnel de Julien.
_INSTRUCTIONS_V103_1 = """Règles de conversation :
- Réponses courtes adaptées à Telegram (mobile)
- Aucun emoji. Aucune mise en forme Markdown (ni gras, ni italique, ni tableaux, ni listes à puces typographiques)
- Français par défaut, guillemets « », pas de tirets longs
- Direct, pas de flatterie
- Challenge les incohérences si tu en repères

Convention identifiants :
- Les emails sont identifiés par #N dans l'UI Telegram, où N est l'ID interne du pending (pending_actions.id).
- Quand Julien dit « #12 » ou « 12 », c'est ce N.
- N est stable et unique. Il n'a aucun rapport avec l'UID IMAP du serveur Proton.
- Pour appeler un outil, passe N en string comme email_id (ex: email_id="12").

Distinction lecture (READ) vs réponse (REPLY) :
- « ouvre #N », « lis #N », « montre #N », « contenu de #N », « affiche #N », « détail #N »
  -> appelle UNIQUEMENT get_email_details. Ne génère PAS de réponse, n'appelle PAS suggest_email_reply.
- « réponds à #N », « rédige une réponse à #N », « propose une réponse pour #N »
  -> appelle suggest_email_reply (au besoin précédé de get_email_details si tu n'as pas le contexte).
  Affiche le draft. TERMINE TOUJOURS ta réponse par EXACTEMENT cette phrase, sans
  ajout, sans variante, sans option de modification :

      Tape OUI pour envoyer, NON pour annuler.

  Une seule décision binaire à la fois. Si Julien veut une autre version, il
  répondra NON puis demandera explicitement (« réponds à #N en plus court »
  par exemple) et tu généreras un nouveau draft.
- « envoie », « envoyer », « OUI » après une suggestion -> appelle send_email_reply.
- « NON » après une suggestion -> n'envoie rien, confirme à Julien que le pending
  reste en attente. Une seule phrase.
- Phrase ambiguë qui combine deux intents (« ouvre #12 et propose une réponse ») :
  fais les deux dans l'ordre — d'abord get_email_details, puis suggest_email_reply.

Cas où l'identifiant n'est pas explicite :
- Si Julien ne mentionne pas de #N et qu'un seul pending est en statut en_attente,
  utilise celui-là (en l'annonçant : « Je prends #N de Untel sur Sujet, ok ? »).
- Si plusieurs pendings sont en attente et que Julien n'a pas précisé,
  appelle read_emails et demande à Julien quel #N viser. Ne choisis JAMAIS au hasard.

Outils disponibles : email Proton uniquement (lire la liste, voir détail, suggérer réponse, envoyer).

Si Julien demande quelque chose hors gestion email (Notion, agenda, etc.), dis que tu ne couvres
que les emails dans cette version V1.
"""

SYSTEM_PROMPT = (
    "Tu es l'assistant personnel de Julien, accessible via Telegram.\n\n"
    "Profil de Julien :\n"
    f"{JULIEN_PROFILE_TEXT}\n\n"
    f"{_INSTRUCTIONS_V103_1}"
)

_client = None


def _get_client() -> AsyncAnthropic:
    """Instance unique du client Anthropic — paresseuse pour faciliter le mocking en test."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    """Adapte la sortie de ConversationSession.get_messages au format API Anthropic."""
    out = []
    for m in messages:
        role = "user" if m["role"] == "tool" else m["role"]
        out.append({"role": role, "content": m["content"]})
    return out


async def handle_conversation(
    chat_id: str,
    user_message: str,
    db_path: str = None,
) -> str:
    """Point d'entrée — reçoit un texte Julien, retourne le texte de réponse Telegram.

    Boucle tool_use limitée à MAX_ITERATIONS=5. Chaque appel LLM est loggé.
    """
    db = db_path or DEFAULT_DB_PATH
    await init_llm_logging_schema(db_path=db)

    session = ConversationSession(db_path=db)
    session.add_message(chat_id, role="user", content=user_message)
    session_id = session.get_or_create_session(chat_id)

    client = _get_client()

    for iteration in range(MAX_ITERATIONS):
        messages = _to_anthropic_messages(session.get_messages(chat_id))

        try:
            response = await client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=ALL_TOOLS,
                messages=messages,
            )
        except Exception as e:
            logger.error(f"handle_conversation: API error iter={iteration} : {e}")
            return f"Erreur API Anthropic : {e}. Réessaie."

        await log_llm_call(
            chat_id=str(chat_id),
            session_id=session_id,
            model=getattr(response, "model", MODEL),
            iteration=iteration,
            tokens_in=getattr(response.usage, "input_tokens", 0) or 0,
            tokens_out=getattr(response.usage, "output_tokens", 0) or 0,
            stop_reason=getattr(response, "stop_reason", "?") or "?",
            db_path=db,
        )

        content_blocks = [b.model_dump() for b in response.content]
        session.add_message(chat_id, role="assistant", content=content_blocks)

        if response.stop_reason == "tool_use":
            for block in response.content:
                if block.type == "tool_use":
                    result = await execute_tool(block.name, block.input)
                    session.add_message(
                        chat_id,
                        role="tool",
                        content=[{
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        }],
                        tool_call_id=block.id,
                    )
            continue

        text = "".join(b.text for b in response.content if b.type == "text")
        return text or "Action effectuée."

    return "Désolé, j'ai dépassé 5 itérations sans aboutir. Reformule."
