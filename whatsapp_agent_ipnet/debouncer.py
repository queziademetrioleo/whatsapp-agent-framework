"""
Debouncer de mensagens WhatsApp.

Comportamento:
- Mensagens de texto do mesmo número são acumuladas numa janela de N segundos.
- Se o usuário enviar 3 mensagens em 4 segundos, apenas 1 chamada ao agente é feita
  com o texto concatenado das 3 mensagens.
- Mídias (imagem, áudio, vídeo, documento) ignoram o debounce e são processadas imediatamente.
- Cada nova mensagem dentro da janela reseta o timer (padrão sliding window).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class BufferedMessage:
    phone: str
    text: str
    message_id: str
    timestamp: float = field(default_factory=time.monotonic)


# Callback chamado após a janela de debounce expirar
MessageCallback = Callable[[str, list[BufferedMessage]], Awaitable[None]]

# Tipos de mensagem que NÃO são acumuladas (mídia → processamento imediato)
MEDIA_TYPES = frozenset({"image", "audio", "video", "document", "sticker", "ptt"})


class MessageDebouncer:
    """
    Acumulador de mensagens com janela deslizante por número de telefone.

    Args:
        debounce_seconds: Tempo de espera após a última mensagem antes de processar.
        callback:         Função assíncrona chamada com (phone, [BufferedMessage]).
        max_buffer_size:  Limite de mensagens por buffer (proteção contra spam).

    Uso:
        async def handle(phone: str, messages: list[BufferedMessage]):
            full_text = "\\n".join(m.text for m in messages)
            await agent.process(phone, full_text)

        debouncer = MessageDebouncer(debounce_seconds=5.0, callback=handle)
        await debouncer.add("5511999999999", "oi")
        await debouncer.add("5511999999999", "tudo bem?")
        # handle é chamado uma única vez, 5s após a última mensagem, com ambos os textos
    """

    def __init__(
        self,
        debounce_seconds: float,
        callback: MessageCallback,
        max_buffer_size: int = 20,
    ) -> None:
        self.debounce_seconds = debounce_seconds
        self.callback = callback
        self.max_buffer_size = max_buffer_size

        self._buffers: dict[str, list[BufferedMessage]] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._lock = asyncio.Lock()

    async def add(
        self,
        phone: str,
        text: str,
        message_id: str = "",
        message_type: str = "text",
    ) -> None:
        """
        Adiciona uma mensagem ao buffer.

        Mídias pulam o debounce e disparam o callback imediatamente
        (após flush do buffer pendente de texto, se houver).
        """
        msg = BufferedMessage(phone=phone, text=text, message_id=message_id)

        if message_type in MEDIA_TYPES:
            await self._flush_immediate(phone, msg)
            return

        async with self._lock:
            if phone not in self._buffers:
                self._buffers[phone] = []

            buf = self._buffers[phone]
            if len(buf) >= self.max_buffer_size:
                logger.warning("Buffer cheio para %s (%d msgs) — processando agora", phone, len(buf))
                self._cancel_timer(phone)
                await self._fire(phone)

            self._buffers.setdefault(phone, []).append(msg)
            self._reschedule_timer(phone)

    async def flush(self, phone: str) -> None:
        """Força o processamento imediato do buffer de um número."""
        async with self._lock:
            self._cancel_timer(phone)
            if self._buffers.get(phone):
                await self._fire(phone)

    async def flush_all(self) -> None:
        """Força o processamento de todos os buffers pendentes."""
        phones = list(self._buffers.keys())
        for phone in phones:
            await self.flush(phone)

    # ─── Internals ───────────────────────────────────────────────────────────

    def _reschedule_timer(self, phone: str) -> None:
        """Cancela timer existente e agenda novo (janela deslizante)."""
        self._cancel_timer(phone)
        loop = asyncio.get_event_loop()
        self._timers[phone] = loop.call_later(
            self.debounce_seconds,
            lambda: asyncio.ensure_future(self._timer_fire(phone)),
        )

    def _cancel_timer(self, phone: str) -> None:
        timer = self._timers.pop(phone, None)
        if timer:
            timer.cancel()

    async def _timer_fire(self, phone: str) -> None:
        async with self._lock:
            await self._fire(phone)

    async def _fire(self, phone: str) -> None:
        """Drena o buffer e chama o callback. Deve ser chamado com _lock adquirido."""
        messages = self._buffers.pop(phone, [])
        self._timers.pop(phone, None)
        if not messages:
            return

        logger.debug(
            "Debounce expirou para %s — enviando %d mensagem(s) ao agente",
            phone,
            len(messages),
        )
        try:
            await self.callback(phone, messages)
        except Exception:
            logger.exception("Erro no callback do debouncer para %s", phone)

    async def _flush_immediate(self, phone: str, media_msg: BufferedMessage) -> None:
        """Flush do texto pendente + processa mídia imediatamente."""
        async with self._lock:
            self._cancel_timer(phone)
            pending = self._buffers.pop(phone, [])

        if pending:
            logger.debug("Mídia recebida — flushando %d msg(s) de texto pendente(s) de %s", len(pending), phone)
            try:
                await self.callback(phone, pending)
            except Exception:
                logger.exception("Erro no flush de texto pendente para %s", phone)

        logger.debug("Processando mídia imediatamente para %s", phone)
        try:
            await self.callback(phone, [media_msg])
        except Exception:
            logger.exception("Erro no callback de mídia para %s", phone)

    @property
    def pending_phones(self) -> list[str]:
        """Retorna a lista de números com mensagens ainda no buffer."""
        return list(self._buffers.keys())

    def buffer_size(self, phone: str) -> int:
        return len(self._buffers.get(phone, []))
