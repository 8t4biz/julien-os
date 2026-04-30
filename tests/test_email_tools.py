"""Tests étape 2.5 — wrappers email Anthropic en async natif."""
from unittest.mock import patch, AsyncMock

import pytest

from julien_os.tools import execute_tool, ALL_TOOLS, ALL_HANDLERS  # noqa: F401
from julien_os.tools.email_tools import (
    execute_read_emails,
    execute_get_email_details,
    execute_send_email_reply,
)

# Tous les tests de ce module sont async — pytest-asyncio activé via marker module-level.
pytestmark = pytest.mark.asyncio


def _make_pending(pid, sender, subject="Sujet test", body="corps de test"):
    return {
        "id": pid,
        "source": "protonmail",
        "item_id": f"msg-{pid}@example.com",
        "item_data": {
            "id": f"msg-{pid}@example.com",
            "uid": str(pid + 100),
            "folder": "INBOX",
            "from": sender,
            "subject": subject,
            "date": "Mon, 27 Apr 2026 10:00:00 +0000",
            "snippet": body[:200],
            "body": body,
        },
        "options": ["opt courte", "opt complete", "ignorer"],
        "statut": "en_attente",
        "created_at": "2026-04-27T10:00:00",
    }


async def test_read_emails_returns_string():
    pendings = [
        _make_pending(1, '"Alice" <alice@example.com>', subject="Demande facture"),
        _make_pending(2, '"Bob" <bob@example.com>'),
    ]
    with patch(
        "julien_os.tools.email_tools._fetch_pendings",
        new=AsyncMock(return_value=pendings),
    ):
        result = await execute_read_emails(limit=10)
    assert isinstance(result, str) and result
    assert "[1]" in result and "Alice" in result
    assert "[2]" in result and "Bob" in result


async def test_sender_filter_works():
    pendings = [
        _make_pending(1, '"Zohra" <zohra@example.com>'),
        _make_pending(2, '"Alice" <alice@example.com>'),
        _make_pending(3, '"zohra-amie" <zohra2@example.com>'),
    ]
    with patch(
        "julien_os.tools.email_tools._fetch_pendings",
        new=AsyncMock(return_value=pendings),
    ):
        result = await execute_read_emails(limit=10, sender_filter="zohra")
    assert "Zohra" in result
    assert "zohra2@example.com" in result
    assert "Alice" not in result
    assert "alice@example.com" not in result


async def test_get_email_details_invalid_id():
    with patch(
        "julien_os.tools.email_tools._fetch_pending_by_pending_id",
        return_value=None,
    ):
        result = await execute_get_email_details("9999")
    assert isinstance(result, str)
    assert "introuvable" in result.lower() or "erreur" in result.lower()


async def test_send_blocks_noreply():
    """Critique : aucun appel SMTP ne doit partir vers une adresse no-reply."""
    pending_noreply = _make_pending(42, '"Airbnb" <automated@airbnb.com>')
    with patch(
        "julien_os.tools.email_tools._fetch_pending_by_pending_id",
        return_value=pending_noreply,
    ), patch(
        "julien_os.tools.email_tools._send_smtp_reply",
        new_callable=AsyncMock,
    ) as mock_send:
        result = await execute_send_email_reply(email_id="42", body="ne devrait pas partir")
    assert ("no-reply" in result.lower()) or ("bloqué" in result.lower())
    mock_send.assert_not_called()


async def test_execute_tool_unknown_handler():
    result = await execute_tool("inexistant", {})
    assert isinstance(result, str)
    assert ("inconnu" in result.lower()) or ("erreur" in result.lower())
