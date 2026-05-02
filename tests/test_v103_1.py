"""Tests V1.0.3.1 — Fix bugs UID + NON + intent read/reply."""
import asyncio
import re
import sys
import sqlite3
import tempfile

sys.path.insert(0, "/root")

from julien_os.telegram.formatting import format_email_list
from julien_os.agents.conversational import (
    parse_pending_id_from_text,
    detect_intent,
    SYSTEM_PROMPT,
    _INSTRUCTIONS_V103_1,
)
from julien_os.tools.email_tools import _format_pending_summary


EMOJI_REGEX = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U0001F1E0-\U0001F1FF"
    "☀-➿"
    "]"
)


def _has_emoji(s: str) -> bool:
    return bool(EMOJI_REGEX.search(s))


def _has_markdown_lourd(s: str) -> bool:
    return ("***" in s) or ("**" in s) or ("•" in s)


# ── 1. format_email_list produit #N au lieu de uid=N (3 modes) ──────────────

def test_format_n_in_scan_mode():
    emails = [
        {"pending_id": 12, "uid": "16", "from": "Mathieu",
         "subject": "Mandat", "priorite": "PRIORITAIRE"},
    ]
    out = format_email_list(emails, mode="scan")
    assert "#12" in out
    assert "uid=" not in out
    assert "uid=16" not in out


def test_format_n_in_actionable_mode():
    emails = [
        {"pending_id": 5, "uid": "99", "from": "Cheryl",
         "subject": "code Airbnb", "snippet": "Bonjour je voudrais le code",
         "priorite": "NORMAL"},
    ]
    out = format_email_list(emails, mode="actionable")
    assert "#5" in out
    assert "uid=" not in out
    assert "« Bonjour" in out  # preview avec guillemets français


def test_format_n_in_synthese_mode():
    data = {
        "now": "2026-05-01T10:00:00",
        "pendings": [
            {"pending_id": 7, "from": "Joh Zark", "subject": "rendez-vous", "age_label": "J+2"},
            {"pending_id": 12, "from": "Mathieu", "subject": "Mandat", "age_label": "nouveau"},
        ],
        "system": {},
    }
    out = format_email_list(data, mode="synthese")
    assert "#7" in out
    assert "#12" in out
    assert "uid=" not in out


# ── 2-3-4. Resolver d'identifiant ────────────────────────────────────────────

def test_parse_pending_id_ouvre_12():
    assert parse_pending_id_from_text("ouvre #12") == 12


def test_parse_pending_id_reponds_5():
    assert parse_pending_id_from_text("réponds à #5") == 5
    assert parse_pending_id_from_text("réponds à 5") == 5  # nombre nu après mot-clé


def test_parse_pending_id_no_number():
    assert parse_pending_id_from_text("ouvre") is None
    assert parse_pending_id_from_text("affiche-moi tout") is None


# ── 5. Cas ambigu : géré par le SYSTEM_PROMPT, vérifié textuellement ─────────

def test_system_prompt_demande_clarif_si_multiple():
    # Le system prompt doit explicitement bannir le « premier pending par défaut »
    assert "demande à Julien" in SYSTEM_PROMPT
    assert "JAMAIS au hasard" in SYSTEM_PROMPT or "jamais au hasard" in SYSTEM_PROMPT.lower()


# ── 6-7. Handler NON vs Hook B (statut DB) ───────────────────────────────────

def _setup_pending(db_path: str):
    """Insère un pending #1 en_attente dans une DB temporaire."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE pending_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            item_id TEXT NOT NULL,
            item_data TEXT NOT NULL,
            options TEXT NOT NULL,
            statut TEXT DEFAULT 'en_attente',
            created_at TEXT,
            expires_at TEXT,
            reponse_choisie TEXT,
            dernier_rappel_at TEXT,
            nb_rappels INTEGER DEFAULT 0
        )
    """)
    conn.execute(
        "INSERT INTO pending_actions (id, source, item_id, item_data, options, statut, reponse_choisie) "
        "VALUES (1, 'protonmail', 'msg-1', '{}', '[]', 'confirme', 'le draft')"
    )
    conn.commit()
    conn.close()


