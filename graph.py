"""
Orchestrateur LangGraph — Julien OS
Tous les nœuds sont async. Utiliser graph.ainvoke() depuis le bot Telegram.
"""
import json
import logging
import sys

from anthropic import Anthropic
from langgraph.graph import END, StateGraph

sys.path.insert(0, "/root")
from julien_os.config import ANTHROPIC_API_KEY

from .memory.store import recuperer_contexte, sauvegarder
from .state import AgentState

logger = logging.getLogger(__name__)
client = Anthropic(api_key=ANTHROPIC_API_KEY)

with open("/root/config_agent.json") as f:
    CONFIG = json.load(f)

MOTS_POLITIQUES_DEFAUT = CONFIG.get("mots_politiques", [])
PROJETS_CONFIG = CONFIG.get("projets", {})

PROMPT_ORCHESTRATEUR = (
    "Tu es un orchestrateur qui analyse le message de Julien et decide quel agent appeler.\n\n"
    "Reponds UNIQUEMENT avec un de ces mots, rien d'autre :\n"
    "- CR : si le message contient une transcription de reunion\n"
    "- EMAIL : si Julien demande de rediger un email ou un suivi\n"
    "- SHEPHERD : si Julien decrit une situation de projet, un blocage, une decision\n"
    "- MEMOIRE : si Julien pose une question sur des echanges passes\n"
    "- PREP : si Julien prepare une reunion ou demande un contexte rapide\n"
    "- DIRECT : si c'est une question simple ou autre chose\n\n"
    "Un seul mot. Pas d'explication."
)

# ── Mots-clés pour déclenchement automatique des scanners ────────────────────

_MOTS_AIRBNB = [
    "airbnb", "message airbnb", "messages airbnb", "voyageur", "voyageurs",
    "locataire", "locataires", "message voyageur", "messages voyageur",
    "réservation airbnb", "reservation airbnb", "hôte airbnb",
    "hote airbnb", "inbox airbnb",
]

_MOTS_PROTON = [
    "mails", "emails", "nouveaux mails", "nouveaux emails",
    "derniers mails", "derniers emails", "dernier mail", "dernier email",
    "boîte mail", "boite mail", "proton mail", "protonmail",
    "nouveaux messages proton", "lire mes mails", "check mail",
]

_MOTS_NOTION_NOTE = [
    "note ça", "note ca", "notes ça", "notes ca",
    "ajoute dans notion", "mémorise ça dans notion", "memorise ca dans notion",
    "mémorise dans notion", "memorise dans notion",
    "ajoute ça dans notion", "ajoute ca dans notion",
    "sauvegarde dans notion", "enregistre dans notion",
    "crée une note", "cree une note", "créer une note",
    "met ça dans notion", "met ca dans notion",
]

_MOTS_NOTION_SEARCH = [
    "cherche dans notion", "recherche dans notion",
    "qu'est-ce que j'ai noté sur", "qu est ce que j ai note sur",
    "ce que j'ai noté sur", "ce que j ai note sur",
    "trouve dans notion", "retrouve dans notion",
    "qu'est-ce que j'ai écrit sur", "ce que j'ai écrit sur",
    "mes notes sur", "j'ai noté quoi sur",
]


# ── Nœuds async ──────────────────────────────────────────────────────────────

async def node_detect_projet(state: AgentState) -> AgentState:
    texte = state["message"].lower()
    for projet, mots_cles in PROJETS_CONFIG.items():
        if any(mot in texte for mot in mots_cles):
            return {**state, "projet": projet}
    return {**state, "projet": "general"}


