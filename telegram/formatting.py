"""
V1.0.3 — Mise en forme unifiée des sorties Telegram.

Trois modes :
- scan       : résumé court d'un /forcer_proton ou batch quand peu/pas d'actionnable
- actionable : variante du scan avec preview tronquée pour les emails à traiter
- synthese   : récap consolidé pour /synthese (pendings + dernier scan + système)

Contraintes V1.0.3 :
- Aucun emoji
- Pas de Markdown lourd (***, tables, bullets •)
- Guillemets français « »
- Sortie envoyée à Telegram en parse_mode=None
"""
from datetime import datetime
import re
from collections import Counter

PREVIEW_MAX = 80
SUBJECT_MAX = 60
SENDERS_TOP = 5

_MOIS_FR = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


def _short_sender(raw: str) -> str:
    """Extrait un nom court depuis 'Nom <email>' ou 'email@domain'."""
    if not raw:
        return "?"
    s = raw.strip()
    m = re.match(r'\s*"?([^"<]+?)"?\s*<', s)
    if m:
        name = m.group(1).strip().strip(",")
        if name:
            return name
    if "@" in s:
        local = s.split("<")[-1].split("@")[0].strip("<>")
        return local or s
    return s


def _truncate(text: str, n: int) -> str:
    text = (text or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= n:
        return text
    return text[:n].rstrip() + "..."


def _condense_senders(emails, top: int = SENDERS_TOP) -> str:
    senders = [_short_sender(e.get("from", e.get("sender", ""))) for e in emails]
    cnt = Counter(senders).most_common()
    if not cnt:
        return ""
    if len(cnt) <= top:
        return ", ".join(f"{name} ×{n}" for name, n in cnt)
    head = cnt[:top]
    extra = sum(n for _, n in cnt[top:])
    head_str = ", ".join(f"{name} ×{n}" for name, n in head)
    return f"{head_str}, et {extra} autres"


def _is_actionable(email: dict) -> bool:
    p = (email.get("priorite") or "NORMAL").upper()
    return p != "IGNORER"


def _fmt_dt_short(d) -> str:
    """Format '30 avril 18h32'."""
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d)
        except Exception:
            return d
    return f"{d.day} {_MOIS_FR[d.month - 1]} {d.hour:02d}h{d.minute:02d}"


def _fmt_hhmm(d) -> str:
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d)
        except Exception:
            return d
    return f"{d.hour:02d}h{d.minute:02d}"


def age_label(created_at: str, nb_rappels: int = 0) -> str:
    """Étiquette d'âge pour un pending : 'nouveau', 'J+1', 'J+7', etc."""
    try:
        d = datetime.fromisoformat(created_at)
    except Exception:
        return ""
    delta = datetime.now() - d
    days = int(delta.total_seconds() // 86400)
    if days <= 0:
        return "nouveau"
    return f"J+{days}"


# ── Modes ─────────────────────────────────────────────────────────────────────

def _format_scan(emails, mode: str) -> str:
    actionable = [e for e in emails if _is_actionable(e)]
    bruit = [e for e in emails if not _is_actionable(e)]
    total = len(emails)

    lignes = [f"Scan Proton — {total} non lus", ""]

    lignes.append(f"À traiter ({len(actionable)})")
    if not actionable:
        lignes.append("   aucun")
    else:
        for e in actionable:
            uid = e.get("uid", "?")
            sender = _short_sender(e.get("from", e.get("sender", "")))
            subject = _truncate(e.get("subject", "?"), SUBJECT_MAX)
            lignes.append(f"   uid={uid}  {sender} — {subject}")
            if mode == "actionable":
                snippet_src = e.get("snippet") or e.get("body") or ""
                preview = _truncate(snippet_src, PREVIEW_MAX)
                if preview:
                    lignes.append(f"           « {preview} »")

    if bruit:
        lignes.append("")
        lignes.append(f"Auto-classé bruit ({len(bruit)})")
        lignes.append(f"   {_condense_senders(bruit)}")

    return "\n".join(lignes)


def _format_synthese(data) -> str:
    if not isinstance(data, dict):
        data = {}
    now_raw = data.get("now") or datetime.now()
    lignes = [f"Synthèse — {_fmt_dt_short(now_raw)}", ""]

    pendings = data.get("pendings") or []
    if pendings:
        lignes.append(f"Pendings actifs ({len(pendings)})")
        for p in pendings:
            uid = p.get("uid", "?")
            sender = _short_sender(p.get("from", p.get("sender", "")))
            subject = _truncate(p.get("subject", "?"), SUBJECT_MAX)
            age = p.get("age_label") or ""
            base = f"   uid={uid}  {sender} — {subject}"
            if age:
                lignes.append(f"{base}    {age}")
            else:
                lignes.append(base)
        lignes.append("")

    last_scan = data.get("last_scan")
    if last_scan and last_scan.get("at"):
        try:
            t_str = _fmt_hhmm(last_scan["at"])
        except Exception:
            t_str = "?"
        lignes.append("Dernier scan")
        lignes.append(
            f"   à {t_str}, {last_scan.get('total', 0)} emails, "
            f"{last_scan.get('actionable', 0)} actionnables, "
            f"{last_scan.get('bruit', 0)} bruit auto-classé"
        )
        lignes.append("")

    system = data.get("system") or {}
    if system:
        up_since = system.get("up_since")
        imap_errs = system.get("imap_errors_24h", 0)
        if up_since:
            up_str = _fmt_dt_short(up_since)
            sys_line = f"   bot up depuis {up_str}"
        else:
            sys_line = "   bot up (timestamp inconnu)"
        if imap_errs == 0:
            sys_line += ", pas d'erreurs IMAP"
        else:
            sys_line += f", {imap_errs} erreur(s) IMAP dans les 24h"
        lignes.append("Système")
        lignes.append(sys_line)

    return "\n".join(lignes).rstrip()


# ── API publique ──────────────────────────────────────────────────────────────

def format_email_list(data, mode: str = "scan") -> str:
    """
    mode='scan'       → liste compacte ; preview omise
    mode='actionable' → preview 80 chars sur les emails à traiter
    mode='synthese'   → data est un dict {pendings, last_scan, system, now}
    """
    if mode == "synthese":
        return _format_synthese(data)
    if mode not in ("scan", "actionable"):
        raise ValueError(f"format_email_list: mode inconnu {mode!r}")
    return _format_scan(list(data or []), mode)
