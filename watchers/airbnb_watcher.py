"""
Airbnb Watcher — polling toutes les 60 minutes.
Détecte les nouveaux messages voyageurs, envoie une alerte Telegram.
"""
import asyncio
import logging
import json

from .flags import alerte_deja_envoyee, marquer_alerte, reset_alerte

logger = logging.getLogger(__name__)

_FLAG = "airbnb_session"


async def charger_credentials() -> dict | None:
    try:
        with open("/root/secrets.json") as f:
            secrets = json.load(f)
        ab = secrets.get("airbnb", {})
        if not ab.get("email") or not ab.get("password"):
            return None
        return ab
    except FileNotFoundError:
        return None


async def poll_once(bot, chat_id: int) -> int:
    from ..tools.airbnb_scraper import AirbnbClient
    from ..agents.airbnb_agent import analyser_priorite, generer_options, formater_alerte_telegram
    from ..memory.pending import creer_pending, item_deja_traite

    creds = await charger_credentials()
    if not creds:
        return 0

    client = AirbnbClient(email=creds["email"], password=creds["password"])

    # Une seule passe : navigue vers /hosting/messages
    # None = session expirée (redirect login), liste = session valide
    messages = await client.get_unread_messages(limit=5)

    if messages is None:
        if not alerte_deja_envoyee(_FLAG):
            marquer_alerte(_FLAG)  # Flag AVANT l'envoi
            logger.warning("Airbnb: session expirée — notification envoyée (SQLite flag)")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "Airbnb — session expirée\n\n"
                        "Je ne peux plus accéder à tes messages Airbnb automatiquement.\n"
                        "Lance /login_airbnb pour te reconnecter."
                    ),
                )
            except Exception as e:
                logger.error(f"Airbnb: impossible d'envoyer l'alerte session: {e}")
        return 0

    # Session OK — reset le flag si on avait notifié
    if alerte_deja_envoyee(_FLAG):
        reset_alerte(_FLAG)
        logger.info("Airbnb: session restaurée, flag SQLite supprimé")

    alertes_envoyees = 0

    for msg_data in messages:
        msg_id = msg_data["id"]
        if await item_deja_traite("airbnb", msg_id):
            continue

        priorite = await analyser_priorite(msg_data)

        # Charge la conversation complète
        if msg_data.get("href"):
            conversation = await client.get_conversation(msg_data["href"])
            msg_data["conversation"] = conversation

        analyse, options = await generer_options(msg_data)

        pending_id = await creer_pending(
            source="airbnb",
            item_id=msg_id,
            item_data=msg_data,
            options=options,
        )

        alerte_msg = formater_alerte_telegram(msg_data, analyse, options)
        alerte_msg += f"\n\n_[ID:{pending_id}]_"

        await bot.send_message(chat_id=chat_id, text=alerte_msg[:4096], parse_mode="Markdown")
        alertes_envoyees += 1

    return alertes_envoyees


async def demarrer_watcher(bot, chat_id: int, intervalle_secondes: int = 3600):
    logger.info(f"Airbnb watcher démarré (intervalle: {intervalle_secondes}s)")
    while True:
        try:
            await poll_once(bot, chat_id)
        except Exception as e:
            logger.error(f"Airbnb watcher error: {e}")
        await asyncio.sleep(intervalle_secondes)
