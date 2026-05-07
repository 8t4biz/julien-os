import sys

from anthropic import Anthropic

sys.path.insert(0, "/root")
from config import ANTHROPIC_API_KEY

from ..profil import PROFIL

client = Anthropic(api_key=ANTHROPIC_API_KEY)

PROMPT = (
    "Tu es l'assistant personnel de Julien, consultant PO chez iA Groupe financier a Montreal.\n\n"
    "Tu as acces a la memoire persistante de vos echanges passes.\n\n"
    "Tu reponds de facon directe et concise. Pas de flatterie. Pas de remplissage.\n"
    "Ton : franc, utile, professionnel."
)


def run(state: dict) -> dict:
    contenu = state.get("contexte", "") + "\n\n" + state["message"] if state.get("contexte") else state["message"]
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        system=PROFIL + "\n\n" + PROMPT,
        messages=[{"role": "user", "content": contenu}]
    )
    return {**state, "resultat": response.content[0].text, "alerte": False}
