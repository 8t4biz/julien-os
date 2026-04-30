"""
Julien OS — Bot Telegram
Interface principale — délègue tout traitement au graphe LangGraph.
Intègre le système de validation OUI/NON pour les actions Proton Mail et Airbnb.
"""
import os
import asyncio
import logging
from datetime import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import sys
sys.path.insert(0, "/root")
from config import TELEGRAM_TOKEN

from .graph import traiter
from .memory.store import (
    init_db, recuperer_contexte, lister_projets, normaliser_projet,
    ajouter_alerte, supprimer_alerte, lister_alertes,
    sauvegarder_chat_id, recuperer_chat_id,
)
from .memory.pending import (
    init_pending_table, get_pending_actif,
    confirmer_pending, marquer_envoye, ignorer_pending,
    get_tous_pending_actifs, get_pending_a_rappeler, marquer_rappel_envoye,
    get_pending_confirme_orphelin,
)
from .tools.transcription import transcrire_audio
from .agents.consolidation import consolider
from .agents.hebdo import generer_tableau_bord
from .telegram_format import envoyer_html

# V1 Niveau 2 — agent conversationnel pour le texte libre
from .agents.conversational import handle_conversation
from .memory.conversation import ConversationSession

logging.basicConfig(level=logging.WARNING)
logging.getLogger('julien_os').setLevel(logging.INFO)
logger = logging.getLogger(__name__)

ETIQUETTES = {
    "CR": "Compte-rendu",
    "EMAIL": "Email de suivi",
    "SHEPHERD": "Analyse Shepherd",
    "PREP": "Preparation de reunion",
    "MEMOIRE": "Memoire",
    "DIRECT": "",
}

# État de confirmation en cours (pending_id → texte final)
_en_attente_confirmation: dict[int, dict] = {}  # chat_id → {pending_id, texte, source}

# Sessions de login interactif en cours
_login_sessions: dict[int, asyncio.Queue] = {}  # chat_id → queue


async def envoyer_resultat(update: Update, result: dict):
    agent = result.get("agent", "DIRECT")
    projet = result.get("projet", "general")
    resultat = result.get("resultat", "")
    alertes = result.get("alertes", [])

    etiquette = ETIQUETTES.get(agent, "")
    prefix = f"<b>[{etiquette} — {projet}]</b>\n\n" if etiquette else ""

    chunks = envoyer_html(prefix + resultat)
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode="HTML")

    for alerte in alertes:
        chunks_a = envoyer_html(f"⚠️ <b>ALERTE</b>\n\n{alerte}")
        for chunk in chunks_a:
            await update.message.reply_text(chunk, parse_mode="HTML")


# ── Handler OUI/NON — intercept avant le graphe ──────────────────────────────

async def handle_validation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Intercepte les réponses de validation pour les pending actions.
    Retourne True si le message a été traité, False sinon.
    """
    chat_id = update.effective_chat.id
    texte = update.message.text.strip()

    # Étape 2 : confirmation finale OUI/NON après présentation du texte
    if chat_id in _en_attente_confirmation:
        state = _en_attente_confirmation[chat_id]
        if texte.upper() in ("OUI", "YES", "O", "Y", "✅"):
            await update.message.reply_text("Envoi en cours...")
            ok = await _executer_action(state, bot=context.bot, chat_id=chat_id)
            if ok:
                await marquer_envoye(state["pending_id"])
                await update.message.reply_text("✅ Envoyé.")
            else:
                await update.message.reply_text("❌ Échec de l'envoi. Vérifie les logs.")
            del _en_attente_confirmation[chat_id]
            return True
        elif texte.upper() in ("NON", "NO", "N", "ANNULER", "CANCEL"):
            del _en_attente_confirmation[chat_id]
            await ignorer_pending(state["pending_id"])
            await update.message.reply_text("Action annulée.")
            return True
        else:
            await update.message.reply_text(
                f"Confirme avec OUI pour envoyer, ou NON pour annuler.\n\n_{state['texte'][:300]}_"
            )
            return True

    # Étape 1 : choix parmi les options (1, 2, 3 ou texte libre)
    pending = await get_pending_actif()
    if not pending:
        return False

    options = pending["options"]
    pending_id = pending["id"]
    source = pending["source"]
    item_data = pending["item_data"]

    texte_choisi = None

    if texte in ("1", "2"):
        idx = int(texte) - 1
        texte_choisi = options[idx] if idx < len(options) else None
    elif texte == "3":
        await ignorer_pending(pending_id)
        # V1.0.2 Hook B — pour les pendings Proton, déplacer vers "À reprendre"
        if source == "protonmail" and item_data.get("uid"):
            try:
                from .tools import imap_actions
                src_folder = item_data.get("folder") or "INBOX"
                await imap_actions.mark_and_move(
                    item_data["uid"], src_folder, imap_actions.FOLDER_REPRENDRE
                )
            except Exception as e:
                logger.error("[IMAP_ACTION_FAIL] hook B: " + str(e))
        await update.message.reply_text("Message ignoré.")
        return True
    elif len(texte) > 10:
        # Texte libre → génération d'une réponse custom
        await update.message.reply_text("Rédaction en cours...")
        texte_choisi = await _generer_reponse_custom(texte, item_data, source)
    else:
        return False  # pas une réponse à un pending

    if not texte_choisi:
        return False

    await confirmer_pending(pending_id, texte_choisi)

    # Présente le texte final pour confirmation
    _en_attente_confirmation[chat_id] = {
        "pending_id": pending_id,
        "source": source,
        "item_data": item_data,
        "texte": texte_choisi,
    }

    await update.message.reply_text(
        f"Voici ce que je vais envoyer :\n\n{texte_choisi}\n\n"
        "Réponds **OUI** pour envoyer, **NON** pour annuler.",
        parse_mode="HTML"
    )
    return True


async def _generer_reponse_custom(instruction: str, item_data: dict, source: str) -> str:
    """Génère une réponse custom à partir de l'instruction de Julien."""
    from anthropic import Anthropic
    from config import ANTHROPIC_API_KEY
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    contexte = (
        f"Source : {source}\n"
        f"Item : {str(item_data)[:500]}\n\n"
        f"Instruction de Julien : {instruction}"
    )
    if source == "protonmail":
        system = "Tu rédiges un email de réponse professionnel pour Julien selon son instruction. Retourne uniquement le corps de l'email, prêt à envoyer."
    else:
        system = "Tu rédiges un message Airbnb pour Julien selon son instruction. Ton chaleureux, concis, en français. Retourne uniquement le message, prêt à envoyer."

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": contexte}]
    )
    return response.content[0].text.strip()


