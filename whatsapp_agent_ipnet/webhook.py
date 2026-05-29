"""
Servidor de webhook FastAPI para receber eventos da Evolution API.

Eventos tratados:
  - MESSAGES_UPSERT   → mensagem recebida → debouncer → agente
  - QRCODE_UPDATED    → novo QR code disponível → log/callback
  - CONNECTION_UPDATE → mudança de estado da conexão → log/callback
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Callable, Awaitable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field

from whatsapp_agent_ipnet.debouncer import MessageDebouncer

logger = logging.getLogger(__name__)

# ─── Modelos de payload da Evolution API ────────────────────────────────────


class MessageKey(BaseModel):
    id: str = ""
    remoteJid: str = ""
    fromMe: bool = False


class MessageContent(BaseModel):
    conversation: str | None = None
    extendedTextMessage: dict[str, Any] | None = None
    imageMessage: dict[str, Any] | None = None
    audioMessage: dict[str, Any] | None = None
    videoMessage: dict[str, Any] | None = None
    documentMessage: dict[str, Any] | None = None
    stickerMessage: dict[str, Any] | None = None
    pttMessage: dict[str, Any] | None = None


class MessageData(BaseModel):
    key: MessageKey = Field(default_factory=MessageKey)
    message: MessageContent | None = None
    messageType: str = "conversation"
    pushName: str | None = None


class EvolutionWebhookPayload(BaseModel):
    event: str
    instance: str
    data: dict[str, Any] = Field(default_factory=dict)
    destination: str = ""
    date_time: str = ""
    server_url: str = ""
    apikey: str = ""


# ─── Callbacks opcionais do usuário ──────────────────────────────────────────

QRCodeCallback = Callable[[str, str], Awaitable[None]]  # (instance_name, base64_qr)
ConnectionCallback = Callable[[str, str], Awaitable[None]]  # (instance_name, state)


# ─── Router ──────────────────────────────────────────────────────────────────


def create_webhook_router(
    debouncer: MessageDebouncer,
    webhook_secret: str | None = None,
    on_qrcode: QRCodeCallback | None = None,
    on_connection_change: ConnectionCallback | None = None,
) -> APIRouter:
    """
    Cria e retorna um APIRouter FastAPI com os endpoints de webhook.

    Args:
        debouncer:            Instância do MessageDebouncer.
        webhook_secret:       Se definido, valida o header 'x-webhook-secret'.
        on_qrcode:            Callback chamado quando um novo QR code é gerado.
        on_connection_change: Callback chamado quando o estado de conexão muda.
    """
    router = APIRouter(prefix="/webhook", tags=["webhook"])

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/{instance_name}")
    async def receive_event(
        instance_name: str,
        request: Request,
        background: BackgroundTasks,
    ) -> Response:
        # Validação de secret (opcional)
        if webhook_secret:
            incoming_secret = request.headers.get("x-webhook-secret", "")
            if not hmac.compare_digest(incoming_secret, webhook_secret):
                raise HTTPException(status_code=401, detail="Invalid webhook secret")

        body = await request.json()
        payload = EvolutionWebhookPayload.model_validate(body)

        logger.debug("Webhook recebido: event=%s instance=%s", payload.event, payload.instance)

        match payload.event:
            case "messages.upsert":
                background.add_task(_handle_message, payload, debouncer)
            case "qrcode.updated":
                background.add_task(_handle_qrcode, payload, on_qrcode)
            case "connection.update":
                background.add_task(_handle_connection, payload, on_connection_change)
            case _:
                logger.debug("Evento ignorado: %s", payload.event)

        return Response(status_code=200)

    return router


# ─── Handlers internos ───────────────────────────────────────────────────────


async def _handle_message(
    payload: EvolutionWebhookPayload,
    debouncer: MessageDebouncer,
) -> None:
    """Extrai texto/mídia da mensagem e entrega ao debouncer."""
    data = payload.data
    key = data.get("key", {})

    # Ignorar mensagens enviadas pelo próprio agente
    if key.get("fromMe", False):
        return

    remote_jid: str = key.get("remoteJid", "")
    if not remote_jid or "status@broadcast" in remote_jid:
        return

    # Extrair número limpo (remover @s.whatsapp.net ou @g.us para grupos)
    phone = remote_jid.split("@")[0]

    message_id: str = key.get("id", "")
    message_type: str = data.get("messageType", "conversation")

    msg_content = data.get("message", {}) or {}
    text = _extract_text(msg_content, message_type)

    if not text:
        logger.debug("Mensagem sem texto extraível de %s (tipo: %s)", phone, message_type)
        return

    logger.info("Mensagem de %s [%s]: %s", phone, message_type, text[:80])
    await debouncer.add(
        phone=phone,
        text=text,
        message_id=message_id,
        message_type=_normalize_type(message_type),
    )


async def _handle_qrcode(
    payload: EvolutionWebhookPayload,
    callback: QRCodeCallback | None,
) -> None:
    qr_data = payload.data.get("qrcode", {})
    base64_qr = qr_data.get("base64", "") if isinstance(qr_data, dict) else str(qr_data)
    logger.info("Novo QR code para instância %s", payload.instance)
    if callback:
        await callback(payload.instance, base64_qr)


async def _handle_connection(
    payload: EvolutionWebhookPayload,
    callback: ConnectionCallback | None,
) -> None:
    state = payload.data.get("state", "unknown")
    logger.info("Conexão da instância %s mudou para: %s", payload.instance, state)
    if callback:
        await callback(payload.instance, state)


# ─── Utilitários ─────────────────────────────────────────────────────────────


def _extract_text(message: dict[str, Any], message_type: str) -> str:
    """Extrai o texto legível de um payload de mensagem da Evolution API."""
    # Texto simples
    if text := message.get("conversation"):
        return text

    # Texto estendido (links, formatação)
    if ext := message.get("extendedTextMessage"):
        return ext.get("text", "")

    # Legenda de mídia
    for media_key in ("imageMessage", "videoMessage", "documentMessage"):
        if media := message.get(media_key):
            caption = media.get("caption", "")
            if caption:
                return f"[{media_key.replace('Message', '')}] {caption}"
            return f"[{media_key.replace('Message', '')}]"

    if message.get("audioMessage") or message.get("pttMessage"):
        return "[Áudio]"

    if message.get("stickerMessage"):
        return "[Sticker]"

    return ""


_TYPE_MAP = {
    "conversation": "text",
    "extendedTextMessage": "text",
    "imageMessage": "image",
    "audioMessage": "audio",
    "videoMessage": "video",
    "documentMessage": "document",
    "stickerMessage": "sticker",
    "pttMessage": "ptt",
}


def _normalize_type(raw: str) -> str:
    return _TYPE_MAP.get(raw, "text")