def test_handler_non_remet_en_attente(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending(db_path)
    # Patche le DB_PATH du module pending
    import julien_os.memory.pending as pending_mod
    monkeypatch.setattr(pending_mod, "DB_PATH", db_path)

    asyncio.run(pending_mod.annuler_redaction(1))

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT statut, reponse_choisie FROM pending_actions WHERE id = 1").fetchone()
    conn.close()
    assert row[0] == "en_attente"
    assert row[1] is None


def test_hook_b_bascule_en_ignore(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending(db_path)
    import julien_os.memory.pending as pending_mod
    monkeypatch.setattr(pending_mod, "DB_PATH", db_path)

    asyncio.run(pending_mod.ignorer_pending(1))

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT statut FROM pending_actions WHERE id = 1").fetchone()
    conn.close()
    assert row[0] == "ignore"


# ── 8-9. Intent read vs reply ────────────────────────────────────────────────

def test_intent_read_ne_declenche_pas_reply():
    # detect_intent sur les phrases « lecture » retourne 'read', pas 'reply'
    for s in ["ouvre #12", "lis le détail de #12", "montre-moi #12", "affiche le contenu de #12"]:
        assert detect_intent(s) == "read", f"intent={detect_intent(s)} pour {s!r}"


def test_intent_reply_declenche_reply():
    for s in ["réponds à #12", "rédige une réponse pour #12", "propose une réponse"]:
        assert detect_intent(s) == "reply", f"intent={detect_intent(s)} pour {s!r}"


# ── 10. Aucun emoji ni Markdown lourd dans system prompt + tools ─────────────

def test_no_emoji_no_markdown_in_conversational_outputs():
    # On teste uniquement les CONSIGNES V1.0.3.1 — le profil personnel de Julien
    # peut contenir du Markdown (** etc.) qui ne nous appartient pas.
    assert not _has_emoji(_INSTRUCTIONS_V103_1), "emoji dans _INSTRUCTIONS_V103_1"
    assert not _has_markdown_lourd(_INSTRUCTIONS_V103_1), "markdown lourd dans _INSTRUCTIONS_V103_1"

    # Format pending summary (utilisé par read_emails) — utilise #N et pas d'emoji
    fake_p = {
        "id": 12,
        "item_data": {"from": "Mathieu", "subject": "Mandat", "snippet": "Bonjour"},
    }
    out = _format_pending_summary(fake_p)
    assert "#12" in out
    assert "[12]" not in out
    assert not _has_emoji(out)


# ── 11. Formulation OUI/NON stricte dans le system prompt ────────────────────

def test_system_prompt_demande_oui_non_strict():
    # Le system prompt doit contenir la formulation imposée mot pour mot,
    # sans variante ouverte type « ou tu veux que je modifie ».
    assert "Tape OUI pour envoyer, NON pour annuler." in _INSTRUCTIONS_V103_1
    # Et bannir explicitement les variantes molles connues.
    forbidden = ("ou tu veux que je modifie", "Laquelle veux-tu envoyer")
    for f in forbidden:
        assert f not in _INSTRUCTIONS_V103_1, f"variante molle interdite trouvée : {f!r}"


# ── 12. Flow watcher : bouton 1 → confirme → NON → annuler_redaction ─────────
# Vérifie le vrai chemin DB du flow batch (pas le flow conversationnel).

def _setup_pending_en_attente(db_path: str):
    """Insère un pending #1 en_attente avec 3 options (cas watcher batch)."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE pending_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            item_id TEXT NOT NULL,
            item_data TEXT NOT NULL,
            options TEXT NOT NULL,
            statut TEXT DEFAULT 'en_attente',
            created_at TEXT,
            expires_at TEXT,
            reponse_choisie TEXT,
            dernier_rappel_at TEXT,
            nb_rappels INTEGER DEFAULT 0
        )
    """)
    item = '{"from": "Mathieu", "subject": "Mandat", "uid": "16", "folder": "INBOX"}'
    opts = '["Bonjour Mathieu, accord donn\\u00e9 pour soumettre. Julien.", "(complete)", "Ignorer"]'
    conn.execute(
        "INSERT INTO pending_actions (id, source, item_id, item_data, options, statut, created_at) "
        "VALUES (1, 'protonmail', 'msg-1', ?, ?, 'en_attente', '2026-05-01T10:00:00')",
        (item, opts),
    )
    conn.commit()
    conn.close()


def test_watcher_flow_bouton1_puis_non_remet_en_attente(monkeypatch):
    """Flow batch complet : bouton 1 → confirme → NON → annuler_redaction → en_attente."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending_en_attente(db_path)
    import julien_os.memory.pending as pending_mod
    monkeypatch.setattr(pending_mod, "DB_PATH", db_path)

    # Étape 1 : bouton 1 → confirmer_pending écrit le draft choisi
    asyncio.run(pending_mod.confirmer_pending(1, "Bonjour Mathieu, accord donné. Julien."))
    conn = sqlite3.connect(db_path)
    statut, choisi = conn.execute(
        "SELECT statut, reponse_choisie FROM pending_actions WHERE id = 1"
    ).fetchone()
    conn.close()
    assert statut == "confirme"
    assert choisi == "Bonjour Mathieu, accord donné. Julien."

    # Étape 2 : NON → annuler_redaction repasse en en_attente, vide reponse_choisie
    asyncio.run(pending_mod.annuler_redaction(1))
    conn = sqlite3.connect(db_path)
    statut2, choisi2 = conn.execute(
        "SELECT statut, reponse_choisie FROM pending_actions WHERE id = 1"
    ).fetchone()
    conn.close()
    assert statut2 == "en_attente", f"attendu en_attente, eu {statut2!r}"
    assert choisi2 is None
    # Et SURTOUT pas 'ignore' (c'est ce que faisait le bug pré-V1.0.3.1)
    assert statut2 != "ignore"


# ── 13. Routing handle_validation : free-text → handle_conversation ──────────

class _FakeMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class _FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id


class _FakeUpdate:
    def __init__(self, chat_id, text):
        self.effective_chat = _FakeChat(chat_id)
        self.message = _FakeMessage(text)


class _FakeContext:
    def __init__(self):
        self.bot = object()


def _setup_main_with_pending(monkeypatch, db_path):
    """Patche pending DB et empêche les appels Telegram/Anthropic réels.

    main.py fait `from telegram import Update` (python-telegram-bot) ; depuis le
    CWD /root/julien_os/, le sous-package julien_os.telegram shadow ce module.
    On stub donc sys.modules['telegram'] et 'telegram.ext' AVANT l'import,
    avec juste les attributs dont main.py a besoin pour s'importer.
    """
    import sys
    import types
    if "telegram" not in sys.modules or not hasattr(sys.modules["telegram"], "Update"):
        fake_tg = types.ModuleType("telegram")
        fake_tg.Update = type("Update", (), {})
        sys.modules["telegram"] = fake_tg
    if "telegram.ext" not in sys.modules:
        fake_ext = types.ModuleType("telegram.ext")
        for attr in (
            "ApplicationBuilder", "CommandHandler", "MessageHandler",
            "filters", "ContextTypes",
        ):
            setattr(fake_ext, attr, type(attr, (), {"DEFAULT_TYPE": object}))
        sys.modules["telegram.ext"] = fake_ext

    import julien_os.memory.pending as pending_mod
    monkeypatch.setattr(pending_mod, "DB_PATH", db_path)
    import julien_os.main as main_mod
    # Reset des states module-level entre tests
    main_mod._en_attente_confirmation.clear()
    main_mod._en_attente_custom.clear()
    return main_mod


def test_routing_freetext_avec_pending_actif_returns_false(monkeypatch):
    """« réponds à #12 » avec pending actif → handle_validation return False
    (le message sera routé vers handle_conversation par handle_message)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending_en_attente(db_path)
    main_mod = _setup_main_with_pending(monkeypatch, db_path)

    upd = _FakeUpdate(chat_id=42, text="réponds à #12")
    handled = asyncio.run(main_mod.handle_validation(upd, _FakeContext()))

    assert handled is False, "free-text avec pending actif doit passer à handle_conversation"
    assert upd.message.replies == [], "handle_validation ne doit envoyer aucun reply"


def test_routing_bouton2_active_mode_custom(monkeypatch):
    """Bouton 2 → entre en _en_attente_custom + ask instruction. Aucun appel Anthropic."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending_en_attente(db_path)
    main_mod = _setup_main_with_pending(monkeypatch, db_path)

    # Stub _generer_reponse_custom : ne doit PAS être appelé pour un simple « 2 »
    called = {"flag": False}

    async def _stub_custom(*a, **kw):
        called["flag"] = True
        return "STUB"

    monkeypatch.setattr(main_mod, "_generer_reponse_custom", _stub_custom)

    upd = _FakeUpdate(chat_id=42, text="2")
    handled = asyncio.run(main_mod.handle_validation(upd, _FakeContext()))

    assert handled is True
    assert called["flag"] is False, "bouton 2 ne doit pas appeler _generer_reponse_custom"
    assert 42 in main_mod._en_attente_custom
    assert any("personnalisée" in r.lower() for r in upd.message.replies)


def test_routing_bouton2_puis_freetext_appelle_generer_custom(monkeypatch):
    """Bouton 2 → puis free-text → _generer_reponse_custom appelé, mode custom purgé."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending_en_attente(db_path)
    main_mod = _setup_main_with_pending(monkeypatch, db_path)

    captured = {"args": None}

    async def _stub_custom(instruction, item_data, source):
        captured["args"] = (instruction, source)
        return "Réponse customisée stub."

    monkeypatch.setattr(main_mod, "_generer_reponse_custom", _stub_custom)

    # Étape 1 : bouton 2
    upd1 = _FakeUpdate(chat_id=42, text="2")
    asyncio.run(main_mod.handle_validation(upd1, _FakeContext()))
    assert 42 in main_mod._en_attente_custom

    # Étape 2 : instruction libre
    upd2 = _FakeUpdate(chat_id=42, text="réponse courte, propose un appel demain")
    handled = asyncio.run(main_mod.handle_validation(upd2, _FakeContext()))

    assert handled is True
    assert captured["args"] is not None, "_generer_reponse_custom doit avoir été appelé"
    assert captured["args"][0] == "réponse courte, propose un appel demain"
    assert captured["args"][1] == "protonmail"
    # State custom purgé, state confirmation armé pour OUI/NON
    assert 42 not in main_mod._en_attente_custom
    assert 42 in main_mod._en_attente_confirmation
    # Formulation stricte
    assert any("Tape OUI pour envoyer, NON pour annuler." in r for r in upd2.message.replies)


def test_routing_aucun_pending_freetext_returns_false(monkeypatch):
    """Pas de pending actif + free-text → return False (route vers agent)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    # DB vide (pas de pending)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE pending_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL, item_id TEXT NOT NULL, item_data TEXT NOT NULL,
            options TEXT NOT NULL, statut TEXT DEFAULT 'en_attente',
            created_at TEXT, expires_at TEXT, reponse_choisie TEXT,
            dernier_rappel_at TEXT, nb_rappels INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
    main_mod = _setup_main_with_pending(monkeypatch, db_path)

    upd = _FakeUpdate(chat_id=42, text="raconte-moi une blague")
    handled = asyncio.run(main_mod.handle_validation(upd, _FakeContext()))

    assert handled is False
    assert upd.message.replies == []