async def _executer_action(state: dict, bot=None, chat_id: int = None) -> bool:
    """
    Exécute l'action selon la source :
    - protonmail + email normal → SMTP via Proton Bridge
    - protonmail + email Airbnb → pas de SMTP (no-reply), affiche texte + lien
    - airbnb → envoi message via Playwright
    """
    import json as _json
    source = state["source"]
    item_data = state["item_data"]
    texte = state["texte"]

    if source == "protonmail":
        expediteur = item_data.get("from", "").lower()
        sujet = item_data.get("subject", "").lower()

        # Bloquer SMTP pour toute adresse no-reply (Airbnb, notifications, factures auto, etc.)
        NOREPLY_PATTERNS = ("noreply", "no-reply", "automated", "do-not-reply", "donotreply", "do_not_reply")
        est_noreply = any(p in expediteur for p in NOREPLY_PATTERNS)

        if est_noreply:
            expediteur_affiche = item_data.get("from", "?")
            est_demande_avis = (
                "airbnb" in expediteur
                and any(mot in sujet for mot in ("commentaire", "review", "avis", "laisser"))
            )
            if bot and chat_id:
                if est_demande_avis:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "\u26d4 Adresse no-reply \u2014 envoi SMTP bloqu\u00e9.\n\n"
                            "Texte d\u2019avis pr\u00eat \u00e0 poster :\nhttps://www.airbnb.ca/hosting/reviews"
                        ),
                    )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "\u26d4 Envoi bloqu\u00e9 : " + expediteur_affiche + "\n\n"
                            "Cette adresse ne peut pas recevoir de r\u00e9ponse (no-reply).\n"
                            "Le texte pr\u00e9par\u00e9 est conserv\u00e9 mais n\u2019a pas \u00e9t\u00e9 envoy\u00e9."
                        ),
                    )
            logger.info("_executer_action: SMTP bloqu\u00e9 \u2014 adresse no-reply: " + expediteur)
            return True

        # Email normal → SMTP Proton Bridge
        try:
            with open("/root/secrets.json") as f:
                secrets = _json.load(f)
            creds = secrets.get("protonmail", {})
        except Exception:
            logger.error("_executer_action: impossible de lire secrets.json")
            return False

        from .tools.protonmail import ProtonMailClient
        client = ProtonMailClient(
            email_addr=creds["email"],
            bridge_password=creds.get("bridge_password", ""),
        )
        folder = item_data.get("folder") or "INBOX"
        ok = await client.reply_to_email(
            email_id=item_data["id"],
            reply_text=texte,
            uid=item_data.get("uid", ""),
            folder=folder,
        )
        logger.info(
            "_executer_action: SMTP reply "
            + ("OK" if ok else "ECHEC")
            + " folder=" + folder
            + " uid=" + str(item_data.get("uid", "?"))
        )
        # V1.0.2 Hook A — déplacement vers "Traité par agent" après envoi SMTP réussi
        if ok and item_data.get("uid"):
            try:
                from .tools import imap_actions
                await imap_actions.mark_and_move(
                    item_data["uid"], folder, imap_actions.FOLDER_TRAITE
                )
            except Exception as e:
                logger.error("[IMAP_ACTION_FAIL] hook A: " + str(e))
        return ok

    elif source == "airbnb":
        try:
            with open("/root/secrets.json") as f:
                secrets = _json.load(f)
            creds = secrets.get("airbnb", {})
        except Exception:
            return False
        from .tools.airbnb_scraper import AirbnbClient
        client = AirbnbClient(email=creds["email"], password=creds["password"])
        await client.login()
        return await client.send_message(item_data.get("href", ""), texte)

    return False





