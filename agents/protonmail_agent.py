"""
Agent Proton Mail — analyse emails entrants, génère 2 réponses prêtes à envoyer.
1 seul appel LLM avec output JSON structuré — extraction fiable, zéro regex fragile.
Airbnb : prompt spécialisé avec contexte hôte réel (style, propriétés, politique avis).
"""
import json
import logging
import sys

from anthropic import Anthropic

sys.path.insert(0, "/root")
from config import ANTHROPIC_API_KEY

client = Anthropic(api_key=ANTHROPIC_API_KEY)
logger = logging.getLogger(__name__)

# ── Prompt générique ──────────────────────────────────────────────────────────

PROMPT_GENERAL = """\
Tu es l'assistant email de Julien Carcaly, consultant PO chez iA Groupe financier à Montréal.
Profil : {profil}

Analyse l'email ci-dessous et retourne UNIQUEMENT un JSON valide, sans markdown, sans explication.

Format strict :
{{
  "priorite": "PRIORITAIRE" | "NORMAL" | "IGNORER",
  "contexte": "Qui est cet expéditeur et quel est l'enjeu réel — 1-2 phrases max",
  "option_courte": "Email de réponse court prêt à envoyer — 2-3 phrases, français professionnel, signé Julien",
  "option_complete": "Email de réponse complet prêt à envoyer — 4-6 phrases, français professionnel, signé Julien"
}}

Règles de classification :
- IGNORER : newsletter, notification automatique sans action (ex: reçu paiement, rappels systèmes), spam, CC informatif
- PRIORITAIRE : délai serré, client direct, problème urgent, question nécessitant réponse rapide
- NORMAL : tout le reste nécessitant une réponse

Règles de rédaction :
- Les deux options sont des emails complets prêts à envoyer — jamais de placeholder [Nom]
- Utilise le prénom de l'expéditeur si disponible dans l'email
- Signe toujours "Julien"
- Langue : français professionnel sauf si l'email est en anglais (dans ce cas, répondre en anglais)
"""

# ── Prompt Airbnb spécialisé ──────────────────────────────────────────────────

PROMPT_AIRBNB = """\
Tu es l'assistant Airbnb de Julien Carcaly, hôte à Montréal.
Profil hôte : {profil_airbnb}

Analyse l'email Airbnb ci-dessous et retourne UNIQUEMENT un JSON valide, sans markdown, sans explication.

Format strict :
{{
  "priorite": "PRIORITAIRE" | "NORMAL" | "IGNORER",
  "contexte": "Type d'email Airbnb et action requise — 1-2 phrases max",
  "option_courte": "Message court prêt à envoyer au voyageur (ou action à effectuer) — 2-3 phrases",
  "option_complete": "Message complet prêt à envoyer au voyageur (ou action à effectuer) — 4-6 phrases"
}}

Classification Airbnb :
- PRIORITAIRE : demande d'avis (délai 14j), annulation voyageur, modification réservation, problème urgent voyageur, litige
- NORMAL : nouveau message voyageur, nouvelle réservation, question avant séjour
- IGNORER : paiement reçu, notification système sans action, rappel app Airbnb, "votre voyage approche" générique

Style de réponse de Julien avec ses voyageurs :
- Anglais par défaut ; français si le voyageur écrit en français
- Salutation : "Hello [Prénom]," ou "Hi [Prénom]," (anglais) / "Bonjour [Prénom]," (français)
- Ton : chaleureux, professionnel, direct — jamais froid ni excessivement formel
- Clôtures anglais : "Talk soon, Julien" (début séjour) | "Best, Julien" (mid-séjour) | "Thanks, Julien" (court)
- Clôtures français : "Cordialement, Julien" | "Bien à vous," | "Merci,"
- Vouvoiement systématique en français
- Phrase d'accroche fréquente : "I am not a native of Montreal but live there since 10 years ;)"
- Pas d'emojis sauf ":)" pour messages très courts

Pour les demandes d'avis (objet contient "commentaire" ou "review") :
- option_courte = texte d'avis court positif prêt à poster (2-3 lignes factuelles)
- option_complete = texte d'avis complet prêt à poster (4-5 lignes : communication, propreté, respect des règles)
- Les avis sont rédigés en français (plateforme fr.airbnb.ca)

Pour les messages voyageurs :
- Répondre dans la langue du voyageur
- Être proactif (anticiper les questions logistiques suivantes)
- Mentionner la propriété concernée si identifiable (Charlotte ou Parthenais)
"""


def _est_email_airbnb(email_data: dict) -> bool:
    """Détecte si l'email vient d'Airbnb (notification ou message relayé)."""
    expediteur = email_data.get("from", "").lower()
    sujet = email_data.get("subject", "").lower()
    corps = (email_data.get("body", "") + email_data.get("snippet", "")).lower()

    if "airbnb" in expediteur:
        return True
    # Certains emails Airbnb arrivent avec un expéditeur relayé
    if "airbnb" in sujet or "airbnb" in corps[:200]:
        return True
    return False


def _identifier_proprieté(email_data: dict) -> str:
    """Identifie quelle propriété est concernée si possible."""
    texte = (
        email_data.get("subject", "") + " " +
        email_data.get("body", "") + " " +
        email_data.get("snippet", "")
    ).lower()
    if "charlotte" in texte or "404" in texte:
        return "404-109 Charlotte (Montréal Centre)"
    if "parthenais" in texte or "406" in texte:
        return "406-1451 Parthenais"
    return ""


