"""Agent conversationnel V1 Niveau 2 — Telegram texte libre, gestion email Proton.

Reçoit un message texte de Julien, dialogue avec Claude Sonnet 4.5 en boucle tool_use,
loggue chaque appel LLM (tokens, coût), retourne le texte final à envoyer.

Async natif — conçu pour être awaité depuis le handler Telegram.
"""
import logging

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

SYSTEM_PROMPT = f"""Tu es l'assistant personnel de Julien, accessible via Telegram.

Profil de Julien :
{JULIEN_PROFILE_TEXT}

Règles de conversation :
- Réponses courtes adaptées à Telegram (mobile)
- Pas de markdown lourd : pas de tableaux, pas de ***, pas de listes à puces excessives
- Français par défaut, guillemets « », pas de tirets longs
- Direct, pas de flatterie
- Challenge les incohérences si tu en repères

Outils disponibles : email Proton uniquement (lire, voir détail, suggérer réponse, envoyer).

Comportement :
- Lis et analyse sans demander la permission
- Demande confirmation explicite avant tout envoi d'email
- Si Julien demande quelque chose qui sort de la gestion email (Notion, agenda, etc.),
  réponds que tu ne couvres que les emails dans cette version V1
"""

_client = None


def _get_client() -> AsyncAnthropic:
    """Instance unique du client Anthropic — paresseuse pour faciliter le mocking en test."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    """Adapte la sortie de ConversationSession.get_messages au format API Anthropic.

    - role='tool' (notre convention de stockage) → role='user' (Anthropic n'a pas de rôle 'tool',
      les tool_result sont des content blocks dans des messages user).
    - On retire toute clé top-level non supportée (ex: 'tool_call_id' annoté côté DB).
    """
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

    Boucle tool_use limitée à MAX_ITERATIONS=5 itérations LLM. Chaque appel est loggé
    (tokens + coût) dans conversation_llm_calls.
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

        # Stocke la réponse assistant complète (content blocks) — round-trip JSON via add_message.
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

        # end_turn (ou tout autre stop_reason qui n'est pas tool_use) → on extrait le texte.
        text = "".join(b.text for b in response.content if b.type == "text")
        return text or "Action effectuée."

    return "Désolé, j'ai dépassé 5 itérations sans aboutir. Reformule."
