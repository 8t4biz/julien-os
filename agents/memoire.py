import sys

from anthropic import Anthropic

sys.path.insert(0, "/root")
from julien_os.config import ANTHROPIC_API_KEY

from ..profil import PROFIL

client = Anthropic(api_key=ANTHROPIC_API_KEY)


async def run(state: dict) -> dict:
    from ..memory.store import recuperer_contexte
    projet = state.get("projet", "general")
    contexte = await recuperer_contexte(projet, limite=10)
    if not contexte:
        return {**state, "resultat": f"Aucun historique trouve pour le projet {projet}.", "alerte": False}
    prompt_memoire = (
        f"Tu es l'assistant memoire de Julien. Voici l'historique de ses echanges recents pour le projet {projet} :\n\n"
        f"{contexte}\n\n"
        "Reponds a sa question de facon directe et concise en te basant sur cet historique."
    )
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        system=PROFIL + "\n\n" + prompt_memoire,
        messages=[{"role": "user", "content": state["message"]}]
    )
    return {**state, "resultat": response.content[0].text, "alerte": False}
