"""Tests V1.0.3 — module julien_os.telegram.formatting."""
import re
import sys

sys.path.insert(0, "/root")

from julien_os.telegram.formatting import format_email_list


# Plages Unicode emoji typiquement utilisées (✅ ❌ ⏰ 📧 etc. ainsi que tous les emojis modernes)
EMOJI_REGEX = re.compile(
    "["
    "\U0001F300-\U0001F5FF"   # symboles & pictographs
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F700-\U0001F77F"   # alchemical
    "\U0001F900-\U0001F9FF"   # supplemental symbols
    "\U0001FA00-\U0001FAFF"   # symbols and pictographs extended-A
    "\U0001F1E0-\U0001F1FF"   # flags
    "☀-➿"           # misc symbols & dingbats (★, ☀, ✅, ⏰…)
    "]"
)


def _has_emoji(s: str) -> bool:
    return bool(EMOJI_REGEX.search(s))


def _has_markdown_lourd(s: str) -> bool:
    return ("***" in s) or ("•" in s)


def test_scan_empty():
    out = format_email_list([], mode="scan")
    assert "À traiter (0)" in out
    assert "aucun" in out
    assert "Auto-classé bruit" not in out
    assert "Scan Proton — 0 non lus" in out
    assert not _has_emoji(out)
    assert not _has_markdown_lourd(out)


def test_scan_8_ignorer_condense():
    emails = (
        [{"uid": str(i), "from": '"Anthropic" <noreply@anthropic.com>',
          "subject": "Newsletter", "priorite": "IGNORER"} for i in range(5)]
        + [{"uid": str(i + 5), "from": '"Cofomo" <noreply@cofomo.com>',
            "subject": "Update", "priorite": "IGNORER"} for i in range(2)]
        + [{"uid": "8", "from": '"GitHub" <noreply@github.com>',
            "subject": "fork notif", "priorite": "IGNORER"}]
    )
    out = format_email_list(emails, mode="scan")
    assert "Scan Proton — 8 non lus" in out
    assert "À traiter (0)" in out
    assert "aucun" in out
    assert "Auto-classé bruit (8)" in out
    assert "Anthropic ×5" in out
    assert "Cofomo ×2" in out
    assert "GitHub ×1" in out
    assert not _has_emoji(out)


def test_scan_top5_avec_overflow():
    # 6 senders distincts → top 5 + "et N autres"
    emails = []
    for i, name in enumerate(["A", "B", "C", "D", "E", "F"]):
        for j in range(2):
            emails.append({
                "uid": f"{i}-{j}",
                "from": f'"{name}" <x@x.com>',
                "subject": "x",
                "priorite": "IGNORER",
            })
    out = format_email_list(emails, mode="scan")
    # 5 premiers + "et 2 autres" (le 6e a 2 occurrences)
    assert "et 2 autres" in out


def test_actionable_avec_preview_tronquee():
    longue = ("Bonjour, je voulais savoir le code d'accès pour entrer dans le "
              "logement ce week-end avec ma famille on arrive samedi vers 16h")
    emails = [
        {"pending_id": 12, "from": '"Cheryl" <c@x.com>',
         "subject": "code d'accès Airbnb",
         "snippet": longue,
         "priorite": "PRIORITAIRE"},
        {"pending_id": 18, "from": '"Janine Daoust" <j@daoust.com>',
         "subject": "ajustement mandat",
         "snippet": "Hello Julien, suite à notre échange j'ai besoin de revoir.",
         "priorite": "NORMAL"},
    ] + [
        {"pending_id": 20 + i, "from": '"Anthropic" <a@a.com>',
         "subject": "x", "priorite": "IGNORER"} for i in range(4)
    ] + [
        {"pending_id": 30 + i, "from": '"GitHub" <g@g.com>',
         "subject": "y", "priorite": "IGNORER"} for i in range(2)
    ]
    out = format_email_list(emails, mode="actionable")
    assert "À traiter (2)" in out
    assert "#12" in out
    assert "Cheryl" in out
    assert "code d'accès Airbnb" in out
    assert "« Bonjour" in out
    assert " »" in out
    assert "..." in out  # preview tronquée
    assert "Auto-classé bruit (6)" in out
    assert "Anthropic ×4" in out
    assert "GitHub ×2" in out
    assert not _has_emoji(out)


def test_synthese_vide_ne_crashe_pas():
    out = format_email_list({}, mode="synthese")
    assert "Synthèse" in out
    assert not _has_emoji(out)
    out2 = format_email_list({"pendings": [], "system": {}}, mode="synthese")
    assert "Synthèse" in out2


def test_synthese_avec_donnees():
    data = {
        "now": "2026-04-30T18:32:00",
        "pendings": [
            {"pending_id": 18, "from": '"Janine Daoust" <j@x.com>',
             "subject": "ajustement mandat", "age_label": "J+1"},
            {"pending_id": 21, "from": '"Mathieu Gaudreault" <m@cofomo.com>',
             "subject": "Cofomo #84519", "age_label": "nouveau"},
        ],
        "last_scan": {
            "at": "2026-04-30T17:00:00",
            "total": 8, "actionable": 0, "bruit": 8,
        },
        "system": {
            "up_since": "2026-04-30T13:31:00",
            "imap_errors_24h": 0,
        },
    }
    out = format_email_list(data, mode="synthese")
    assert "Synthèse — 30 avril 18h32" in out
    assert "Pendings actifs (2)" in out
    assert "#18" in out
    assert "Janine Daoust" in out
    assert "J+1" in out
    assert "nouveau" in out
    assert "Dernier scan" in out
    assert "à 17h00" in out
    assert "8 emails" in out
    assert "0 actionnables" in out
    assert "Système" in out
    assert "30 avril 13h31" in out
    assert "pas d'erreurs IMAP" in out
    assert not _has_emoji(out)


def test_no_emoji_tous_modes():
    samples = [
        ([], "scan"),
        ([{"uid": "1", "from": "x", "subject": "y", "snippet": "z", "priorite": "NORMAL"}], "actionable"),
        ({"pendings": [], "system": {}}, "synthese"),
    ]
    for data, mode in samples:
        out = format_email_list(data, mode=mode)
        assert not _has_emoji(out), f"emoji dans mode={mode}: {out!r}"


def test_no_markdown_lourd_tous_modes():
    samples = [
        ([], "scan"),
        ([{"uid": "1", "from": "x", "subject": "y", "snippet": "z", "priorite": "NORMAL"}], "actionable"),
        ({"pendings": [], "system": {}}, "synthese"),
    ]
    for data, mode in samples:
        out = format_email_list(data, mode=mode)
        assert not _has_markdown_lourd(out), f"markdown lourd dans mode={mode}: {out!r}"
