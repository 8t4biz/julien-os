"""
Agent Airbnb — analyse les messages voyageurs et génère 3 options de réponse.
"""
from anthropic import Anthropic
import sys
sys.path.insert(0, "/root")
from config import ANTHROPIC_API_KEY

client = Anthropic(api_key=ANTHROPIC_API_KEY)

PROMPT_ANALYSE = """
Tu es l'assistant Airbnb de Julien, propriétaire d'un logement locatif au Québec.
Julien veut des réponses professionnelles, chaleureuses mais concises, en français.

Analyse ce message d'un voyageur et produis :

**CONTEXTE**
- Demande ou situation principale
- Urgence ou point d'attention

**RÉPONSE SUGGÉRÉE — 3 OPTIONS**
Option 1 (courte et directe — 2-3 phrases) :
[texte prêt à envoyer au voyageur]

Option 2 (complète et détaillée — 4-6 phrases) :
[texte prêt à envoyer au voyageur]

Option 3 : Ignorer / Répondre plus tard

Ton : chaleureux, professionnel, en français québécois.
"""

PROMPT_PRIORITE = """
Tu analyses un message Airbnb. Réponds UNIQUEMENT par PRIORITAIRE ou NORMAL.

PRIORITAIRE = problème dans le logement, question avant arrivée dans les 48h, annulation potentielle, incident
NORMAL = question générale, après séjour, demande sans urgence

Un seul mot.
"""


async def analyser_priorite(msg_data: dict) -> str:
    contenu = f"Voyageur: {msg_data.get('guest', '')}\nMessage: {msg_data.get('preview', '')}"
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=10,
        system=PROMPT_PRIORITE,
        messages=[{"role": "user", "content": contenu}]
    )
    return response.content[0].text.strip().upper()


async def generer_options(msg_data: dict) -> tuple[str, list[str]]:
    contenu = (
        f"Voyageur : {msg_data.get('guest', '')}\n"
        f"Date : {msg_data.get('date', '')}\n\n"
        f"Message :\n{msg_data.get('conversation', msg_data.get('preview', ''))[:3000]}"
    )
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1200,
        system=PROMPT_ANALYSE,
        messages=[{"role": "user", "content": contenu}]
    )
    analyse = response.content[0].text
    options = _extraire_options(analyse)
    return analyse, options


def _extraire_options(texte: str) -> list[str]:
    import re
    options = []
    for i in [1, 2]:
        pattern = rf"Option {i}[^:]*:\s*\n(.*?)(?=Option {i+1}|$)"
        match = re.search(pattern, texte, re.DOTALL | re.IGNORECASE)
        if match:
            options.append(match.group(1).strip())
        else:
            options.append(f"Option {i} — voir analyse ci-dessus")
    options.append("Ignorer / Répondre plus tard")
    return options


def formater_alerte_telegram(msg_data: dict, analyse: str, options: list[str]) -> str:
    msg = (
        f"🏠 **AIRBNB**\n"
        f"De : {msg_data.get('guest', '?')}\n"
        f"Date : {msg_data.get('date', '?')}\n\n"
        f"_{msg_data.get('preview', '')[:200]}_\n\n"
        f"**Options :**\n"
        f"1️⃣ {options[0][:150]}...\n\n"
        f"2️⃣ {options[1][:150]}...\n\n"
        f"3️⃣ {options[2]}\n\n"
        f"Réponds avec **1**, **2**, **3** ou rédige ta propre instruction."
    )
    return msg
