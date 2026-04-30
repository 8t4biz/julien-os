"""
Playwright base — gestionnaire de navigateur partagé avec sessions persistantes.
Un seul browser tourne en background, les pages sont ouvertes/fermées à la demande.
"""
import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

SESSIONS_DIR = Path("/root/julien_os/.sessions")
SESSIONS_DIR.mkdir(exist_ok=True)


class BrowserManager:
    """Gestionnaire singleton du navigateur Chromium headless."""

    _instance: "BrowserManager | None" = None
    _playwright = None
    _browser: Browser | None = None

    @classmethod
    async def get(cls) -> "BrowserManager":
        if cls._instance is None:
            cls._instance = BrowserManager()
        if cls._browser is None or not cls._browser.is_connected():
            await cls._instance._launch()
        return cls._instance

    async def _launch(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,900",
            ]
        )

    async def new_context(self, session_name: str) -> BrowserContext:
        """Retourne un contexte avec cookies persistants."""
        cookie_file = SESSIONS_DIR / f"{session_name}.json"
        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="fr-CA",
        )
        if cookie_file.exists():
            cookies = json.loads(cookie_file.read_text())
            await context.add_cookies(cookies)
        return context

    async def save_session(self, context: BrowserContext, session_name: str):
        cookie_file = SESSIONS_DIR / f"{session_name}.json"
        cookies = await context.cookies()
        cookie_file.write_text(json.dumps(cookies, indent=2))

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        BrowserManager._instance = None
        BrowserManager._browser = None


async def screenshot_debug(page: Page, nom: str):
    """Sauvegarde un screenshot pour débugger (désactiver en prod)."""
    path = f"/tmp/debug_{nom}.png"
    await page.screenshot(path=path)
