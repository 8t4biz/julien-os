"""
Agent consolidation — Chantier 10
Résumé consolidé de tout l'historique d'un projet sur 90 jours.
"""
from anthropic import Anthropic
import sys
sys.path.insert(0, "/root")
from config import ANTHROPIC_API_KEY
from ..profil import PROFIL

client = Anthropic(api_key=ANTHROPIC_API_KEY)


async def consolider(projet: str) -> str:
    from ..memory.store import recuperer_tout_historique

    entrees = await recuperer_tout_historique(projet, jours=90)
    if not entrees:
        return f"Aucun historique trouvé pour le projet **{projet}** sur les 90 derniers jours."

    # Construit un digest compact de tous les résumés
    digest = f"Projet : {projet} — {len(entrees)} échange(s) sur 90 jours\n\n"
    for e in entrees:
        date = e["date"][:10]
        type_agent = e["type_agent"]
        resume = e["resume"] or e["output"][:300]
        digest += f"[{date} — {type_agent}]\n{resume}\n\n"

    # Limite à ~12 000 caractères pour tenir dans le contexte Claude
    if len(digest) > 12000:
        digest = digest[:12000] + "\n...(tronqué)"

    prompt = (
        f"Tu es l'assistant de Julien. Voici l'historique complet du projet **{projet}** sur les 90 derniers jours.\n\n"
        f"{digest}\n\n"
        "Produis un résumé consolidé structuré :\n\n"
        "**SITUATION ACTUELLE**\n"
        "- État du projet en 3-5 points\n"
        "- Décisions clés prises\n"
        "- Tensions ou risques persistants\n\n"
        "**CHRONOLOGIE DES MOMENTS CLÉS**\n"
        "- Les 5-7 événements les plus importants avec date\n\n"
        "**PATTERNS OBSERVÉS**\n"
        "- Tendances récurrentes (blocages, acteurs, thèmes)\n\n"
        "**ACTIONS EN SUSPENS**\n"
        "- Ce qui n'a pas encore été résolu\n\n"
        "Ton : direct, factuel, sans flatterie."
    )

    response = client.messages.create(
        system=PROFIL,
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text
