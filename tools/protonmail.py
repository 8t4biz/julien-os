"""
Proton Mail — accès via Proton Bridge (IMAP/SMTP).
Remplace complètement l'approche Playwright.

Proton Bridge écoute sur :
  IMAP : 127.0.0.1:1143  (STARTTLS)
  SMTP : 127.0.0.1:1025  (STARTTLS)

Le bridge password est différent du mot de passe ProtonMail.
Il est généré par Bridge et stocké dans secrets.json["protonmail"]["bridge_password"].
"""
import imaplib
import smtplib
import email
import email.mime.text
import email.mime.multipart
import email.header
import logging
import ssl
from typing import Optional

logger = logging.getLogger(__name__)

IMAP_HOST = "127.0.0.1"
IMAP_PORT = 1143
SMTP_HOST = "127.0.0.1"
SMTP_PORT = 1025


def _decode_header(raw: str) -> str:
    parts = email.header.decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


class ProtonMailClient:
    """Client IMAP/SMTP via Proton Bridge local."""

    def __init__(self, email_addr: str, bridge_password: str,
                 # legacy params ignorés — conservés pour compatibilité
                 password: str = "", mailbox_password: str = "", totp_secret: str = ""):
        self.email = email_addr
        self.bridge_password = bridge_password

    # ── Connexion IMAP ────────────────────────────────────────────────────────

    def _connect_imap(self) -> imaplib.IMAP4:
        """Ouvre une connexion IMAP avec STARTTLS (cert auto-signé accepté)."""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
        conn.starttls(ssl_context=ctx)
        conn.login(self.email, self.bridge_password)
        return conn

    # ── API publique ──────────────────────────────────────────────────────────

    async def login(self) -> bool:
        """Vérifie que Bridge est joignable et les credentials valides."""
        try:
            conn = self._connect_imap()
            conn.logout()
            logger.info("ProtonMail Bridge: connexion IMAP OK")
            return True
        except Exception as e:
            logger.error(f"ProtonMail Bridge: connexion IMAP échouée: {e}")
            return False

    # Dossiers scannés à chaque polling — ordre : plus important en premier.
    # "All Mail" et "Archive" sont des vues virtuelles (agrégats) — exclues pour éviter les doublons.
    FOLDERS_TO_SCAN = [
        "INBOX",
        "Folders/[INC] Consulting",
        "Folders/[INC] Build",
        "Folders/[INC] Finance",
        "Folders/[FI]",
        "Folders/[PERSO]",
    ]

    async def get_unread_emails(self, limit: int = 10) -> list[dict]:
        """
        Retourne les emails non lus depuis tous les dossiers pertinents.
        Déduplication par Message-ID — un email ne remonte qu'une fois même s'il
        apparaît dans plusieurs dossiers/labels ProtonMail.
        """
        try:
            conn = self._connect_imap()
            seen_ids: set[str] = set()
            emails: list[dict] = []

            for folder in self.FOLDERS_TO_SCAN:
                try:
                    status, _ = conn.select(f'"{folder}"', readonly=True)
                    if status != "OK":
                        logger.info(f"ProtonMail: dossier {folder!r} introuvable — skip")
                        continue

                    status, data = conn.search(None, "UNSEEN")
                    if status != "OK":
                        continue

                    uids = data[0].split()
                    if not uids:
                        logger.info(f"ProtonMail: {folder!r} → 0 non-lus")
                        continue

                    logger.info(f"ProtonMail: {folder!r} → {len(uids)} non-lu(s) : {[u.decode() for u in uids]}")

                    # Les N plus récents en premier
                    for uid in reversed(uids[-limit:]):
                        status, msg_data = conn.fetch(uid, "(BODY.PEEK[])")
                        if status != "OK":
                            logger.warning(f"ProtonMail: fetch uid={uid.decode()} dans {folder!r} → {status}")
                            continue
                        if not msg_data or not isinstance(msg_data[0], tuple):
                            logger.warning(f"ProtonMail: uid={uid.decode()} msg_data inattendu: {msg_data!r:.80}")
                            continue

                        raw = msg_data[0][1]
                        if not raw:
                            continue
                        msg = email.message_from_bytes(raw)

                        msg_id = msg.get("Message-ID", "")
                        clean_id = msg_id.strip("<>") if msg_id else f"{folder}/{uid.decode()}"

                        # Déduplication — skip si déjà vu dans un autre dossier
                        if clean_id in seen_ids:
                            logger.info(f"ProtonMail: uid={uid.decode()} {folder!r} — doublon skippé (id={clean_id[:40]})")
                            continue
                        seen_ids.add(clean_id)

                        subject = _decode_header(msg.get("Subject", "(sans sujet)"))
                        sender  = _decode_header(msg.get("From", ""))
                        date    = msg.get("Date", "")
                        body    = _extract_text_body(msg)

                        logger.info(f"ProtonMail: uid={uid.decode()} {folder!r} sujet={subject!r:.60} from={sender!r:.50}")

                        emails.append({
                            "id":      clean_id,
                            "uid":     uid.decode(),
                            "folder":  folder,
                            "subject": subject,
                            "from":    sender,
                            "date":    date,
                            "snippet": body[:300],
                        })

                        if len(emails) >= limit:
                            break

                except Exception as e:
                    logger.error(f"ProtonMail: erreur dossier {folder!r}: {e}")
                    continue

                if len(emails) >= limit:
                    break

            conn.logout()
            logger.info(f"ProtonMail: get_unread_emails → {len(emails)} email(s) au total")
            return emails

        except Exception as e:
            logger.error(f"ProtonMail Bridge: get_unread_emails error: {e}")
            return []

    async def get_email_body_by_uid(self, uid: str, folder: str = "INBOX") -> str:
        """
        Charge le corps complet d'un email par UID IMAP.
        folder : dossier où se trouve l'email (récupéré depuis email_data["folder"]).
        """
        try:
            conn = self._connect_imap()
            conn.select(f'"{folder}"')
            status, msg_data = conn.fetch(uid.encode(), "(BODY.PEEK[])")
            conn.logout()
            if status != "OK" or not msg_data or not msg_data[0]:
                return ""
            msg = email.message_from_bytes(msg_data[0][1])
            return _extract_text_body(msg)
        except Exception as e:
            logger.error(f"ProtonMail Bridge: get_email_body_by_uid error: {e}")
            return ""

    async def get_email_body(self, email_id: str) -> str:
        """Charge le corps complet par Message-ID (fallback). Préférer get_email_body_by_uid."""
        try:
            conn = self._connect_imap()
            conn.select("INBOX")

            status, data = conn.search(None, f'HEADER Message-ID "{email_id}"')
            if status != "OK" or not data[0]:
                conn.logout()
                return ""

            uid = data[0].split()[0]
            status, msg_data = conn.fetch(uid, "(BODY.PEEK[])")
            conn.logout()
            if status != "OK":
                return ""

            msg = email.message_from_bytes(msg_data[0][1])
            return _extract_text_body(msg)

        except Exception as e:
            logger.error(f"ProtonMail Bridge: get_email_body error: {e}")
            return ""

    async def mark_as_read(self, uid: str, folder: str = "INBOX") -> bool:
        r"""Marque un email comme lu (\Seen) par UID IMAP."""
        try:
            conn = self._connect_imap()
            conn.select(f'"{folder}"')
            conn.store(uid.encode(), "+FLAGS", "\\Seen")
            conn.logout()
            logger.info(f"ProtonMail: email UID={uid} marqué comme lu")
            return True
        except Exception as e:
            logger.error(f"ProtonMail Bridge: mark_as_read error: {e}")
            return False

    async def reply_to_email(self, email_id: str, reply_text: str,
                             uid: str = "", folder: str = "INBOX") -> bool:
        """
        Envoie une réponse à un email via SMTP Bridge.
        Marque l'original comme lu après envoi.
        uid    : optionnel, pour mark_as_read plus rapide.
        folder : dossier de l'email original (depuis email_data["folder"]).
        """
        try:
            # Récupère l'email original pour construire les headers de réponse
            conn = self._connect_imap()
            conn.select(f'"{folder}"')

            original = None
            original_uid = uid

            if not original_uid:
                status, data = conn.search(None, f'HEADER Message-ID "{email_id}"')
                if status == "OK" and data[0]:
                    original_uid = data[0].split()[0].decode()

            if original_uid:
                status, msg_data = conn.fetch(original_uid.encode(), "(BODY.PEEK[])")
                if status == "OK" and msg_data and msg_data[0]:
                    original = email.message_from_bytes(msg_data[0][1])

            conn.logout()

            if not original:
                logger.error("ProtonMail: email original introuvable pour reply")
                return False

            # Compose la réponse
            reply = email.mime.multipart.MIMEMultipart()
            reply["From"]       = self.email
            reply["To"]         = original.get("From", "")
            reply["Subject"]    = "Re: " + _decode_header(original.get("Subject", ""))
            reply["In-Reply-To"] = f"<{email_id}>"
            reply["References"]  = f"<{email_id}>"
            reply.attach(email.mime.text.MIMEText(reply_text, "plain", "utf-8"))

            # Envoie via SMTP Bridge
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.login(self.email, self.bridge_password)
                smtp.sendmail(self.email, [reply["To"]], reply.as_bytes())

            logger.info(f"ProtonMail: réponse envoyée à {reply['To']}")

            # Marque l'original comme lu dans le bon dossier
            if original_uid:
                await self.mark_as_read(original_uid, folder=folder)

            return True

        except Exception as e:
            logger.error(f"ProtonMail Bridge: reply error: {e}")
            return False

    async def get_latest_emails(self, limit: int = 5) -> list[dict]:
        """Retourne les N emails les plus récents triés par INTERNALDATE décroissant."""
        try:
            from email.utils import parsedate_to_datetime
            import re as _re

            conn = self._connect_imap()
            conn.select("INBOX")

            status, data = conn.search(None, "ALL")
            if status != "OK":
                conn.logout()
                return []

            all_uids = data[0].split()
            if not all_uids:
                conn.logout()
                return []

            uid_list = b",".join(all_uids)
            status, dates_data = conn.fetch(uid_list, "(INTERNALDATE)")
            if status != "OK":
                conn.logout()
                return []

            uid_dates = []
            for item in dates_data:
                line = item.decode() if isinstance(item, bytes) else (item[0].decode() if item[0] else "")
                uid_m  = _re.match(r"(\d+)", line)
                date_m = _re.search(r'INTERNALDATE "([^"]+)"', line)
                if not uid_m or not date_m:
                    continue
                seq = uid_m.group(1).encode()
                try:
                    ts = parsedate_to_datetime(date_m.group(1)).timestamp()
                except Exception:
                    ts = 0
                uid_dates.append((seq, ts))

            uid_dates.sort(key=lambda x: x[1], reverse=True)
            top_seqs = [seq for seq, _ in uid_dates[:limit]]

            emails = []
            for seq in top_seqs:
                status, msg_data = conn.fetch(seq, "(RFC822.HEADER FLAGS INTERNALDATE)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                header_raw = msg_data[0][1]
                full_meta = " ".join(
                    item.decode(errors="replace") for item in msg_data if isinstance(item, bytes)
                )
                if isinstance(msg_data[0], tuple) and msg_data[0][0]:
                    full_meta = msg_data[0][0].decode(errors="replace") + " " + full_meta

                msg     = email.message_from_bytes(header_raw)
                subject = _decode_header(msg.get("Subject", "(sans sujet)"))
                sender  = _decode_header(msg.get("From", ""))
                msg_id  = msg.get("Message-ID", seq.decode())

                date_fmt = "\u2014"
                dm = _re.search(r'INTERNALDATE "([^"]+)"', full_meta)
                if dm:
                    try:
                        date_fmt = parsedate_to_datetime(dm.group(1)).strftime("%-d %b %Y, %H:%M")
                    except Exception:
                        pass

                is_unread = "\\Seen" not in full_meta

                emails.append({
                    "id":      msg_id.strip("<>"),
                    "uid":     seq.decode(),
                    "subject": subject,
                    "from":    sender,
                    "date":    date_fmt,
                    "unread":  is_unread,
                })

            conn.logout()
            return emails

        except Exception as e:
            logger.error(f"ProtonMail Bridge: get_latest_emails error: {e}")
            return []

    # ── Méthodes stub pour compatibilité ────────────────────────────────────

    async def interactive_login(self, input_fn, status_fn) -> bool:
        """Proton Bridge ne nécessite pas de login interactif via Telegram."""
        await status_fn(
            "\u2139\ufe0f Proton Mail utilise Proton Bridge (IMAP).\n\n"
            "Le login se configure sur le VPS :\n"
            "`protonmail-bridge --cli`\n\n"
            "Ensuite bridge_password est récupéré automatiquement.",
            None
        )
        return await self.login()


# ── Helpers privés ────────────────────────────────────────────────────────────

def _extract_text_body(msg: email.message.Message) -> str:
    """
    Extrait le corps texte brut d'un message email.
    Préfère text/plain. Fallback text/html avec strip des balises.
    Fonctionne pour les emails multipart et non-multipart (HTML seul).
    """
    import re

    def _strip_html(html: str) -> str:
        text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    body_plain = ""
    body_html  = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not body_plain:
                charset = part.get_content_charset() or "utf-8"
                body_plain = part.get_payload(decode=True).decode(charset, errors="replace")
            elif ct == "text/html" and not body_html:
                charset = part.get_content_charset() or "utf-8"
                html = part.get_payload(decode=True).decode(charset, errors="replace")
                body_html = _strip_html(html)
    else:
        charset = msg.get_content_charset() or "utf-8"
        raw = msg.get_payload(decode=True).decode(charset, errors="replace")
        if msg.get_content_type() == "text/html":
            body_html = _strip_html(raw)
        else:
            body_plain = raw

    return (body_plain or body_html).strip()
