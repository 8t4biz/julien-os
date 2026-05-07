import sys

from anthropic import Anthropic

sys.path.insert(0, "/root")
from config import ANTHROPIC_API_KEY

from ..profil import PROFIL

client = Anthropic(api_key=ANTHROPIC_API_KEY)

PROMPT = (
    "Tu es un assistant specialise dans l'analyse de transcriptions de reunions Teams pour Julien, consultant PO chez iA Groupe financier.\n\n"
    "Quand tu recois une transcription, tu produis :\n\n"
    "**RESUME DE LA RENCONTRE**\n"
    "- Contexte et participants cles\n"
    "- Sujets abordes (3-5 points maximum)\n"
    "- Decisions prises\n\n"
    "**POINTS EN SUSPENS**\n"
    "- Questions non resolues\n"
    "- Tensions ou resistances notees\n"
    "- Elements politiques a surveiller\n\n"
    "**PLAN D'ACTION**\n"
    "- Actions concretes avec responsable identifie quand possible\n"
    "- Prochaines etapes pour Julien specifiquement\n\n"
    "Sois direct, concis. Aucune flatterie. Si la transcription est ambigue, note-le."
)


def run(state: dict) -> dict:
    contenu = state.get("contexte", "") + "\n\n" + state["message"] if state.get("contexte") else state["message"]
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        system=PROFIL + "\n\n" + PROMPT,
        messages=[{"role": "user", "content": contenu}]
    )
    return {**state, "resultat": response.content[0].text, "alerte": True}
