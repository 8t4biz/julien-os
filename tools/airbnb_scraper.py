"""
Airbnb — automation Playwright avec profil Chrome persistant.
Le profil est sauvegardé dans /root/julien_os/.chrome_profile/airbnb/
et survit aux redémarrages (cookies + localStorage + session).

Le navigateur est ouvert uniquement pendant le scan puis fermé immédiatement
pour libérer la RAM (~400 MB par instance Chromium).
"""
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Callable, Awaitable, Optional
from playwright.async_api import (
    async_playwright, BrowserContext, Page,
    TimeoutError as PWTimeout,
)

try:
    from playwright_stealth import Stealth as _Stealth
    _STEALTH = _Stealth()
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False

logger = logging.getLogger(__name__)

AIRBNB_URL = "https://www.airbnb.ca"
MESSAGES_URL = f"{AIRBNB_URL}/hosting/messages"
PROFILE_DIR = Path("/root/julien_os/.chrome_profile/airbnb")

InputFn = Callable[[str], Awaitable[str]]
StatusFn = Callable[[str, Optional[bytes]], Awaitable[None]]

_LAUNCH_KWARGS = dict(
    headless=True,
    args=[
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
    ],
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    viewport={"width": 1280, "height": 900},
    locale="fr-FR",
    timezone_id="America/Toronto",
)


