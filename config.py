"""
Julien OS — chargement centralisé des secrets via .env.

Charge le fichier .env (production : /root/.env, local : ./.env) et expose
chaque secret comme une variable de module typée str. Lève ValueError au
chargement si une variable requise est manquante — pas de fallback à None,
pas d'erreurs différées au moment de l'utilisation.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

_PROD_ENV = Path("/root/.env")
_LOCAL_ENV = Path(__file__).resolve().parent / ".env"

if _PROD_ENV.exists():
    load_dotenv(_PROD_ENV)
elif _LOCAL_ENV.exists():
    load_dotenv(_LOCAL_ENV)


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(
            f"Variable d'environnement requise manquante : {name}. "
            f"Vérifie /root/.env (prod) ou ./.env (local) — voir .env.example."
        )
    return value


TELEGRAM_TOKEN: str = _require("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY: str = _require("ANTHROPIC_API_KEY")
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")
NOTION_TOKEN: str = _require("NOTION_TOKEN")

PROTONMAIL_EMAIL: str = _require("PROTONMAIL_EMAIL")
PROTONMAIL_PASSWORD: str = _require("PROTONMAIL_PASSWORD")
PROTONMAIL_MAILBOX_PASSWORD: str = _require("PROTONMAIL_MAILBOX_PASSWORD")
PROTONMAIL_TOTP_SECRET: str = _require("PROTONMAIL_TOTP_SECRET")
PROTONMAIL_BRIDGE_PASSWORD: str = _require("PROTONMAIL_BRIDGE_PASSWORD")

AIRBNB_EMAIL: str = _require("AIRBNB_EMAIL")
AIRBNB_PASSWORD: str = _require("AIRBNB_PASSWORD")
