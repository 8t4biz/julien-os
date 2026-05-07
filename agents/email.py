import sys

from anthropic import Anthropic

sys.path.insert(0, "/root")
from config import ANTHROPIC_API_KEY

from ..profil import PROFIL

client = Anthropic(api_key=ANTHROPIC_API_KEY)

PROMPT = (
    "Tu es un assistant qui redige des emails de suivi professionnels pour Julien, consultant PO chez iA Groupe financier.\n\n"
    "Structure :\n"
    "- Objet clair\n"
    "- Rappel des decisions prises\n"
    "- Plan d'action avec responsables\n"
    "- Prochaine etape\n\n"
    "Ton : professionnel, direct, en francais. Pas de flatterie."
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
