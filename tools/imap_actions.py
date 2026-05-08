"""
V1.0.2 — Actions IMAP post-traitement.

Toutes les fonctions sont idempotentes et ne lèvent jamais d'exception
(les échecs sont loggés avec préfixe [IMAP_ACTION_FAIL] et la fonction retourne False).

Les dossiers cibles sont créés sous la racine "Folders/" pour être cohérents
avec ce que Proton Bridge expose déjà (Folders/[INC] Build, etc.).

Les noms de dossier non-ASCII sont encodés en modified UTF-7 (RFC 3501) avant
d'être passés à imaplib, qui n'accepte pas l'UTF-8 brut.
"""
import base64
import imaplib
import logging
import ssl

from julien_os.config import PROTONMAIL_BRIDGE_PASSWORD, PROTONMAIL_EMAIL

logger = logging.getLogger(__name__)

IMAP_HOST = "127.0.0.1"
IMAP_PORT = 1143

FOLDER_TRAITE = "Folders/Traité par agent"
FOLDER_REPRENDRE = "Folders/À reprendre"
FOLDER_BRUIT = "Folders/Auto-classés bruit"

V102_FOLDERS = (FOLDER_TRAITE, FOLDER_REPRENDRE, FOLDER_BRUIT)


def _imap_utf7_encode(name: str) -> str:
    """RFC 3501 modified UTF-7 encoding pour les noms de mailbox IMAP."""
    res = []
    buf = []

    def _flush():
        if buf:
            data = "".join(buf).encode("utf-16-be")
            b64 = base64.b64encode(data).rstrip(b"=").replace(b"/", b",").decode("ascii")
            res.append("&" + b64 + "-")
            buf.clear()

    for ch in name:
        o = ord(ch)
        if 0x20 <= o <= 0x7E:
            _flush()
            if ch == "&":
                res.append("&-")
            else:
                res.append(ch)
        else:
            buf.append(ch)
    _flush()
    return "".join(res)


def _q(folder: str) -> str:
    """Renvoie un nom de dossier IMAP-quoté (encodé mUTF-7 + entouré de guillemets)."""
    return '"' + _imap_utf7_encode(folder) + '"'


def _connect() -> imaplib.IMAP4:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    conn = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
    conn.starttls(ssl_context=ctx)
    conn.login(PROTONMAIL_EMAIL, PROTONMAIL_BRIDGE_PASSWORD)
    return conn


def _seq(uid) -> bytes:
    if isinstance(uid, bytes):
        return uid
    return str(uid).encode()


async def ensure_folder(folder_name: str) -> bool:
    """CREATE le dossier IMAP si absent. Idempotent (NO = déjà présent → succès)."""
    try:
        conn = _connect()
        try:
            status, resp = conn.create(_q(folder_name))
            if status == "OK":
                logger.info(f"[IMAP] dossier créé: {folder_name}")
                return True
            # NO peut signifier "already exists" — on considère ça comme un succès
            msg = b" ".join(resp).decode(errors="replace") if resp else ""
            if "exist" in msg.lower() or status == "NO":
                logger.info(f"[IMAP] dossier déjà présent: {folder_name}")
                return True
            logger.error(f"[IMAP_ACTION_FAIL] ensure_folder({folder_name}): {status} {msg}")
            return False
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"[IMAP_ACTION_FAIL] ensure_folder({folder_name}): {e}")
        return False


async def ensure_v102_folders() -> dict:
    """Crée les 3 dossiers V1.0.2. Retourne un dict folder -> bool."""
    results = {}
    for f in V102_FOLDERS:
        results[f] = await ensure_folder(f)
    return results


async def mark_as_read(uid, folder: str = "INBOX") -> bool:
    """STORE +FLAGS \\Seen sur l'UID/seq donné dans le folder."""
    try:
        conn = _connect()
        try:
            status, _ = conn.select(_q(folder))
            if status != "OK":
                logger.error(f"[IMAP_ACTION_FAIL] mark_as_read SELECT {folder!r}: {status}")
                return False
            conn.store(_seq(uid), "+FLAGS", "\\Seen")
            logger.info(f"[IMAP] mark_as_read uid={uid} folder={folder!r} OK")
            return True
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"[IMAP_ACTION_FAIL] mark_as_read uid={uid} folder={folder!r}: {e}")
        return False


async def move_to_folder(uid, src_folder: str, dst_folder: str) -> bool:
    """COPY uid vers dst_folder puis EXPUNGE de src_folder. Crée dst_folder si absent."""
    if not src_folder or not dst_folder:
        return False
    if src_folder == dst_folder:
        logger.info(f"[IMAP] move skip — uid={uid} déjà dans {dst_folder!r}")
        return True

    if not await ensure_folder(dst_folder):
        return False

    try:
        conn = _connect()
        try:
            status, _ = conn.select(_q(src_folder))
            if status != "OK":
                logger.error(f"[IMAP_ACTION_FAIL] move SELECT {src_folder!r}: {status}")
                return False
            seq = _seq(uid)
            status, resp = conn.copy(seq, _q(dst_folder))
            if status != "OK":
                msg = b" ".join(resp).decode(errors="replace") if resp else ""
                logger.error(f"[IMAP_ACTION_FAIL] move COPY uid={uid} -> {dst_folder!r}: {status} {msg}")
                return False
            conn.store(seq, "+FLAGS", "\\Deleted")
            conn.expunge()
            logger.info(f"[IMAP] move uid={uid} {src_folder!r} -> {dst_folder!r} OK")
            return True
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"[IMAP_ACTION_FAIL] move uid={uid} {src_folder!r} -> {dst_folder!r}: {e}")
        return False


async def mark_and_move(uid, src_folder: str, dst_folder: str) -> bool:
    """
    Mark \\Seen puis MOVE en une seule connexion IMAP.
    Si MOVE échoue (création dossier impossible, etc.), retombe sur mark_as_read seul.
    Idempotent : si src == dst, ne fait rien et retourne True.
    """
    if not src_folder or not dst_folder:
        return False
    if src_folder == dst_folder:
        logger.info(f"[IMAP] mark_and_move skip — uid={uid} déjà dans {dst_folder!r}")
        return True

    if not await ensure_folder(dst_folder):
        # Fallback : au moins marquer lu dans src
        return await mark_as_read(uid, src_folder)

    try:
        conn = _connect()
        try:
            status, _ = conn.select(_q(src_folder))
            if status != "OK":
                logger.error(f"[IMAP_ACTION_FAIL] mark_and_move SELECT {src_folder!r}: {status}")
                return False
            seq = _seq(uid)
            # 1) Marquer lu (le flag est conservé par COPY)
            conn.store(seq, "+FLAGS", "\\Seen")
            # 2) Copier vers dst
            status, resp = conn.copy(seq, _q(dst_folder))
            if status != "OK":
                msg = b" ".join(resp).decode(errors="replace") if resp else ""
                logger.error(f"[IMAP_ACTION_FAIL] mark_and_move COPY uid={uid} -> {dst_folder!r}: {status} {msg}")
                return False  # Seen est appliqué dans src, pas grave
            # 3) Marquer deleted dans src + expunge
            conn.store(seq, "+FLAGS", "\\Deleted")
            conn.expunge()
            logger.info(f"[IMAP] mark_and_move uid={uid} {src_folder!r} -> {dst_folder!r} OK")
            return True
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"[IMAP_ACTION_FAIL] mark_and_move uid={uid} {src_folder!r} -> {dst_folder!r}: {e}")
        # Fallback best-effort
        try:
            return await mark_as_read(uid, src_folder)
        except Exception:
            return False