async def node_orchestrate(state: AgentState) -> AgentState:
    msg = state["message"]
    msg_lower = msg.lower()

    # 1. Préfixes de forçage explicites
    for prefix, agent in [("CR_FORCE:", "CR"), ("EMAIL_FORCE:", "EMAIL"),
                           ("SHEPHERD_FORCE:", "SHEPHERD"), ("PREP_FORCE:", "PREP")]:
        if msg.startswith(prefix):
            return {**state, "agent": agent, "message": msg[len(prefix):].strip()}

    # 2. Détection automatique Airbnb — déclenche le scanner sans LLM
    if any(mot in msg_lower for mot in _MOTS_AIRBNB):
        logger.info("Orchestrateur: déclenchement automatique AIRBNB_SCAN")
        return {**state, "agent": "AIRBNB_SCAN"}

    # 3. Détection automatique Proton Mail — déclenche la lecture IMAP sans LLM
    if any(mot in msg_lower for mot in _MOTS_PROTON):
        logger.info("Orchestrateur: déclenchement automatique PROTON_MAILS")
        return {**state, "agent": "PROTON_MAILS"}

    # 4. Détection automatique Notion — recherche
    if any(mot in msg_lower for mot in _MOTS_NOTION_SEARCH):
        logger.info("Orchestrateur: déclenchement automatique NOTION_SEARCH")
        return {**state, "agent": "NOTION_SEARCH"}

    # 5. Détection automatique Notion — création de note
    if any(mot in msg_lower for mot in _MOTS_NOTION_NOTE):
        logger.info("Orchestrateur: déclenchement automatique NOTION_NOTE")
        return {**state, "agent": "NOTION_NOTE"}

    # 6. Routage Claude pour tout le reste
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=10,
        system=PROMPT_ORCHESTRATEUR,
        messages=[{"role": "user", "content": msg}]
    )
    agent = response.content[0].text.strip().upper()
    if agent not in {"CR", "EMAIL", "SHEPHERD", "MEMOIRE", "PREP", "DIRECT"}:
        agent = "DIRECT"
    return {**state, "agent": agent}


async def node_load_context(state: AgentState) -> AgentState:
    # Les scanners n'ont pas besoin de contexte
    if state.get("agent") in ("MEMOIRE", "PREP", "AIRBNB_SCAN", "PROTON_MAILS",
                               "NOTION_NOTE", "NOTION_SEARCH"):
        return state
    projet = state.get("projet", "general")
    if projet != "general":
        contexte = await recuperer_contexte(projet, limite=3)
        return {**state, "contexte": contexte}
    return {**state, "contexte": ""}


async def _run_airbnb_scan(state: AgentState) -> AgentState:
    """Scan Airbnb à la demande — messages non lus."""
    from julien_os.config import AIRBNB_EMAIL, AIRBNB_PASSWORD

    try:
        from .tools.airbnb_scraper import AirbnbClient
        client_ab = AirbnbClient(email=AIRBNB_EMAIL, password=AIRBNB_PASSWORD)
        messages = await client_ab.get_unread_messages(limit=5)
    except Exception as e:
        logger.error(f"AIRBNB_SCAN error: {e}")
        return {**state, "resultat": f"Erreur scan Airbnb : {e}", "alerte": False}

    if not messages:
        return {**state, "resultat": "Aucun message Airbnb non lu.", "alerte": False}

    lines = [f"Airbnb — {len(messages)} message(s) non lu(s) :\n"]
    for i, m in enumerate(messages, 1):
        lines.append(f"{i}. {m.get('guest', 'Voyageur')} — {m.get('date', '')}")
        preview = m.get("preview", "")
        if preview:
            lines.append(f"   {preview[:120]}")
        lines.append("")
    return {**state, "resultat": "\n".join(lines).strip(), "alerte": False}


async def _run_proton_mails(state: AgentState) -> AgentState:
    """Lecture IMAP Proton Bridge à la demande."""
    from julien_os.config import PROTONMAIL_BRIDGE_PASSWORD, PROTONMAIL_EMAIL

    try:
        from .tools.protonmail import ProtonMailClient
        client_pm = ProtonMailClient(email_addr=PROTONMAIL_EMAIL, bridge_password=PROTONMAIL_BRIDGE_PASSWORD)
        emails = await client_pm.get_latest_emails(5)
    except Exception as e:
        logger.error(f"PROTON_MAILS error: {e}")
        return {**state, "resultat": f"Erreur IMAP : {e}", "alerte": False}

    if not emails:
        return {**state, "resultat": "Boîte vide ou Bridge inaccessible.", "alerte": False}

    lines = ["5 derniers emails — Proton Mail\n"]
    for i, e in enumerate(emails, 1):
        mark = "•" if e.get("unread") else " "
        lines.append(f"{mark} {i}. {e['date']}")
        lines.append(f"   De : {e['from'][:60]}")
        lines.append(f"   Objet : {e['subject'][:80]}")
        lines.append("")
    lines.append("• = non lu")
    return {**state, "resultat": "\n".join(lines).strip(), "alerte": False}


