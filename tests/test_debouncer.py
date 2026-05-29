"""Testes do MessageDebouncer."""

import asyncio
import pytest
from whatsapp_agent_ipnet.debouncer import MessageDebouncer, BufferedMessage, MEDIA_TYPES


@pytest.fixture
def received():
    return []


@pytest.fixture
def debouncer(received):
    async def callback(phone: str, messages: list[BufferedMessage]):
        received.append((phone, messages))

    return MessageDebouncer(debounce_seconds=0.1, callback=callback)


@pytest.mark.asyncio
async def test_single_message_fires_after_delay(debouncer, received):
    await debouncer.add("5511999", "oi")
    assert received == []
    await asyncio.sleep(0.2)
    assert len(received) == 1
    assert received[0][0] == "5511999"
    assert received[0][1][0].text == "oi"


@pytest.mark.asyncio
async def test_multiple_messages_batched(debouncer, received):
    await debouncer.add("5511999", "msg1")
    await asyncio.sleep(0.05)
    await debouncer.add("5511999", "msg2")
    await asyncio.sleep(0.05)
    await debouncer.add("5511999", "msg3")
    await asyncio.sleep(0.2)

    assert len(received) == 1
    assert len(received[0][1]) == 3


@pytest.mark.asyncio
async def test_different_phones_independent(debouncer, received):
    await debouncer.add("111", "msg-a")
    await debouncer.add("222", "msg-b")
    await asyncio.sleep(0.2)

    phones = {r[0] for r in received}
    assert phones == {"111", "222"}


@pytest.mark.asyncio
async def test_media_flushes_immediately(debouncer, received):
    await debouncer.add("5511999", "texto antes")
    await debouncer.add("5511999", "[Imagem]", message_type="image")
    await asyncio.sleep(0.05)

    # Texto pendente + mídia = 2 callbacks imediatos
    assert len(received) == 2
    assert received[0][1][0].text == "texto antes"
    assert received[1][1][0].text == "[Imagem]"


@pytest.mark.asyncio
async def test_flush_forces_immediate_processing(debouncer, received):
    await debouncer.add("5511999", "mensagem")
    assert received == []
    await debouncer.flush("5511999")
    assert len(received) == 1


@pytest.mark.asyncio
async def test_empty_buffer_no_callback(debouncer, received):
    await debouncer.flush("numero-inexistente")
    assert received == []
