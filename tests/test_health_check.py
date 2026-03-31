import pytest


@pytest.mark.asyncio
async def test_health_endpoint(unauthed_client):
    r = await unauthed_client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "arlo-assistant"
