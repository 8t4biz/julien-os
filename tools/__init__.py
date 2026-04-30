"""Dispatcher des tools async exposés au LLM conversationnel."""
from julien_os.tools.email_tools import EMAIL_TOOLS, EMAIL_HANDLERS

ALL_TOOLS = list(EMAIL_TOOLS)
ALL_HANDLERS = dict(EMAIL_HANDLERS)


async def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Appel d'outil par nom depuis un contexte async (handler Telegram).

    Tous les handlers sont `async def` → await direct sur le résultat.
    Retourne toujours une string (les exceptions sont aplaties en messages d'erreur).
    """
    handler = ALL_HANDLERS.get(tool_name)
    if not handler:
        return f"Erreur : outil inconnu '{tool_name}'."
    try:
        return await handler(**(tool_input or {}))
    except TypeError as e:
        return f"Erreur arguments {tool_name} : {e}"
    except Exception as e:
        return f"Erreur exécution {tool_name} : {e}"
