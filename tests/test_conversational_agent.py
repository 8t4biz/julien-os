"""Tests étape 3 — agent conversationnel V1."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ── Helpers de construction de réponses Anthropic mockées ─────────────────────


def _text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    block.model_dump = MagicMock(return_value={"type": "text", "text": text})
    return block


def _tool_use_block(name, input_data, block_id="toolu_test"):
    block = MagicMock()
    block.type = "tool_use"
    block.id = block_id
    block.name = name
    block.input = input_data
    block.model_dump = MagicMock(
        return_value={"type": "tool_use", "id": block_id, "name": name, "input": input_data}
    )
    return block


def _make_response(content_blocks, stop_reason, input_tokens=100, output_tokens=20):
    response = MagicMock()
    response.stop_reason = stop_reason
    response.content = content_blocks
    response.model = "claude-sonnet-4-5"
    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


def _mock_client(*responses):
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=list(responses))
    return client


# ── Tests ────────────────────────────────────────────────────────────────────


async def test_simple_text_response(tmp_path):
    from julien_os.agents.conversational import handle_conversation

    response = _make_response([_text_block("Bonjour Julien")], stop_reason="end_turn")
    client = _mock_client(response)

    db = str(tmp_path / "conv.db")
    with patch("julien_os.agents.conversational._get_client", return_value=client):
        result = await handle_conversation("chat-test-1", "salut", db_path=db)

    assert result == "Bonjour Julien"
    assert client.messages.create.await_count == 1


async def test_tool_use_loop(tmp_path):
    from julien_os.agents.conversational import handle_conversation

    tool_block = _tool_use_block("read_emails", {"limit": 5})
    response_tool = _make_response([tool_block], stop_reason="tool_use")
    response_final = _make_response([_text_block("Voici tes emails")], stop_reason="end_turn")
    client = _mock_client(response_tool, response_final)

    db = str(tmp_path / "conv.db")
    with patch("julien_os.agents.conversational._get_client", return_value=client), patch(
        "julien_os.agents.conversational.execute_tool",
        new_callable=AsyncMock,
        return_value="1 email de Zohra",
    ) as mock_exec:
        result = await handle_conversation("chat-test-2", "lis mes emails", db_path=db)

    assert result == "Voici tes emails"
    mock_exec.assert_awaited_once_with("read_emails", {"limit": 5})
    assert client.messages.create.await_count == 2


async def test_max_iterations_safeguard(tmp_path):
    from julien_os.agents.conversational import handle_conversation

    # Toujours retourner tool_use → la boucle doit s'arrêter à 5 itérations.
    infinite_tool_responses = [
        _make_response(
            [_tool_use_block("read_emails", {"limit": 1}, block_id=f"toolu_{i}")],
            stop_reason="tool_use",
        )
        for i in range(10)
    ]
    client = _mock_client(*infinite_tool_responses)

    db = str(tmp_path / "conv.db")
    with patch("julien_os.agents.conversational._get_client", return_value=client), patch(
        "julien_os.agents.conversational.execute_tool",
        new_callable=AsyncMock,
        return_value="ok",
    ):
        result = await handle_conversation("chat-test-3", "boucle infinie", db_path=db)

    assert ("5 itérations" in result) or ("dépassé" in result.lower())
    assert client.messages.create.await_count == 5


async def test_session_context_preserved(tmp_path):
    from julien_os.agents.conversational import handle_conversation

    response_a = _make_response([_text_block("Salut Julien")], stop_reason="end_turn")
    response_b = _make_response([_text_block("Oui je me souviens")], stop_reason="end_turn")
    client = _mock_client(response_a, response_b)

    db = str(tmp_path / "conv.db")
    with patch("julien_os.agents.conversational._get_client", return_value=client):
        await handle_conversation("chat-mem", "salut", db_path=db)
        await handle_conversation("chat-mem", "tu te souviens ?", db_path=db)

    second_call_kwargs = client.messages.create.await_args_list[1].kwargs
    second_messages = second_call_kwargs["messages"]

    user_contents = [m["content"] for m in second_messages if m["role"] == "user"]
    assert "salut" in user_contents
    assert "tu te souviens ?" in user_contents

    # Le tour précédent doit avoir laissé un message assistant en mémoire.
    assistant_messages = [m for m in second_messages if m["role"] == "assistant"]
    assert len(assistant_messages) >= 1
