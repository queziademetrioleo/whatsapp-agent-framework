"""Testes do webhook FastAPI."""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from whatsapp_agent_ipnet.debouncer import BufferedMessage, MessageDebouncer
from whatsapp_agent_ipnet.webhook import create_webhook_router


@pytest.fixture
def received():
    return []


@pytest.fixture
def app(received):
    async def callback(phone: str, messages: list[BufferedMessage]):
        received.append((phone, messages))

    debouncer = MessageDebouncer(debounce_seconds=0.05, callback=callback)
    router = create_webhook_router(debouncer=debouncer)

    fast_app = FastAPI()
    fast_app.include_router(router)
    return fast_app


def test_health_endpoint(app):
    client = TestClient(app)
    resp = client.get("/webhook/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_message_upsert_event(app, received):
    client = TestClient(app)
    payload = {
        "event": "messages.upsert",
        "instance": "test",
        "data": {
            "key": {
                "id": "msg-1",
                "remoteJid": "5511999999999@s.whatsapp.net",
                "fromMe": False,
            },
            "messageType": "conversation",
            "message": {"conversation": "olá agente"},
        },
    }
    resp = client.post("/webhook/test", json=payload)
    assert resp.status_code == 200


def test_own_messages_ignored(app, received):
    client = TestClient(app)
    payload = {
        "event": "messages.upsert",
        "instance": "test",
        "data": {
            "key": {
                "id": "msg-2",
                "remoteJid": "5511999999999@s.whatsapp.net",
                "fromMe": True,  # ← mensagem enviada pelo próprio agente
            },
            "messageType": "conversation",
            "message": {"conversation": "resposta do agente"},
        },
    }
    resp = client.post("/webhook/test", json=payload)
    assert resp.status_code == 200
    # Buffer deve continuar vazio
    import asyncio
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.1))
    assert received == []


def test_webhook_secret_validation():
    async def cb(phone, msgs):
        pass

    debouncer = MessageDebouncer(debounce_seconds=1, callback=cb)
    router = create_webhook_router(debouncer=debouncer, webhook_secret="meu-secret")
    fast_app = FastAPI()
    fast_app.include_router(router)
    client = TestClient(fast_app, raise_server_exceptions=False)

    resp = client.post(
        "/webhook/test",
        json={"event": "connection.update", "instance": "test", "data": {}},
        headers={"x-webhook-secret": "wrong-secret"},
    )
    assert resp.status_code == 401


def test_unknown_event_ignored(app):
    client = TestClient(app)
    resp = client.post(
        "/webhook/test",
        json={"event": "some.unknown.event", "instance": "test", "data": {}},
    )
    assert resp.status_code == 200