# ── Handlers messages ────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await sauvegarder_chat_id(update.effective_chat.id)
    chat_id = update.effective_chat.id
    if chat_id in _login_sessions:
        await _login_sessions[chat_id].put(update.message.text.strip())
        return
    if await handle_validation(update, context):
        return

    # V1 Niveau 2 — texte libre routé vers l'agent conversationnel.
    # /reset force une nouvelle session ; les CommandHandler slash sont déjà gérés en amont.
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        pass  # action typing best-effort, on n'échoue pas le tour pour ça
    try:
        response = await handle_conversation(str(chat_id), update.message.text)
    except Exception as e:
        logger.error("handle_conversation a échoué : %s", e, exc_info=True)
        response = f"Erreur agent : {e}. Tu peux essayer /reset si ça persiste."
    if not response:
        response = "(réponse vide)"
    # Découpe à 4000 chars — même mécanique que les autres handlers (cmd_pending, etc.).
    for i in range(0, len(response), 4000):
        await update.message.reply_text(response[i:i + 4000])


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await sauvegarder_chat_id(update.effective_chat.id)
    await update.message.reply_text("Message vocal recu, transcription en cours...")
    fichier = await update.message.voice.get_file()
    chemin = "/tmp/voice_message.ogg"
    await fichier.download_to_drive(chemin)
    texte = await transcrire_audio(chemin)
    os.remove(chemin)
    # On garde la confirmation de transcription — utile pour valider Whisper côté Julien.
    await update.message.reply_text(f"Transcrit : {texte}")

    # V1 Niveau 2 — le vocal passe par le même agent conversationnel que le texte.
    chat_id = update.effective_chat.id
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        pass  # action typing best-effort
    try:
        response = await handle_conversation(str(chat_id), texte)
    except Exception as e:
        logger.error("handle_conversation (vocal) a échoué : %s", e, exc_info=True)
        response = f"Erreur agent : {e}. Tu peux essayer /reset si ça persiste."
    if not response:
        response = "(réponse vide)"
    for i in range(0, len(response), 4000):
        await update.message.reply_text(response[i:i + 4000])


# ── Commandes de base ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await sauvegarder_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "Julien OS — Agent actif (LangGraph)\n\n"
        "Envoie du texte ou un message vocal.\n\n"
        "/cr /email /shepherd /prep — Agents\n"
        "/consolider [projet] — Résumé 90 jours\n"
        "/stats [projet] — Statistiques\n"
        "/memoire [projet] — Historique\n"
        "/projets — Projets\n"
        "/alerte — Gestion alertes\n"
        "/surveillance — Statut Proton + Airbnb\n"
        "/aide — Aide complète"
    )


async def cmd_aide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/cr /email /shepherd /prep — Agents\n"
        "/consolider [projet] — Résumé 90 jours\n"
        "/stats [projet] — Stats\n"
        "/memoire [projet] — Historique\n"
        "/projets — Projets en mémoire\n"
        "/alerte add|del|list [projet] [mot] — Alertes custom\n"
        "/surveillance — Statut watchers\n"
        "/forcer_proton — Scan Proton Mail maintenant\n"
        "/forcer_airbnb — Scan Airbnb maintenant"
    )


async def cmd_projets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await lister_projets()
    if not rows:
        await update.message.reply_text("Aucun projet en memoire.")
        return
    msg = "Projets en memoire :\n\n"
    for projet, nb, derniere in rows:
        msg += f"- {projet} : {nb} echange(s), dernier : {derniere[:10]}\n"
    await update.message.reply_text(msg)


async def cmd_memoire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    projet_raw = " ".join(context.args) if context.args else "general"
    projet = normaliser_projet(projet_raw)
    await update.message.reply_text(f"Recuperation de l'historique pour {projet}...")
    contexte = await recuperer_contexte(projet, limite=10)
    if not contexte:
        await update.message.reply_text(f"Aucun historique pour {projet}.")
        return
    await update.message.reply_text(contexte[:4000])


async def cmd_cr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = " ".join(context.args)
    if not texte:
        await update.message.reply_text("Envoie la transcription apres /cr")
        return
    await update.message.reply_text("Analyse en cours...")
    result = await traiter("CR_FORCE: " + texte)
    result["agent"] = "CR"
    await envoyer_resultat(update, result)


async def cmd_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = " ".join(context.args)
    if not texte:
        await update.message.reply_text("Envoie le contenu apres /email")
        return
    await update.message.reply_text("Redaction en cours...")
    result = await traiter("EMAIL_FORCE: " + texte)
    result["agent"] = "EMAIL"
    await envoyer_resultat(update, result)


