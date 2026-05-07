"""Tests V1.0.3.2 — Friction 8 : collision /mails vs pending validation.

Reproduit le scénario du 1er mai 2026 et vérifie qu'il ne peut plus se produire :
- /mails capture sa propre liste numérotée
- "1" après /mails route vers handle_conversation avec l'email sélectionné en
  contexte explicite, JAMAIS vers get_pending_actif()
- /reset purge les états RAM (pas seulement la session conversationnelle)
"""
import asyncio
import sqlite3
import sys
import tempfile
import time
import types

sys.path.insert(0, "/root")


# ── Stubs telegram pour pouvoir importer julien_os.main ─────────────────────

def _stub_telegram_modules():
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


# ── Fakes Telegram Update ────────────────────────────────────────────────────

class _FakeMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class _FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id


class _FakeBot:
    async def send_chat_action(self, **kw):
        pass


class _FakeUpdate:
    def __init__(self, chat_id, text):
        self.effective_chat = _FakeChat(chat_id)
        self.message = _FakeMessage(text)


class _FakeContext:
    def __init__(self):
        self.bot = _FakeBot()


# ── Setup commun ─────────────────────────────────────────────────────────────

def _setup_pending_cofomo(db_path: str):
    """Reproduit l'état DB du jour de Friction 8 : un pending Cofomo en_attente."""
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
    item = (
        '{"from": "\\"Mathieu Gaudreault\\" <mathieu.gaudreault@cofomo.com>", '
        '"subject": "RE: Mandat #84519 (exclusivité)", "uid": "16", "folder": "INBOX"}'
    )
    opts = (
        '["Bonjour Mathieu, accord donn\\u00e9 pour soumettre. Julien.", '
        '"(complete Cofomo)", "Ignorer / Traiter plus tard"]'
    )
    conn.execute(
        "INSERT INTO pending_actions (id, source, item_id, item_data, options, statut, created_at) "
        "VALUES (12, 'protonmail', 'msg-cofomo', ?, ?, 'en_attente', '2026-04-30T20:55:50')",
        (item, opts),
    )
    conn.commit()
    conn.close()


def _load_main(monkeypatch, db_path):
    _stub_telegram_modules()
    import julien_os.memory.pending as pending_mod
    monkeypatch.setattr(pending_mod, "DB_PATH", db_path)
    import julien_os.main as main_mod
    main_mod._en_attente_confirmation.clear()
    main_mod._en_attente_custom.clear()
    main_mod._mails_selection.clear()
    return main_mod


# ── 1. Le bug Friction 8 : reproductible AVANT V1.0.3.2 ──────────────────────
# Vérifié dans le diff git, pas dans les tests (le bug a été corrigé).


# ── 2. /mails capture la liste, "1" sélectionne CET email pas le pending ────

