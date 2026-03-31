import pytest


@pytest.mark.asyncio
async def test_send_message_returns_thinking(client):
    """Sending a message should return immediately with status 'thinking'."""
    r = await client.post("/chat/message", json={"text": "Hello Arlo"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "thinking"
    assert data["message_id"] is not None
    assert data["conversation_id"] is not None
    assert data["content"] == ""


@pytest.mark.asyncio
async def test_send_message_creates_conversation(client):
    """First message should create a new conversation."""
    r = await client.post("/chat/message", json={"text": "Start a new chat"})
    data = r.json()
    conv_id = data["conversation_id"]

    # Conversation should exist
    r2 = await client.get(f"/chat/conversations/{conv_id}")
    assert r2.status_code == 200
    messages = r2.json()["messages"]
    # Should have at least the user message and the thinking assistant message
    assert len(messages) >= 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Start a new chat"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["status"] == "thinking"


@pytest.mark.asyncio
async def test_send_message_to_existing_conversation(client):
    """Sending with a conversation_id should add to that thread."""
    r1 = await client.post("/chat/message", json={"text": "First message"})
    conv_id = r1.json()["conversation_id"]

    r2 = await client.post("/chat/message", json={
        "text": "Second message",
        "conversation_id": conv_id,
    })
    assert r2.json()["conversation_id"] == conv_id


@pytest.mark.asyncio
async def test_get_message_not_found(client):
    r = await client.get("/chat/message/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_conversations(client):
    # Create a conversation
    await client.post("/chat/message", json={"text": "Test conversation"})

    r = await client.get("/chat/conversations")
    assert r.status_code == 200
    assert r.json()["count"] >= 1


@pytest.mark.asyncio
async def test_send_message_empty_text_rejected(client):
    r = await client.post("/chat/message", json={"text": ""})
    assert r.status_code == 422