async def analyser_et_generer(email_data: dict) -> dict:
    """
    Analyse l'email et retourne un dict :
    { priorite, contexte, option_courte, option_complete }
    Un seul appel LLM. Prompt spécialisé pour les emails Airbnb.
    """
    from ..profil import PROFIL as profil_julien
    try:
        from ..profil import PROFIL_AIRBNB as profil_airbnb
    except ImportError:
        profil_airbnb = ""

    expediteur = email_data.get("from", email_data.get("sender", ""))
    sujet      = email_data.get("subject", "(sans sujet)")
    corps      = email_data.get("body", email_data.get("snippet", ""))[:3000]
    date       = email_data.get("date", "")

    contenu = (
        f"De : {expediteur}\n"
        f"Sujet : {sujet}\n"
        f"Date : {date}\n\n"
        f"Corps :\n{corps}"
    )

    is_airbnb = _est_email_airbnb(email_data)

    if is_airbnb and profil_airbnb:
        propriete = _identifier_proprieté(email_data)
        profil_ctx = profil_airbnb[:2000]
        if propriete:
            profil_ctx = f"Propriété concernée : {propriete}\n\n" + profil_ctx
        prompt = PROMPT_AIRBNB.replace("{profil_airbnb}", profil_ctx)
        logger.info(f"ProtonAgent: email Airbnb détecté — prompt spécialisé (propriété: {propriete or 'inconnue'})")
    else:
        prompt = PROMPT_GENERAL.replace("{profil}", profil_julien[:600])

    raw = ""
    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1500,
            system=prompt,
            messages=[{"role": "user", "content": contenu}]
        )
        raw = response.content[0].text.strip()
        # Strip markdown si le LLM en ajoute malgré l'instruction
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"ProtonAgent: JSON parse error: {e} — raw: {raw[:300]}")
    except Exception as e:
        logger.error(f"ProtonAgent: analyser_et_generer error: {e}")

    # Fallback
    return {
        "priorite": "NORMAL",
        "contexte": f"De : {expediteur} | Sujet : {sujet}",
        "option_courte": (
            "Bonjour,\n\nMerci pour votre message. Je reviens vers vous rapidement.\n\nJulien"
        ),
        "option_complete": (
            f"Bonjour,\n\nMerci pour votre message concernant \u00ab {sujet} \u00bb.\n\n"
            "Je prends note et vous réponds en détail dans les prochaines heures.\n\n"
            "Cordialement,\nJulien"
        ),
    }


# ── Fonctions publiques appelées par le watcher ───────────────────────────────

async def analyser_priorite(email_data: dict) -> str:
    """Compatibilité : retourne PRIORITAIRE | NORMAL | IGNORER."""
    result = await analyser_et_generer(email_data)
    return result.get("priorite", "NORMAL").upper()


async def generer_options(email_data: dict) -> tuple[str, list[str]]:
    """Retourne (contexte, [option_courte, option_complete, 'Ignorer'])."""
    result = await analyser_et_generer(email_data)
    contexte = result.get("contexte", "")
    options = [
        result.get("option_courte", "Option courte non disponible"),
        result.get("option_complete", "Option compl\u00e8te non disponible"),
        "Ignorer / Traiter plus tard",
    ]
    return contexte, options


def formater_alerte_telegram(email_data: dict, contexte: str, options: list[str]) -> str:
    """
    Formate l'alerte Telegram (parse_mode HTML).
    Toutes les données dynamiques sont escapées pour éviter les erreurs HTML.
    """
    import html as _html
    expediteur = _html.escape(email_data.get("from", email_data.get("sender", "?")))
    sujet      = _html.escape(email_data.get("subject", "?"))
    date       = _html.escape(email_data.get("date", ""))
    ctx        = _html.escape(contexte)
    opt        = [_html.escape(o) for o in options]
    sep        = "\u2500" * 32

    # Icône selon source
    is_airbnb = "airbnb" in expediteur.lower() or "airbnb" in sujet.lower()
    icone = "\U0001f3e0" if is_airbnb else "\U0001f4e7"
    label = "AIRBNB" if is_airbnb else "PROTON MAIL"

    # V1.0.3.1 \u2014 Bouton 2 = opt-in pour r\u00e9daction personnalis\u00e9e (mode custom).
    # Bouton 1 reste l'option courte pr\u00e9-r\u00e9dig\u00e9e par l'agent batch.
    # Le free-text en dehors de 1/2/3 part d\u00e9sormais vers l'agent conversationnel
    # (\u00ab r\u00e9ponds \u00e0 #N \u00bb, \u00ab ouvre #N \u00bb etc.).
    msg = (
        f"{icone} <b>{label}</b>\n"
        f"De : {expediteur}\n"
        f"Sujet : {sujet}\n"
        f"Re\u00e7u : {date}\n\n"
        f"<i>{ctx}</i>\n\n"
        f"{sep}\n"
        f"<b>1\ufe0f\u20e3 Option courte</b>\n"
        f"{opt[0]}\n\n"
        f"{sep}\n"
        f"<b>2\ufe0f\u20e3 R\u00e9ponse personnalis\u00e9e</b>\n"
        f"R\u00e9ponds <b>2</b> puis d\u00e9cris ton instruction au prochain message.\n\n"
        f"{sep}\n"
        f"<b>3\ufe0f\u20e3</b> {opt[2]}\n\n"
        f"R\u00e9ponds <b>1</b>, <b>2</b>, <b>3</b> ou demande \u00e0 l'agent (\u00ab r\u00e9ponds \u00e0 #N \u00bb, \u00ab ouvre #N \u00bb)."
    )
    return msg
