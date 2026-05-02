"""
Proton Mail Watcher — batch 2x/jour (11h45 et 17h EDT).
Flux complet : lecture → analyse → options → Telegram → en attente réponse Julien.
"""
import logging
import json
from datetime import datetime

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


async def poll_once(bot, chat_id: int) -> tuple[int, dict]:
    """
    Un cycle de scan complet.

    Retourne (alertes_envoyees, scan_data) où scan_data = {
        "scan_at": iso timestamp,
        "bridge_ok": bool,
        "error": str | None,
        "emails": [...],            # emails traités CE scan, chacun avec priorite/uid/from/subject/...
        "alertes_envoyees": int,
    }
    """
    from ..tools.protonmail import ProtonMailClient
    from ..agents.protonmail_agent import analyser_et_generer, formater_alerte_telegram
    from ..memory.pending import creer_pending, item_deja_traite, get_pending_by_item_id, update_pending_item_data
    from ..memory.scan_state import enregistrer_scan

    scan_at = datetime.now().isoformat()
    scan_data = {
        "scan_at": scan_at,
        "bridge_ok": False,
        "error": None,
        "emails": [],
        "alertes_envoyees": 0,
    }

    creds = await charger_credentials()
    if not creds:
        scan_data["error"] = "bridge_password manquant dans secrets.json"
        logger.warning("ProtonMail: " + scan_data["error"])
        return 0, scan_data

    client = ProtonMailClient(
        email_addr=creds["email"],
        bridge_password=creds["bridge_password"],
    )

    connecte = await client.login()
    scan_data["bridge_ok"] = connecte
    logger.info(f"ProtonMail: login Bridge → {'OK' if connecte else 'ÉCHEC'}")

    if not connecte:
        scan_data["error"] = "connexion IMAP échouée"
        if not alerte_deja_envoyee(_FLAG):
            marquer_alerte(_FLAG)
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "Proton Mail Bridge — connexion IMAP échouée.\n"
                        "Sur le VPS : systemctl status proton-bridge ; systemctl restart proton-bridge"
                    ),
                )
            except Exception as e:
                logger.error(f"ProtonMail: alerte Bridge échouée: {e}")
        return 0, scan_data

    if alerte_deja_envoyee(_FLAG):
        reset_alerte(_FLAG)
        logger.info("ProtonMail: Bridge OK, flag réinitialisé")

    emails = await client.get_unread_emails(limit=10)
    logger.info(f"ProtonMail: get_unread_emails → {len(emails)} email(s)")

    if not emails:
        await enregistrer_scan("protonmail", total=0, actionable=0, bruit=0)
        return 0, scan_data

    alertes_envoyees = 0
    nouveau_emails = []  # emails traités ce scan (skipped exclus)

    for email_data in emails:
        email_id = email_data["id"]
        uid      = email_data["uid"]
        sujet    = email_data.get("subject", "?")
        expediteur = email_data.get("from", "?")

        logger.info(f"ProtonMail: traitement uid={uid} sujet={sujet!r} from={expediteur!r}")

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
            continue

        folder = email_data.get("folder", "INBOX")
        body = await client.get_email_body_by_uid(uid, folder=folder)
        if body:
            email_data["body"] = body
        logger.info(f"ProtonMail: uid={uid} corps chargé : {len(body)} chars depuis {folder!r}")

        result = await analyser_et_generer(email_data)
        priorite = result.get("priorite", "NORMAL").upper()
        contexte = result.get("contexte", "")
        email_data["priorite"] = priorite
        logger.info(f"ProtonMail: uid={uid} LLM → priorite={priorite} contexte={contexte[:80]!r}")

        if priorite == "IGNORER":
            try:
                from ..tools import imap_actions
                await imap_actions.mark_and_move(uid, folder, imap_actions.FOLDER_BRUIT)
            except Exception as e:
                logger.error("[IMAP_ACTION_FAIL] hook C uid=" + str(uid) + ": " + str(e))
            nouveau_emails.append(email_data)
            continue

        options = [
            result.get("option_courte", "Option courte non disponible"),
            result.get("option_complete", "Option complète non disponible"),
            "Ignorer / Traiter plus tard",
        ]

        pending_id = await creer_pending(
            source="protonmail",
            item_id=email_id,
            item_data=email_data,
            options=options,
        )
        email_data["pending_id"] = pending_id
        logger.info(f"ProtonMail: uid={uid} pending créé id={pending_id}")

        alerte_msg = formater_alerte_telegram(email_data, contexte, options)
        alerte_msg += f"\n\n<i>[ID:{pending_id}]</i>"

        for i in range(0, len(alerte_msg), 4000):
            await bot.send_message(
                chat_id=chat_id,
                text=alerte_msg[i:i + 4000],
                parse_mode="HTML",
            )

        alertes_envoyees += 1
        nouveau_emails.append(email_data)
        logger.info(f"ProtonMail: uid={uid} alerte envoyée [{priorite}]")

    actionable_count = sum(1 for e in nouveau_emails if (e.get("priorite") or "NORMAL").upper() != "IGNORER")
    bruit_count = sum(1 for e in nouveau_emails if (e.get("priorite") or "NORMAL").upper() == "IGNORER")
    await enregistrer_scan(
        "protonmail",
        total=len(nouveau_emails),
        actionable=actionable_count,
        bruit=bruit_count,
    )

    scan_data["emails"] = nouveau_emails
    scan_data["alertes_envoyees"] = alertes_envoyees
    return alertes_envoyees, scan_data