async def cmd_shepherd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = " ".join(context.args)
    if not texte:
        await update.message.reply_text("Decris la situation apres /shepherd")
        return
    await update.message.reply_text("Analyse en cours...")
    result = await traiter("SHEPHERD_FORCE: " + texte)
    result["agent"] = "SHEPHERD"
    await envoyer_resultat(update, result)


async def cmd_prep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sujet = " ".join(context.args)
    if not sujet:
        await update.message.reply_text("Indique un nom ou sujet apres /prep")
        return
    await update.message.reply_text(f"Preparation pour {sujet}...")
    result = await traiter("PREP_FORCE: " + sujet)
    result["agent"] = "PREP"
    await envoyer_resultat(update, result)


async def cmd_consolider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    projet_raw = " ".join(context.args) if context.args else ""
    if not projet_raw:
        await update.message.reply_text("Indique un projet.\nEx: /consolider iA")
        return
    projet = normaliser_projet(projet_raw)
    await update.message.reply_text(f"Consolidation {projet} sur 90 jours...")
    resultat = await consolider(projet)
    await update.message.reply_text(f"[Consolidation — {projet}]\n\n{resultat}"[:4096])


async def cmd_alerte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "/alerte add [projet] [mot] — Ajouter\n"
            "/alerte del [projet] [mot] — Supprimer\n"
            "/alerte list [projet] — Lister"
        )
        return
    action = args[0].lower()
    if action == "list":
        projet = normaliser_projet(" ".join(args[1:]) if len(args) > 1 else "general")
        mots = await lister_alertes(projet)
        await update.message.reply_text(
            f"Alertes — {projet} :\n" + ("\n".join(f"• {m}" for m in mots) if mots else "(aucune)")
        )
    elif action == "add":
        if len(args) < 3:
            await update.message.reply_text("Usage : /alerte add [projet] [mot]")
            return
        projet = normaliser_projet(args[1])
        mot = " ".join(args[2:])
        ok = await ajouter_alerte(projet, mot)
        await update.message.reply_text(f"{'Ajouté' if ok else 'Déjà existant'} : {mot} → {projet}")
    elif action == "del":
        if len(args) < 3:
            await update.message.reply_text("Usage : /alerte del [projet] [mot]")
            return
        projet = normaliser_projet(args[1])
        mot = " ".join(args[2:])
        ok = await supprimer_alerte(projet, mot)
        await update.message.reply_text(f"{'Supprimé' if ok else 'Introuvable'} : {mot} → {projet}")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .memory.store import recuperer_tout_historique
    from datetime import datetime, timedelta
    from collections import Counter
    projet_raw = " ".join(context.args) if context.args else ""
    if not projet_raw:
        rows = await lister_projets()
        if not rows:
            await update.message.reply_text("Aucun projet.")
            return
        msg = "**Statistiques**\n\n"
        for projet, nb, derniere in rows:
            msg += f"**{projet}** : {nb} échange(s), dernier : {derniere[:10]}\n"
        await update.message.reply_text(msg)
        return
    projet = normaliser_projet(projet_raw)
    entrees = await recuperer_tout_historique(projet, jours=90)
    if not entrees:
        await update.message.reply_text(f"Aucun historique pour {projet}.")
        return
    dates = [e["date"][:10] for e in entrees]
    types = {}
    for e in entrees:
        types[e["type_agent"]] = types.get(e["type_agent"], 0) + 1
    semaines = Counter()
    for e in entrees:
        d = datetime.fromisoformat(e["date"])
        semaines[d.strftime("%Y-W%W")] += 1
    msg = f"**Stats — {projet}** (90 jours)\nTotal : {len(entrees)} | Premier : {dates[0]} | Dernier : {dates[-1]}\n\n"
    for t, n in sorted(types.items(), key=lambda x: -x[1]):
        msg += f"• {t} : {n}\n"
    msg += "\n**Activité hebdo :**\n"
    for s, n in sorted(semaines.items())[-5:]:
        msg += f"• {s} : {n}\n"
    await update.message.reply_text(msg)


# ── Commandes surveillance ────────────────────────────────────────────────────


