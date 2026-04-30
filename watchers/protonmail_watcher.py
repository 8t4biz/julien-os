"""
Proton Mail Watcher — batch 2x/jour (11h45 et 17h EDT).
Flux complet : lecture → analyse → options → Telegram → en attente réponse Julien.
"""
import logging
import json

from .flags import alerte_deja_envoyee, marquer_alerte, reset_alerte

logger = logging.getLogger(__name__)

_FLAG = "proton_session"


async def charger_credentials() -> dict | None:
    try:
        with open("/root/secrets.json") as f:
            secrets = json.load(f)
        pm = secrets.get("protonmail", {})
        if not pm.get("email") or not pm.get("bridge_password"):
            return None
        return pm
    except FileNotFoundError:
        return None


async def poll_once(bot, chat_id: int) -> tuple[int, list[str]]:
    """
    Un cycle de scan complet.
    Retourne (nb_alertes_envoyees, rapport_lignes).
    rapport_lignes : liste de strings décrivant chaque étape — pour debug Telegram.
    """
    from ..tools.protonmail import ProtonMailClient
    from ..agents.protonmail_agent import analyser_et_generer, formater_alerte_telegram
    from ..memory.pending import creer_pending, item_deja_traite, get_pending_by_item_id, update_pending_item_data

    rapport = []

    creds = await charger_credentials()
    if not creds:
        msg = "❌ bridge_password manquant dans secrets.json"
        logger.warning(f"ProtonMail: {msg}")
        rapport.append(msg)
        return 0, rapport

    client = ProtonMailClient(
        email_addr=creds["email"],
        bridge_password=creds["bridge_password"],
    )

    # 1. Connexion Bridge
    connecte = await client.login()
    logger.info(f"ProtonMail: login Bridge → {'OK' if connecte else 'ÉCHEC'}")
    rapport.append(f"{'✅' if connecte else '❌'} Bridge IMAP → {'connecté' if connecte else 'ÉCHEC connexion'}")

    if not connecte:
        if not alerte_deja_envoyee(_FLAG):
            marquer_alerte(_FLAG)
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "⚠️ Proton Mail Bridge — connexion IMAP échouée\n\n"
                        "Vérifie sur le VPS :\n"
                        "<code>systemctl status proton-bridge</code>\n"
                        "<code>systemctl restart proton-bridge</code>"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"ProtonMail: alerte Bridge échouée: {e}")
        return 0, rapport

    if alerte_deja_envoyee(_FLAG):
        reset_alerte(_FLAG)
        logger.info("ProtonMail: Bridge OK, flag réinitialisé")

    # 2. Récupération emails non lus
    emails = await client.get_unread_emails(limit=10)
    logger.info(f"ProtonMail: get_unread_emails → {len(emails)} email(s)")
    rapport.append(f"📬 Emails non lus trouvés : {len(emails)}")

    if not emails:
        rapport.append("   → Boîte vide ou tous lus")
        return 0, rapport

    alertes_envoyees = 0

    for email_data in emails:
        email_id = email_data["id"]
        uid      = email_data["uid"]
        sujet    = email_data.get("subject", "?")
        expediteur = email_data.get("from", "?")

        logger.info(f"ProtonMail: traitement uid={uid} sujet={sujet!r} from={expediteur!r}")
        rapport.append(f"\n📧 uid={uid} | {sujet[:60]}")
        rapport.append(f"   De : {expediteur[:60]}")

        # Anti-doublon
        deja = await item_deja_traite("protonmail", email_id)
        logger.info(f"ProtonMail: uid={uid} item_deja_traite → {deja}")
        if deja:
            existant = await get_pending_by_item_id("protonmail", email_id)
            if existant:
                stored_uid = existant["item_data"].get("uid")
                stored_folder = existant["item_data"].get("folder")
                if existant["statut"] == "en_attente" and (stored_uid != uid or stored_folder != email_data.get("folder")):
                    refreshed = dict(existant["item_data"])
                    refreshed["uid"]    = uid
                    refreshed["folder"] = email_data.get("folder", "INBOX")
                    await update_pending_item_data(existant["id"], refreshed)
                    logger.info(f"ProtonMail: pending #{existant['id']} rafraîchi → uid={uid} folder={refreshed['folder']!r}")
                    rapport.append(f"   🔄 pending #{existant['id']} ({existant['statut']}) — UID rafraîchi {stored_uid}→{uid}")
                else:
                    rapport.append(f"   ⏭ déjà traité — pending #{existant['id']} ({existant['statut']})")
            else:
                rapport.append("   ⏭ déjà traité (pending_actions) — skippé")
            continue

        # Corps complet — en précisant le dossier source
        folder = email_data.get("folder", "INBOX")
        body = await client.get_email_body_by_uid(uid, folder=folder)
        if body:
            email_data["body"] = body
        logger.info(f"ProtonMail: uid={uid} corps chargé : {len(body)} chars depuis {folder!r}")
        rapport.append(f"   📄 Corps : {len(body)} chars  [{folder}]")

        # Analyse LLM
        result = await analyser_et_generer(email_data)
        priorite = result.get("priorite", "NORMAL").upper()
        contexte = result.get("contexte", "")
        logger.info(f"ProtonMail: uid={uid} LLM → priorite={priorite} contexte={contexte[:80]!r}")
        rapport.append(f"   🤖 LLM : {priorite} — {contexte[:80]}")

        if priorite == "IGNORER":
            rapport.append("   🚫 Classé IGNORER → pas d'alerte envoyée")
            # V1.0.2 Hook C — déplacer vers "Auto-classés bruit"
            try:
                from ..tools import imap_actions
                await imap_actions.mark_and_move(
                    uid, folder, imap_actions.FOLDER_BRUIT
                )
            except Exception as e:
                logger.error("[IMAP_ACTION_FAIL] hook C uid=" + str(uid) + ": " + str(e))
            continue

        # Options
        options = [
            result.get("option_courte", "Option courte non disponible"),
            result.get("option_complete", "Option complète non disponible"),
            "Ignorer / Traiter plus tard",
        ]

        # Pending
        pending_id = await creer_pending(
            source="protonmail",
            item_id=email_id,
            item_data=email_data,
            options=options,
        )
        logger.info(f"ProtonMail: uid={uid} pending créé id={pending_id}")

        # Envoi Telegram
        alerte_msg = formater_alerte_telegram(email_data, contexte, options)
        alerte_msg += f"\n\n<i>[ID:{pending_id}]</i>"

        for i in range(0, len(alerte_msg), 4000):
            await bot.send_message(
                chat_id=chat_id,
                text=alerte_msg[i:i + 4000],
                parse_mode="HTML",
            )

        alertes_envoyees += 1
        rapport.append(f"   ✅ Alerte envoyée (pending #{pending_id})")
        logger.info(f"ProtonMail: uid={uid} alerte envoyée [{priorite}]")

    rapport.append(f"\n📊 Total : {alertes_envoyees} alerte(s) envoyée(s)")
    return alertes_envoyees, rapport
