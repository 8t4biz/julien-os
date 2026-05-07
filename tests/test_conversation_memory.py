"""Tests étape 1 — mémoire conversationnelle Telegram."""
from datetime import datetime, timedelta

from julien_os.memory.conversation import HARD_CAP_MESSAGES, ConversationSession

CHAT = "telegram-chat-1"


def _make_session(tmp_path):
    return ConversationSession(db_path=str(tmp_path / "conv.db"))


def test_new_session_after_4h(tmp_path):
    cs = _make_session(tmp_path)
    cs.add_message(CHAT, "user", "premier message")
    sid_initial = cs.get_or_create_session(CHAT)

    # On force le timestamp du message à T-5h pour franchir la fenêtre 4h.
    five_hours_ago = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
    with cs._conn() as c:
        c.execute(
            "UPDATE conversation_messages SET created_at = ? WHERE chat_id = ?",
            (five_hours_ago, CHAT),
        )
        c.commit()

    sid_apres = cs.get_or_create_session(CHAT)
    assert sid_initial != sid_apres


def test_session_continues_within_4h(tmp_path):
    cs = _make_session(tmp_path)
    cs.add_message(CHAT, "user", "msg1")
    cs.add_message(CHAT, "assistant", "rep1")
    cs.add_message(CHAT, "user", "msg2")

    with cs._conn() as c:
        cur = c.execute(
            "SELECT DISTINCT session_id FROM conversation_messages WHERE chat_id = ?",
            (CHAT,),
        )
        sessions = {row[0] for row in cur.fetchall()}

    assert len(sessions) == 1


def test_reset_forces_new_session(tmp_path):
    cs = _make_session(tmp_path)
    cs.add_message(CHAT, "user", "avant reset")
    sid_avant = cs.get_or_create_session(CHAT)

    cs.reset(CHAT)
    cs.add_message(CHAT, "user", "apres reset")
    sid_apres = cs.get_or_create_session(CHAT)

    assert sid_avant != sid_apres


def test_hard_cap_at_20_messages(tmp_path):
    cs = _make_session(tmp_path)
    for i in range(25):
        cs.add_message(CHAT, "user", f"msg{i:02d}")

    msgs = cs.get_messages(CHAT)
    assert len(msgs) == HARD_CAP_MESSAGES == 20
    # Les 20 plus récents, dans l'ordre chronologique : msg05..msg24
    assert msgs[0]["content"] == "msg05"
    assert msgs[-1]["content"] == "msg24"


def test_anthropic_format_output(tmp_path):
    cs = _make_session(tmp_path)
    cs.add_message(CHAT, "user", "bonjour")
    cs.add_message(CHAT, "assistant", [{"type": "text", "text": "salut"}])

    msgs = cs.get_messages(CHAT)

    assert isinstance(msgs, list) and len(msgs) == 2
    for m in msgs:
        assert set(m.keys()) >= {"role", "content"}
        assert m["role"] in ("user", "assistant", "tool")

    assert msgs[0] == {"role": "user", "content": "bonjour"}
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == [{"type": "text", "text": "salut"}]