async def cmd_login_proton(update, context):
    """Login interactif Proton Mail via Telegram (gere le 2FA pas-a-pas)."""
    chat_id = update.effective_chat.id
    if chat_id in _login_sessions:
        await update.message.reply_text("Un login est deja en cours. Reponds aux questions ou tape ANNULER.")
        return
    import json as _j
    try:
        creds = _j.load(open("/root/secrets.json")).get("protonmail", {})
        assert creds.get("email") and creds.get("password")
    except Exception:
        await update.message.reply_text("Credentials manquants dans /root/secrets.json")
        return

    await update.message.reply_text(
        "Connexion Proton Mail en cours...\n"
        "Je te demande le code 2FA si necessaire.\n"
        "Entre ANNULER pour stopper."
    )
    q = asyncio.Queue()
    _login_sessions[chat_id] = q

    async def input_fn(prompt):
        await context.bot.send_message(chat_id=chat_id, text=prompt)
        try:
            rep = await asyncio.wait_for(q.get(), timeout=180)
            if rep.strip().upper() == "ANNULER":
                raise asyncio.CancelledError()
            return rep.strip()
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError("Delai de 3 min depasse — login annule")

    async def status_fn(msg, screenshot=None):
        await context.bot.send_message(chat_id=chat_id, text=msg)
        if screenshot:
            from io import BytesIO
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=BytesIO(screenshot))
            except Exception:
                pass

    async def _run():
        try:
            from .tools.protonmail import ProtonMailClient
            c = ProtonMailClient(
                email_addr=creds["email"],
                bridge_password=creds.get("bridge_password", ""),
            )
            ok = await c.interactive_login(input_fn=input_fn, status_fn=status_fn)
            await context.bot.send_message(
                chat_id=chat_id,
                text="Connexion reussie. Lance /forcer_proton pour tester." if ok
                     else "Connexion echouee. Verifie les credentials et relance /login_proton."
            )
        except asyncio.CancelledError:
            await context.bot.send_message(chat_id=chat_id, text="Login annule.")
        except asyncio.TimeoutError as e:
            await context.bot.send_message(chat_id=chat_id, text=str(e))
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id, text=f"Erreur login : {e}")
        finally:
            _login_sessions.pop(chat_id, None)

    asyncio.create_task(_run())



async def cmd_login_airbnb(update, context):
    chat_id = update.effective_chat.id
    if chat_id in _login_sessions:
        await update.message.reply_text("Un login est deja en cours. Reponds ou tape ANNULER.")
        return
    import json as _j
    try:
        creds = _j.load(open("/root/secrets.json")).get("airbnb", {})
        assert creds.get("email") and creds.get("password")
    except Exception:
        await update.message.reply_text("Credentials Airbnb manquants dans /root/secrets.json")
        return
    await update.message.reply_text(
        "Connexion Airbnb en cours...\n"
        "Si Airbnb envoie un code par email, entre-le ici.\n"
        "Tape ANNULER pour stopper."
    )
    q = asyncio.Queue()
    _login_sessions[chat_id] = q

    async def input_fn(prompt):
        await context.bot.send_message(chat_id=chat_id, text=prompt)
        try:
            rep = await asyncio.wait_for(q.get(), timeout=180)
            if rep.strip().upper() == "ANNULER":
                raise asyncio.CancelledError()
            return rep.strip()
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError("Delai de 3 min depasse")

    async def status_fn(msg, screenshot=None):
        await context.bot.send_message(chat_id=chat_id, text=msg)
        if screenshot:
            from io import BytesIO
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=BytesIO(screenshot))
            except Exception:
                pass

    async def _run():
        try:
            from .tools.airbnb_scraper import AirbnbClient
            c = AirbnbClient(email=creds["email"], password=creds["password"])
            ok = await c.interactive_login(input_fn=input_fn, status_fn=status_fn)
            await context.bot.send_message(
                chat_id=chat_id,
                text="Connexion reussie. Lance /forcer_airbnb pour tester." if ok
                     else "Connexion echouee. Relance /login_airbnb."
            )
        except asyncio.CancelledError:
            await context.bot.send_message(chat_id=chat_id, text="Login annule.")
        except asyncio.TimeoutError as e:
            await context.bot.send_message(chat_id=chat_id, text=str(e))
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id, text=f"Erreur login Airbnb : {e}")
        finally:
            _login_sessions.pop(chat_id, None)

    asyncio.create_task(_run())



async def cmd_mails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les 5 derniers emails Proton Mail via IMAP Bridge."""
    import json as _json
    try:
        with open("/root/secrets.json") as f:
            s = _json.load(f)
        pm = s.get("protonmail", {})
        bridge_password = pm.get("bridge_password", "")
        if not bridge_password:
            await update.message.reply_text(
                "Bridge Proton Mail non configuré.\nLance: python3 /root/bridge_setup.py sur le VPS."
            )
            return
    except Exception:
        await update.message.reply_text("Erreur lecture secrets.json")
        return

    await update.message.reply_text("Lecture IMAP en cours...")
    try:
        from .tools.protonmail import ProtonMailClient
        client = ProtonMailClient(email_addr=pm["email"], bridge_password=bridge_password)
        emails = await client.get_latest_emails(5)
    except Exception as e:
        await update.message.reply_text(f"Erreur IMAP : {e}")
        return

    if not emails:
        await update.message.reply_text("Boîte vide ou Bridge inaccessible.")
        return

    lines = ["5 derniers emails — Proton Mail", ""]
    for i, e in enumerate(emails, 1):
        unread_mark = "• " if e.get("unread") else "  "
        lines.append(f"{unread_mark}{i}. {e['date']}")
        lines.append(f"   De : {e['from'][:60]}")
        lines.append(f"   Objet : {e['subject'][:80]}")
        lines.append("")

    lines.append("(• = non lu)")
    await update.message.reply_text("\n".join(lines))


async def cmd_noter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Crée une note dans BDD_Notes_Inbox Notion. Usage : /noter [texte]"""
    import json as _json
    try:
        with open("/root/secrets.json") as f:
            s = _json.load(f)
        if not s.get("notion_token"):
            await update.message.reply_text(
                "notion_token manquant dans /root/secrets.json.\n"
                "Ajoute-le manuellement : nano /root/secrets.json"
            )
            return
    except Exception:
        await update.message.reply_text("Erreur lecture secrets.json")
        return

    texte = " ".join(context.args) if context.args else ""
    if not texte:
        await update.message.reply_text("Usage : /noter [texte de la note]")
        return

    await update.message.reply_text("Création de la note...")
    try:
        from .tools.notion_tool import creer_note
        url = await creer_note(texte=texte)
        await update.message.reply_text(f"Note créée.\n{url}")
    except Exception as e:
        await update.message.reply_text(f"Erreur Notion : {e}")