@asynccontextmanager
async def _ctx():
    """Ouvre un BrowserContext persistant et le ferme a la sortie du bloc."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            **_LAUNCH_KWARGS,
        )
        try:
            yield ctx
        finally:
            await ctx.close()
            logger.debug("Airbnb: browser ferme, RAM liberee.")


async def _new_page(ctx: BrowserContext) -> Page:
    page = await ctx.new_page()
    if _STEALTH_AVAILABLE:
        await _STEALTH.apply_stealth_async(page)
    return page


def _est_url_login(url: str) -> bool:
    return "/login" in url or "accounts.airbnb" in url


async def _verifier_session(page: Page) -> bool:
    """
    Navigue directement vers /hosting/messages.
    Utilise uniquement par interactive_login pour savoir si un re-login est necessaire.
    """
    try:
        await page.goto(MESSAGES_URL, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(5000)

        if _est_url_login(page.url):
            logger.debug(f"Airbnb: redirige vers login ({page.url}) -> session invalide")
            return False

        try:
            await page.wait_for_selector(
                'input#phone-or-email, [data-testid="login-form"]',
                timeout=2000
            )
            logger.debug("Airbnb: formulaire login detecte -> session invalide")
            return False
        except PWTimeout:
            pass

        try:
            await page.wait_for_selector(
                '[data-testid="main-nav-profile-button"]',
                timeout=5000
            )
        except PWTimeout:
            logger.debug("Airbnb: element hote absent -> session invalide")
            return False

        if _est_url_login(page.url):
            return False

        return True

    except Exception as e:
        logger.debug(f"Airbnb _verifier_session exception: {e}")
        return False


class AirbnbClient:

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password

    async def login(self) -> bool:
        """Verifie la session. Utilise uniquement par interactive_login."""
        try:
            async with _ctx() as ctx:
                page = await _new_page(ctx)
                ok = await _verifier_session(page)
                if ok:
                    logger.info("Airbnb: session persistante valide")
                return ok
        except Exception as e:
            logger.error(f"Airbnb login check error: {e}")
            return False

    async def interactive_login(self, input_fn: InputFn, status_fn: StatusFn) -> bool:
        """Login interactif avec OTP SMS. Browser ferme apres la procedure complete."""
        try:
            async with _ctx() as ctx:
                page = await _new_page(ctx)
                if await _verifier_session(page):
                    await status_fn("Session Airbnb persistante valide. Pas besoin de se reconnecter.", None)
                    return True
                return await self._faire_login(page, input_fn, status_fn)
        except Exception as e:
            logger.error(f"Airbnb interactive_login error: {e}")
            try:
                await status_fn(f"Erreur inattendue : {e}", None)
            except Exception:
                pass
            return False

    async def _faire_login(self, page: Page,
                           input_fn: Optional[InputFn],
                           status_fn: Optional[StatusFn]) -> bool:

        async def s(msg: str, screenshot: bool = False):
            if status_fn:
                img = None
                if screenshot:
                    try:
                        img = await page.screenshot(type="jpeg", quality=70)
                    except Exception:
                        pass
                await status_fn(msg, img)
            else:
                logger.info(f"Airbnb login: {msg}")

        try:
            stealth_note = " (stealth actif)" if _STEALTH_AVAILABLE else " stealth non disponible"
            await s(f"Ouverture de Airbnb{stealth_note}...")
            await page.goto(f"{AIRBNB_URL}/login", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            try:
                btn = await page.wait_for_selector(
                    'button:has-text("Tout accepter"), button:has-text("Accept all")',
                    timeout=3000
                )
                await btn.click()
                await page.wait_for_timeout(800)
            except PWTimeout:
                pass

            try:
                email_input = await page.wait_for_selector('input#phone-or-email', timeout=10000)
            except PWTimeout:
                await s("Champ email/telephone introuvable.", screenshot=True)
                return False

            await s("Saisie de l'email...")
            await email_input.click()
            await page.wait_for_timeout(300)
            await email_input.type(self.email, delay=80)
            await page.wait_for_timeout(600)
            submit = await page.wait_for_selector('button[type="submit"]', timeout=5000)
            await submit.click()
            await page.wait_for_timeout(10000)

            try:
                otp_input = await page.wait_for_selector('input#otp-code-input', timeout=8000)
                body_text = await page.inner_text("body")
                import re
                phone_hint = ""
                m = re.search(r"\+\d[\d\s\*\-]{5,20}", body_text)
                if m:
                    phone_hint = f" ({m.group(0).strip()})"
                await s(f"Airbnb demande un code SMS{phone_hint}.", screenshot=True)
                if input_fn:
                    code = await input_fn(
                        f"Airbnb a envoye un code par SMS{phone_hint}.\n\n"
                        "Entre le code a 6 chiffres recu par SMS :"
                    )
                else:
                    await s("Code SMS requis mais mode non interactif.")
                    return False
                await otp_input.fill(code.strip())
                await page.wait_for_timeout(500)
                for sub_sel in ['button[type="submit"]', 'button:has-text("Continuer")', 'button:has-text("Verifier")']:
                    try:
                        btn = await page.wait_for_selector(sub_sel, timeout=3000)
                        await btn.click()
                        break
                    except PWTimeout:
                        continue
                await page.wait_for_timeout(5000)
            except PWTimeout:
                await s("Pas de code SMS detecte — verification directe...", screenshot=True)

            await s("Verification de la connexion...")
            await page.goto(MESSAGES_URL, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
            if _est_url_login(page.url):
                await s("Connexion echouee — redirige vers login.", screenshot=True)
                return False
            await s(f"Connecte a Airbnb. Session persistante dans {PROFILE_DIR} (30+ jours)")
            return True

        except Exception as e:
            try:
                await s(f"Erreur : {e}", screenshot=True)
            except Exception:
                pass
            logger.error(f"Airbnb login error: {e}")
            return False

    async def get_unread_messages(self, limit: int = 5) -> list | None:
        """
        Navigue vers /hosting/messages en une seule passe.
        Retourne None si session expiree (redirect login).
        Retourne une liste (possiblement vide) si session valide.
        """
        try:
            async with _ctx() as ctx:
                page = await _new_page(ctx)
                return await self._fetch_messages(page, limit)
        except Exception as e:
            logger.error(f"Airbnb get_unread_messages error: {e}")
            return None

    async def _fetch_messages(self, page: Page, limit: int) -> list | None:
        """
        Retourne None si session expiree, liste (vide ou non) si connecte.
        Inclut la meme validation SPA que _verifier_session (5s wait + form check).
        """
        try:
            await page.goto(MESSAGES_URL, wait_until="domcontentloaded", timeout=25000)
            # Attendre que le SPA Airbnb fasse sa verification cote JS
            await page.wait_for_timeout(5000)

            # Redirect URL = session invalide
            if _est_url_login(page.url):
                logger.debug(f"Airbnb: fetch redirige vers login ({page.url})")
                return None

            # Verif negative : formulaire de login present
            try:
                await page.wait_for_selector(
                    'input#phone-or-email, [data-testid="login-form"]',
                    timeout=2000
                )
                logger.debug("Airbnb: formulaire login detecte dans fetch -> session invalide")
                return None
            except PWTimeout:
                pass

            # Session valide — lire les threads
            messages = []
            threads = await page.query_selector_all('[data-testid="message-thread"]')
            if not threads:
                threads = await page.query_selector_all('[class*="thread"]')
            for thread in threads[:limit]:
                try:
                    unread_badge = await thread.query_selector('[data-testid="unread-badge"]')
                    is_bold = await thread.evaluate(
                        'el => { const name = el.querySelector("[data-testid=\'thread-guest-name\']"); '
                        'return name ? window.getComputedStyle(name).fontWeight >= 600 : false; }'
                    )
                    if not unread_badge and not is_bold:
                        continue
                    thread_id_el = await thread.get_attribute("data-thread-id")
                    guest_el = await thread.query_selector('[data-testid="thread-guest-name"]')
                    preview_el = await thread.query_selector('[data-testid="thread-message-preview"]')
                    date_el = await thread.query_selector('[data-testid="thread-date"]')
                    link = await thread.query_selector("a")
                    href = await link.get_attribute("href") if link else ""
                    guest = await guest_el.inner_text() if guest_el else "Voyageur"
                    preview = await preview_el.inner_text() if preview_el else ""
                    date = await date_el.inner_text() if date_el else ""
                    thread_id = thread_id_el or (href.split("/")[-1] if href else f"t_{guest}")
                    messages.append({
                        "id": thread_id,
                        "guest": guest.strip(),
                        "preview": preview.strip(),
                        "date": date.strip(),
                        "href": href,
                    })
                except Exception:
                    continue
            return messages

        except Exception as e:
            logger.error(f"Airbnb fetch_messages error: {e}")
            return None

    async def get_conversation(self, href: str) -> str:
        try:
            async with _ctx() as ctx:
                page = await _new_page(ctx)
                url = f"{AIRBNB_URL}{href}" if href.startswith("/") else href
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)
                msg_elements = await page.query_selector_all('[data-testid="message-bubble"]')
                if not msg_elements:
                    msg_elements = await page.query_selector_all('[class*="message-text"]')
                msgs = []
                for el in msg_elements[-10:]:
                    try:
                        msgs.append((await el.inner_text()).strip())
                    except Exception:
                        continue
                return "\n---\n".join(msgs)
        except Exception as e:
            logger.error(f"Airbnb get_conversation error: {e}")
            return ""

    async def send_message(self, href: str, message_text: str) -> bool:
        try:
            async with _ctx() as ctx:
                page = await _new_page(ctx)
                target_url = f"{AIRBNB_URL}{href}" if href.startswith("/") else href
                await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)
                input_box = await page.wait_for_selector(
                    '[data-testid="message-input"], textarea[placeholder*="message"], '
                    'textarea[placeholder*="Message"]',
                    timeout=8000
                )
                await input_box.click()
                await input_box.fill(message_text)
                await page.wait_for_timeout(500)
                send_btn = await page.wait_for_selector(
                    '[data-testid="send-message-button"], button[type="submit"][aria-label*="Send"]',
                    timeout=5000
                )
                await send_btn.click()
                await page.wait_for_timeout(2000)
                return True
        except Exception as e:
            logger.error(f"Airbnb send_message error: {e}")
            return False
