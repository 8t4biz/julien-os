"""
Agent hebdomadaire — Chantier 13
Synthèse automatique par projet, envoyée chaque lundi matin.
"""
import sys

from anthropic import Anthropic

sys.path.insert(0, "/root")
from julien_os.config import ANTHROPIC_API_KEY

from ..profil import PROFIL

client = Anthropic(api_key=ANTHROPIC_API_KEY)


async def generer_tableau_bord() -> str:
    """Génère la synthèse hebdomadaire de tous les projets actifs."""
    from ..memory.store import lister_projets, recuperer_contexte

    projets = await lister_projets()
    if not projets:
        return "Aucun projet en mémoire pour le tableau de bord."

    # Filtre les projets avec activité dans les 30 derniers jours
    from datetime import datetime, timedelta
    seuil = (datetime.now() - timedelta(days=30)).isoformat()
    projets_actifs = [(p, nb, d) for p, nb, d in projets if d >= seuil]

    if not projets_actifs:
        return "Aucun projet actif dans les 30 derniers jours."

    syntheses = []
    for projet, nb, derniere in projets_actifs:
        contexte = await recuperer_contexte(projet, limite=8)
        if not contexte:
            continue
        prompt = (
            f"Voici l'historique récent du projet {projet} :\n\n{contexte}\n\n"
            "En 3-4 lignes maximum :\n"
            "- Statut actuel\n"
            "- Dernière action notable\n"
            "- Point d'attention si pertinent\n\n"
            "Sois ultra-concis. Pas de titre, pas de flatterie."
        )
        response = client.messages.create(
            system=PROFIL,
            model="claude-opus-4-5",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        syntheses.append((projet, nb, derniere[:10], response.content[0].text))

    from datetime import date
    aujourdhui = date.today().strftime("%A %d %B %Y")

    msg = f"**Tableau de bord — {aujourdhui}**\n"
    msg += f"_{len(syntheses)} projet(s) actif(s)_\n\n"
    msg += "─" * 30 + "\n\n"

    for projet, nb, derniere, synthese in syntheses:
        msg += f"**{projet}** _(dernier échange : {derniere}, {nb} total)_\n"
        msg += synthese.strip() + "\n\n"

    msg += "─" * 30 + "\n"
    msg += "_Bonne semaine. Envoie /aide pour les commandes._"

    return msg