async def _run_notion_note(state: AgentState) -> AgentState:
    """Crée une note dans BDD_Notes_Inbox."""
    msg = state["message"]
    projet = state.get("projet", "general")

    # Retire les déclencheurs du début du message pour garder juste le contenu
    _prefixes_a_retirer = [
        "note ça : ", "note ca : ", "note ça:", "note ca:",
        "note ça ", "note ca ", "notes ça ", "notes ca ",
        "ajoute dans notion : ", "ajoute dans notion: ", "ajoute dans notion ",
        "mémorise ça dans notion : ", "memorise ca dans notion : ",
        "mémorise dans notion : ", "memorise dans notion : ",
        "mémorise dans notion ", "memorise dans notion ",
        "sauvegarde dans notion : ", "enregistre dans notion : ",
        "crée une note : ", "cree une note : ", "créer une note : ",
        "met ça dans notion : ", "met ca dans notion : ",
    ]
    texte = msg
    msg_lower = msg.lower()
    for p in _prefixes_a_retirer:
        if msg_lower.startswith(p):
            texte = msg[len(p):].strip()
            break

    if not texte:
        return {**state, "resultat": "Aucun contenu à noter.", "alerte": False}

    try:
        from .tools.notion_tool import creer_note
        url = await creer_note(texte=texte, projet=projet)
        return {
            **state,
            "resultat": f"Note créée dans Notion.\n{url}",
            "alerte": False,
        }
    except ValueError as e:
        return {**state, "resultat": str(e), "alerte": False}
    except Exception as e:
        logger.error(f"NOTION_NOTE error: {e}")
        return {**state, "resultat": f"Erreur Notion : {e}", "alerte": False}


async def _run_notion_search(state: AgentState) -> AgentState:
    """Recherche dans le workspace Notion."""
    msg = state["message"]

    # Extrait le mot-clé de recherche
    _prefixes_recherche = [
        "cherche dans notion ", "recherche dans notion ",
        "trouve dans notion ", "retrouve dans notion ",
        "qu'est-ce que j'ai noté sur ", "ce que j'ai noté sur ",
        "qu est ce que j ai note sur ", "ce que j ai note sur ",
        "qu'est-ce que j'ai écrit sur ", "ce que j'ai écrit sur ",
        "mes notes sur ", "j'ai noté quoi sur ", "j ai note quoi sur ",
    ]
    mot_cle = msg
    msg_lower = msg.lower()
    for p in _prefixes_recherche:
        if msg_lower.startswith(p):
            mot_cle = msg[len(p):].strip().rstrip("?")
            break

    if not mot_cle or mot_cle.lower() == msg_lower:
        # Fallback : prend le message entier comme mot-clé
        mot_cle = msg.strip().rstrip("?")

    try:
        from .tools.notion_tool import chercher
        results = await chercher(mot_cle, limit=5)
    except ValueError as e:
        return {**state, "resultat": str(e), "alerte": False}
    except Exception as e:
        logger.error(f"NOTION_SEARCH error: {e}")
        return {**state, "resultat": f"Erreur Notion : {e}", "alerte": False}

    if not results:
        return {**state, "resultat": f"Aucun résultat pour « {mot_cle} » dans Notion.", "alerte": False}

    lines = [f"Notion — {len(results)} résultat(s) pour « {mot_cle} » :\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['last_edited']} — {r['url']}")
        lines.append("")
    return {**state, "resultat": "\n".join(lines).strip(), "alerte": False}


async def node_run_agent(state: AgentState) -> AgentState:
    agent_key = state.get("agent", "DIRECT")

    if agent_key == "AIRBNB_SCAN":
        return await _run_airbnb_scan(state)
    if agent_key == "PROTON_MAILS":
        return await _run_proton_mails(state)
    if agent_key == "NOTION_NOTE":
        return await _run_notion_note(state)
    if agent_key == "NOTION_SEARCH":
        return await _run_notion_search(state)

    import inspect

    from . import agents
    agent_map = {
        "CR": agents.cr,
        "EMAIL": agents.email,
        "SHEPHERD": agents.shepherd,
        "MEMOIRE": agents.memoire,
        "PREP": agents.prep,
        "DIRECT": agents.direct,
    }
    module = agent_map.get(agent_key, agents.direct)
    if inspect.iscoroutinefunction(module.run):
        return await module.run(state)
    return module.run(state)


