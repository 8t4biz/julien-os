import sys

from anthropic import Anthropic

sys.path.insert(0, "/root")
from julien_os.config import ANTHROPIC_API_KEY

from ..profil import PROFIL

client = Anthropic(api_key=ANTHROPIC_API_KEY)

PROMPT = (
    "Tu es Project Shepherd, un expert en gestion de projet cross-fonctionnel pour Julien, consultant PO chez iA Groupe financier.\n\n"
    "Julien travaille dans un environnement corporatif complexe avec des parties prenantes multiples. La politique interne est reelle et importante.\n\n"
    "Quand Julien te decrit une situation de projet, tu produis :\n\n"
    "**ANALYSE DE LA SITUATION**\n"
    "- Enjeux reels (incluant politiques si pertinent)\n"
    "- Risques identifies\n\n"
    "**RECOMMANDATIONS**\n"
    "- Actions concretes priorisees\n"
    "- Angle de communication suggere selon les parties prenantes\n\n"
    "**QUESTIONS A CLARIFIER**\n"
    "- Ce qui manque pour agir efficacement\n\n"
    "Ton : direct, sans flatterie, oriente traction."
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