async def cmd_surveillance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import json
    try:
        with open("/root/secrets.json") as f:
            secrets = json.load(f)
        pm = secrets.get("protonmail", {})
        ab = secrets.get("airbnb", {})
        proton_ok = bool(pm.get("email") and pm.get("password"))
        airbnb_ok = bool(ab.get("email") and ab.get("password"))
    except Exception:
        proton_ok = airbnb_ok = False

    msg = (
        "Statut de la surveillance\n\n"
        f"\U0001f4e7 Proton Mail : {'\u2705 configuré' if proton_ok else '\u274c credentials manquants'}\n"
        "   Watcher : ✅ actif — 11h45 et 17h EDT\n\n"
        f"\U0001f3e0 Airbnb : {'\u2705 configuré' if airbnb_ok else '\u274c credentials manquants'}\n"
        "   Watcher : ✅ actif — 11h45 et 17h EDT\n\n"
        "Commandes manuelles :\n"
        "/forcer_proton — scan Proton maintenant\n"
        "/forcer_airbnb — scan Airbnb maintenant\n"
        "/login_airbnb — reconnecter la session"
    )
    await update.message.reply_text(msg)






async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liste tous les emails en attente de réponse."""
    import html as _html
    from datetime import datetime
    pendings = await get_tous_pending_actifs()
    if not pendings:
        await update.message.reply_text("Aucun email en attente de réponse.")
        return

    lignes = ["<b>En attente (" + str(len(pendings)) + ")</b>"]
    for p in pendings:
        item = p["item_data"]
        exp = _html.escape(item.get("from", item.get("sender", "?")))
        sujet = _html.escape(item.get("subject", "?"))
        source = p["source"].upper()
        try:
            age = datetime.now() - datetime.fromisoformat(p["created_at"])
            heures = int(age.total_seconds() // 3600)
            mins = int((age.total_seconds() % 3600) // 60)
            age_str = (str(heures) + "h" + str(mins).zfill(2)) if heures else (str(mins) + "min")
        except Exception:
            age_str = "?"
        uid_e = item.get("uid", "?")
        folder_e = item.get("folder", "")
        ref_e = (" " + folder_e + "#" + str(uid_e)) if folder_e else (" #" + str(uid_e))
        ligne = (
            "\n<b>[" + str(p["id"]) + "]</b> " + source + " — " + age_str + ref_e + "\n"
            "De : " + exp + "\n"
            "Sujet : " + sujet
        )
        lignes.append(ligne)

    lignes.append("\n\nRéponds à un pending : tape son ID puis 1/2/3.")
    msg = "\n".join(lignes)
    for i in range(0, len(msg), 4000):
        await update.message.reply_text(msg[i:i+4000], parse_mode="HTML")


async def job_rappel_pending(context: ContextTypes.DEFAULT_TYPE):
    """V1.0.1 — Rappels selon cadence J+1 / J+7 (max 2 par pending, dedup 12h)."""
    chat_id = await recuperer_chat_id()
    if not chat_id:
        return

    a_rappeler = await get_pending_a_rappeler()
    if not a_rappeler:
        return

    logger.info("Rappels pending : " + str(len(a_rappeler)) + " a envoyer")

    for p in a_rappeler:
        try:
            item = p["item_data"]
            options = p["options"]
            exp = item.get("from", item.get("sender", "?"))
            sujet = item.get("subject", "?")
            opt = list(options) + ["", "", ""]

            msg = (
                "⏰ Rappel — " + sujet + "\n"
                "De : " + exp + "\n\n"
                "1️⃣ Option courte\n" + opt[0] + "\n\n"
                "2️⃣ Option complète\n" + opt[1] + "\n\n"
                "3️⃣ Ignorer / Traiter plus tard\n\n"
                "Réponds 1, 2, 3 ou écris ton instruction. [ID:" + str(p["id"]) + "]"
            )

            for i in range(0, len(msg), 4000):
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg[i:i+4000],
                )

            await marquer_rappel_envoye(p["id"])
            rang = (p.get("nb_rappels") or 0) + 1
            logger.info("Rappel #" + str(rang) + "/2 envoye pour pending #" + str(p["id"]))

        except Exception as e:
            logger.error("Rappel pending #" + str(p["id"]) + " erreur : " + str(e))



async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force une nouvelle session conversationnelle — utile quand l'agent dérive."""
    chat_id = update.effective_chat.id
    ConversationSession().reset(str(chat_id))
    await update.message.reply_text("Session réinitialisée.")