async def node_save_memory(state: AgentState) -> AgentState:
    # Les scanners et outils Notion ne sauvegardent pas en mémoire interne
    if state.get("agent") in ("MEMOIRE", "AIRBNB_SCAN", "PROTON_MAILS",
                               "NOTION_NOTE", "NOTION_SEARCH"):
        return state
    if state.get("resultat"):
        await sauvegarder(
            state.get("agent", "DIRECT"),
            state["message"],
            state["resultat"],
            state.get("projet", "general")
        )

        # Sync automatique CR → Journal des réunions Notion (tableau de bord iA)
        if state.get("agent") == "CR":
            try:
                import datetime as _dt

                from .tools.notion_tool import ajouter_cr_ia

                date_str = _dt.date.today().strftime("%d %B %Y")
                resultat = state["resultat"]

                # Extrait le plan d'action s'il est présent
                plan = ""
                resume = resultat
                for marker in ("**PLAN D'ACTION**", "PLAN D'ACTION", "**Plan d'action**"):
                    if marker in resultat:
                        idx = resultat.index(marker)
                        resume = resultat[:idx].strip()
                        plan = resultat[idx + len(marker):].strip()
                        break

                await ajouter_cr_ia(date_str=date_str, resume=resume, plan_action=plan)
                logger.info("CR synchronisé dans le journal Notion.")
            except Exception as _e:
                logger.warning(f"Notion CR sync non-bloquant : {_e}")

    return state


async def node_check_alerts(state: AgentState) -> AgentState:
    # Les scanners et outils Notion ne déclenchent pas d'alertes politiques
    if state.get("agent") in ("AIRBNB_SCAN", "PROTON_MAILS",
                               "NOTION_NOTE", "NOTION_SEARCH"):
        return {**state, "_alertes": []}

    if not state.get("alerte"):
        return {**state, "_alertes": []}

    from .memory.store import recuperer_alertes_projet
    projet = state.get("projet", "general")
    texte_combined = (state["message"] + " " + (state.get("resultat") or "")).lower()
    alertes = []

    mots_custom = await recuperer_alertes_projet(projet)
    tous_les_mots = MOTS_POLITIQUES_DEFAUT + mots_custom

    mots_detectes = [m for m in tous_les_mots if m in texte_combined]
    if mots_detectes:
        alertes.append(
            f"SIGNAL POLITIQUE detecte dans le projet {projet} :\n"
            f"Mots cles : {', '.join(mots_detectes)}"
        )

    prompt_decision = (
        "Analyse ce texte et reponds UNIQUEMENT par OUI ou NON.\n\n"
        "Y a-t-il une absence claire de decision dans cet echange ?\n\n"
        f"Texte : {(state.get('resultat') or '')[:1500]}"
    )
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=5,
        messages=[{"role": "user", "content": prompt_decision}]
    )
    if "OUI" in response.content[0].text.upper():
        alertes.append(
            f"DECISION NON TRANCHEE dans le projet {projet} :\n"
            "Cet echange ne contient pas de decision claire."
        )

    return {**state, "_alertes": alertes}


# ── Construction du graphe ───────────────────────────────────────────────────

def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("detect_projet", node_detect_projet)
    builder.add_node("orchestrate", node_orchestrate)
    builder.add_node("load_context", node_load_context)
    builder.add_node("run_agent", node_run_agent)
    builder.add_node("save_memory", node_save_memory)
    builder.add_node("check_alerts", node_check_alerts)

    builder.set_entry_point("detect_projet")
    builder.add_edge("detect_projet", "orchestrate")
    builder.add_edge("orchestrate", "load_context")
    builder.add_edge("load_context", "run_agent")
    builder.add_edge("run_agent", "save_memory")
    builder.add_edge("save_memory", "check_alerts")
    builder.add_edge("check_alerts", END)

    return builder.compile()


graph = build_graph()


async def traiter(message: str) -> dict:
    state = AgentState(
        message=message,
        projet="general",
        agent=None,
        contexte=None,
        resultat=None,
        alerte=None,
    )
    result = await graph.ainvoke(state)
    return {
        "agent": result.get("agent"),
        "projet": result.get("projet"),
        "resultat": result.get("resultat"),
        "alertes": result.get("_alertes", []),
    }
