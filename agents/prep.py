import sys

from anthropic import Anthropic

sys.path.insert(0, "/root")
from julien_os.config import ANTHROPIC_API_KEY

from ..profil import PROFIL

client = Anthropic(api_key=ANTHROPIC_API_KEY)


async def run(state: dict) -> dict:
    from ..memory.store import recuperer_contexte
    sujet = state["message"]
    projet = state.get("projet", "general")
    contexte = await recuperer_contexte(projet, limite=10)
    if not contexte:
        contexte = "Aucun historique disponible."
    prompt_prep = (
        "Tu es l'assistant de preparation de reunions de Julien.\n\n"
        f"Historique :\n{contexte}\n\n"
        f"Sujet : {sujet}\n\n"
        "Produis :\n\n"
        "**CONTEXTE RAPIDE**\n"
        "- Ce qu'on sait (3-4 points max)\n"
        "- Derniers developpements\n"
        "- Points de tension\n\n"
        "**QUESTIONS A POSER**\n"
        "2-3 questions strategiques.\n\n"
        "Sois concis."
    )
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=800,
        system=PROFIL,
        messages=[{"role": "user", "content": prompt_prep}]
    )
    return {**state, "resultat": response.content[0].text, "alerte": False}