async def cmd_forcer_proton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import html as _html
    chat_id = update.effective_chat.id
    await update.message.reply_text("Scan Proton Mail en cours...")
    from .watchers.protonmail_watcher import poll_once
    nb, rapport = await poll_once(context.bot, chat_id)
    # Escape chaque ligne — les adresses email contiennent < > qui cassent HTML
    rapport_esc = "\n".join(_html.escape(line) for line in rapport) if rapport else "(aucun détail)"
    await update.message.reply_text(
        f"<b>Scan Proton Mail — résultat</b>\n\n{rapport_esc}",
        parse_mode="HTML"
    )


async def cmd_forcer_airbnb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("Scan Airbnb en cours...")
    from .watchers.airbnb_watcher import poll_once
    nb = await poll_once(context.bot, chat_id)
    await update.message.reply_text(f"Scan terminé : {nb} alerte(s) envoyée(s).")


async def cmd_migrate_v102(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """V1.0.2 — Migration rétroactive des pendings Proton vers les dossiers cibles. Idempotent."""
    import aiosqlite
    import json as _json
    from .tools import imap_actions

    await update.message.reply_text("🔄 Migration V1.0.2 en cours…")

    # 1) S'assurer que les 3 dossiers existent
    creation = await imap_actions.ensure_v102_folders()

    cnt_traite = 0
    cnt_reprendre = 0
    cnt_skip = 0
    cnt_fail = 0

    async with aiosqlite.connect("/root/memoire.db") as db:
        cursor = await db.execute(
            """SELECT id, item_data, statut FROM pending_actions
               WHERE source = 'protonmail' AND statut IN ('envoye','ignore')
               ORDER BY id"""
        )
        rows = await cursor.fetchall()

    for row in rows:
        pid, raw, statut = row
        try:
            item = _json.loads(raw)
        except Exception as e:
            logger.error("[IMAP_ACTION_FAIL] migrate_v102 pending #" + str(pid) + " json: " + str(e))
            cnt_fail += 1
            continue
        uid = item.get("uid")
        src_folder = item.get("folder") or "INBOX"
        if not uid:
            cnt_skip += 1
            continue
        target = imap_actions.FOLDER_TRAITE if statut == "envoye" else imap_actions.FOLDER_REPRENDRE
        if src_folder == target:
            cnt_skip += 1
            continue
        ok = await imap_actions.mark_and_move(uid, src_folder, target)
        if ok:
            if statut == "envoye":
                cnt_traite += 1
            else:
                cnt_reprendre += 1
        else:
            cnt_fail += 1

    lignes = ["✅ Migration V1.0.2 terminée", "", "Dossiers Proton :"]
    for f, ok in creation.items():
        lignes.append("  • " + f + " → " + ("OK" if ok else "FAIL"))
    lignes += [
        "",
        "Résultat :",
        "  • " + str(cnt_traite) + " pending(s) → Traité par agent",
        "  • " + str(cnt_reprendre) + " pending(s) → À reprendre",
        "  • " + str(cnt_skip) + " skippé(s) (déjà classé ou pas d'UID)",
        "  • " + str(cnt_fail) + " échec(s) IMAP (voir logs [IMAP_ACTION_FAIL])",
        "",
        "Note : les emails classés IGNORER avant V1.0.2 ne sont pas migrés "
        "(pas de trace en base). Les futurs IGNORER vont dans Auto-classés bruit automatiquement.",
    ]
    rapport = "\n".join(lignes)
    for i in range(0, len(rapport), 4000):
        await update.message.reply_text(rapport[i:i+4000])


# ── Scheduler hebdomadaire ────────────────────────────────────────────────────

async def job_tableau_bord_hebdo(context: ContextTypes.DEFAULT_TYPE):
    chat_id = await recuperer_chat_id()
    if not chat_id:
        return
    tableau = await generer_tableau_bord()
    for i in range(0, len(tableau), 4096):
        await context.bot.send_message(chat_id=chat_id, text=tableau[i:i+4096])


# ── Démarrage des watchers ────────────────────────────────────────────────────

async def job_scan_proton(context: ContextTypes.DEFAULT_TYPE):
    """Scan Proton Mail — batch 11h45 et 17h EDT."""
    chat_id = await recuperer_chat_id()
    if not chat_id:
        return
    from .watchers.protonmail_watcher import poll_once
    nb, rapport = await poll_once(context.bot, chat_id)
    logger.info(f"Batch Proton : {nb} alerte(s) | " + " | ".join(rapport[-3:]))


async def job_scan_airbnb(context: ContextTypes.DEFAULT_TYPE):
    """Scan Airbnb — batch 11h45 et 17h EDT."""
    chat_id = await recuperer_chat_id()
    if not chat_id:
        return
    from .watchers.airbnb_watcher import poll_once
    nb = await poll_once(context.bot, chat_id)
    logger.info(f"Batch Airbnb : {nb} alerte(s)")


async def post_init(application):
    await init_db()
    await init_pending_table()

    # V1.0.2 — créer les 3 dossiers Proton dès le boot (idempotent, échec non bloquant)
    try:
        from .tools import imap_actions
        creation = await imap_actions.ensure_v102_folders()
        for f, ok in creation.items():
            logger.info("V1.0.2 dossier " + f + " : " + ("OK" if ok else "FAIL"))
    except Exception as e:
        logger.error("[IMAP_ACTION_FAIL] ensure_v102_folders au boot: " + str(e))

    # Tableau de bord chaque lundi à 8h EDT (13h UTC)
    application.job_queue.run_daily(
        job_tableau_bord_hebdo,
        time=time(13, 0, 0),
        days=(0,),
        name="tableau_bord_hebdo"
    )

    # Watchers Proton + Airbnb — batch 2x/jour : 11h45 EDT (15h45 UTC) et 17h EDT (21h00 UTC)
    for heure, minute, suffix in [(15, 45, "matin"), (21, 0, "soir")]:
        application.job_queue.run_daily(
            job_scan_proton,
            time=time(heure, minute, 0),
            name=f"proton_batch_{suffix}"
        )
        application.job_queue.run_daily(
            job_scan_airbnb,
            time=time(heure, minute, 0),
            name=f"airbnb_batch_{suffix}"
        )

    # Rappel pending toutes les heures (emails sans réponse depuis >4h)
    application.job_queue.run_repeating(
        job_rappel_pending,
        interval=3600,
        first=300,  # premier check 5 min après démarrage
        name="rappel_pending"
    )

    # Recuperer les confirmations orphelines (perdues au dernier restart)
    try:
        orphelin = await get_pending_confirme_orphelin()
        if orphelin and chat_id:
            import html as _html
            _en_attente_confirmation[chat_id] = {
                "pending_id": orphelin["id"],
                "source": orphelin["source"],
                "item_data": orphelin["item_data"],
                "texte": orphelin["reponse_choisie"],
            }
            texte_esc = _html.escape(orphelin["reponse_choisie"][:500])
            source_lbl = orphelin["source"].upper()
            msg_orphelin = (
                "\u26a0\ufe0f Action non finalisee au dernier arret ("
                + source_lbl
                + "):\n\n"
                + texte_esc
                + "\n\nReponds <b>OUI</b> pour envoyer, <b>NON</b> pour annuler."
                + "\n\n<i>[ID:" + str(orphelin["id"]) + "]</i>"
            )
            await application.bot.send_message(
                chat_id=chat_id, text=msg_orphelin, parse_mode="HTML"
            )
            logger.info("Confirme orphelin recupere : pending #" + str(orphelin["id"]))
    except Exception as e:
        logger.warning("Recovery orphelin failed : " + str(e))

    # Notification de démarrage (inclut restart après crash)
    chat_id = await recuperer_chat_id()
    if chat_id:
        import datetime as _dt
        now = _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Julien OS — demarre (" + now + ")\n\n"
                    "Watchers actifs :\n"
                    "• Proton Mail — 11h45 et 17h EDT\n"
                    "• Airbnb — 11h45 et 17h EDT\n"
                    "• Tableau de bord — lundi 8h EDT"
                )
            )
        except Exception:
            pass


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("aide", cmd_aide))
    app.add_handler(CommandHandler("memoire", cmd_memoire))
    app.add_handler(CommandHandler("projets", cmd_projets))
    app.add_handler(CommandHandler("prep", cmd_prep))
    app.add_handler(CommandHandler("cr", cmd_cr))
    app.add_handler(CommandHandler("email", cmd_email))
    app.add_handler(CommandHandler("shepherd", cmd_shepherd))
    app.add_handler(CommandHandler("consolider", cmd_consolider))
    app.add_handler(CommandHandler("alerte", cmd_alerte))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("login_proton", cmd_login_proton))
    app.add_handler(CommandHandler("login_airbnb", cmd_login_airbnb))
    app.add_handler(CommandHandler("mails", cmd_mails))
    app.add_handler(CommandHandler("noter", cmd_noter))
    app.add_handler(CommandHandler("surveillance", cmd_surveillance))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("forcer_proton", cmd_forcer_proton))
    app.add_handler(CommandHandler("forcer_airbnb", cmd_forcer_airbnb))
    app.add_handler(CommandHandler("migrate_v102", cmd_migrate_v102))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Julien OS — LangGraph actif...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