def test_mails_selection_capture_la_liste(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending_cofomo(db_path)
    main_mod = _load_main(monkeypatch, db_path)

    # Simule /mails ayant capturé une liste airbnb
    main_mod._mails_selection[42] = {
        "emails": [
            {"from": "Airbnb <noreply@airbnb.com>", "subject": "Réservation confirmée",
             "date": "1 mai 2026, 14:00", "unread": True, "uid": "999"},
        ],
        "expires_at": time.time() + 300,
    }

    # Stub handle_conversation pour vérifier ce qu'on lui passe en contexte
    captured = {"prompt": None}

    async def _stub_conv(chat_id, message, db_path=None):
        captured["prompt"] = message
        return "Email Airbnb sélectionné, que veux-tu faire ?"

    monkeypatch.setattr(main_mod, "handle_conversation", _stub_conv)

    upd = _FakeUpdate(chat_id=42, text="1")
    handled = asyncio.run(main_mod.handle_validation(upd, _FakeContext()))

    assert handled is True
    # L'agent a bien reçu le contexte du mail Airbnb sélectionné, PAS Cofomo
    assert captured["prompt"] is not None
    assert "Airbnb" in captured["prompt"]
    assert "Cofomo" not in captured["prompt"]
    assert "Mathieu" not in captured["prompt"]
    assert "[Sélection /mails — index 1]" in captured["prompt"]
    # La liste a été consommée
    assert 42 not in main_mod._mails_selection


def test_mails_selection_priorite_sur_pending_cofomo(monkeypatch):
    """Le test cœur de Friction 8 : un pending Cofomo en DB ne doit PAS
    polluer la sélection numérique d'une liste /mails affichée juste avant."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending_cofomo(db_path)  # pending #12 Cofomo en_attente
    main_mod = _load_main(monkeypatch, db_path)

    # /mails vient d'afficher 5 emails, dont un Airbnb en position 1
    main_mod._mails_selection[42] = {
        "emails": [
            {"from": "Airbnb", "subject": "Code accès", "date": "1 mai", "unread": True, "uid": "9001"},
            {"from": "Stripe", "subject": "Reçu", "date": "1 mai", "unread": False, "uid": "9000"},
        ],
        "expires_at": time.time() + 300,
    }

    captured = {"prompt": None}

    async def _stub_conv(chat_id, message, db_path=None):
        captured["prompt"] = message
        return "OK"

    monkeypatch.setattr(main_mod, "handle_conversation", _stub_conv)

    upd = _FakeUpdate(chat_id=42, text="1")
    handled = asyncio.run(main_mod.handle_validation(upd, _FakeContext()))

    assert handled is True
    # AUCUNE référence Cofomo malgré le pending #12 actif en DB
    assert "Cofomo" not in captured["prompt"]
    assert "Mathieu" not in captured["prompt"]
    assert "84519" not in captured["prompt"]
    # En revanche, l'email Airbnb sélectionné est bien là
    assert "Airbnb" in captured["prompt"]
    assert "Code accès" in captured["prompt"]
    # Aucun draft d'envoi n'a été armé
    assert 42 not in main_mod._en_attente_confirmation


def test_mails_selection_index_hors_limites(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending_cofomo(db_path)
    main_mod = _load_main(monkeypatch, db_path)

    main_mod._mails_selection[42] = {
        "emails": [{"from": "X", "subject": "Y", "date": "z", "unread": False, "uid": "1"}],
        "expires_at": time.time() + 300,
    }
    captured = {"called": False}

    async def _stub_conv(*a, **kw):
        captured["called"] = True
        return "ne devrait pas être appelé"

    monkeypatch.setattr(main_mod, "handle_conversation", _stub_conv)

    upd = _FakeUpdate(chat_id=42, text="3")
    handled = asyncio.run(main_mod.handle_validation(upd, _FakeContext()))

    assert handled is True
    assert captured["called"] is False
    assert any("hors limites" in r for r in upd.message.replies)


def test_mails_selection_ttl_expire(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending_cofomo(db_path)
    main_mod = _load_main(monkeypatch, db_path)

    # Selection expirée il y a 1 seconde
    main_mod._mails_selection[42] = {
        "emails": [{"from": "X", "subject": "Y", "date": "z", "unread": False, "uid": "1"}],
        "expires_at": time.time() - 1,
    }

    captured = {"called": False}

    async def _stub_conv(*a, **kw):
        captured["called"] = True
        return "ne devrait pas être appelé"

    monkeypatch.setattr(main_mod, "handle_conversation", _stub_conv)

    upd = _FakeUpdate(chat_id=42, text="1")
    handled = asyncio.run(main_mod.handle_validation(upd, _FakeContext()))

    # Selection expirée → purgée et "1" retombe dans le flow pending normal
    # (qui à son tour traite "1" comme bouton 1 sur le pending Cofomo).
    # On ne pousse pas l'agent. Le chat_id ne doit plus être dans _mails_selection.
    assert 42 not in main_mod._mails_selection
    assert captured["called"] is False
    # Le flow pending classique a pris le relais → texte_choisi = options[0] de #12
    # → state confirmation armé
    assert handled is True
    assert 42 in main_mod._en_attente_confirmation


# ── 3. /reset purge les états RAM ────────────────────────────────────────────

def test_reset_purge_etats_ram(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending_cofomo(db_path)
    main_mod = _load_main(monkeypatch, db_path)

    # Pollue les 3 états
    main_mod._en_attente_confirmation[42] = {"pending_id": 12, "texte": "draft Cofomo", "source": "protonmail", "item_data": {}}
    main_mod._en_attente_custom[42] = {"pending_id": 12, "source": "protonmail", "item_data": {}}
    main_mod._mails_selection[42] = {"emails": [], "expires_at": time.time() + 300}

    upd = _FakeUpdate(chat_id=42, text="/reset")
    asyncio.run(main_mod.cmd_reset(upd, _FakeContext()))

    assert 42 not in main_mod._en_attente_confirmation, "confirmation pas purgée"
    assert 42 not in main_mod._en_attente_custom, "mode custom pas purgé"
    assert 42 not in main_mod._mails_selection, "selection /mails pas purgée"
    # Le message de retour mentionne ce qui a été purgé
    full_reply = " ".join(upd.message.replies)
    assert "purgés" in full_reply.lower() or "purgé" in full_reply.lower()


def test_reset_idempotent_si_etats_vides(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending_cofomo(db_path)
    main_mod = _load_main(monkeypatch, db_path)

    upd = _FakeUpdate(chat_id=42, text="/reset")
    asyncio.run(main_mod.cmd_reset(upd, _FakeContext()))

    # Aucune erreur, juste un message neutre
    assert upd.message.replies == ["Session réinitialisée."]


# ── 4. Non-régression V1.0.3.1 : sans /mails actif, "1" reste pending flow ──

def test_sans_mails_selection_le_1_garde_lancien_comportement_pending(monkeypatch):
    """V1.0.3.1 : si pas de /mails actif et un pending existe, "1" pioche
    options[0] du pending — comportement existant à conserver."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    _setup_pending_cofomo(db_path)
    main_mod = _load_main(monkeypatch, db_path)

    # Pas de _mails_selection
    upd = _FakeUpdate(chat_id=42, text="1")
    handled = asyncio.run(main_mod.handle_validation(upd, _FakeContext()))

    assert handled is True
    # Le pending Cofomo est armé pour OUI/NON (comportement V1.0.3.1)
    assert 42 in main_mod._en_attente_confirmation
    state = main_mod._en_attente_confirmation[42]
    assert state["pending_id"] == 12
    # Et la formulation OUI/NON stricte est dans la réponse
    assert any("Tape OUI pour envoyer, NON pour annuler." in r for r in upd.message.replies)
