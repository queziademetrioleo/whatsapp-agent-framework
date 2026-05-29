"""
Cliente para a Evolution API (WhatsApp).
Documentação: https://doc.evolution-api.com/v2
"""

from __future__ import annotations

import base64
import logging
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    OPEN = "open"
    CLOSE = "close"
    CONNECTING = "connecting"


class QRCodeData(BaseModel):
    code: str
    base64: str


class InstanceInfo(BaseModel):
    instance_name: str
    state: ConnectionState
    qrcode: QRCodeData | None = None


class WebhookEvents(BaseModel):
    messages_upsert: bool = True
    messages_update: bool = False
    messages_delete: bool = False
    send_message: bool = False
    qrcode_updated: bool = True
    connection_update: bool = True


class EvolutionClient:
    """
    Cliente assíncrono para a Evolution API.

    Uso:
        async with EvolutionClient(url, api_key) as client:
            await client.send_text("5511999999999", "Olá!")
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "EvolutionClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"apikey": self.api_key, "Content-Type": "application/json"},
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Use 'async with EvolutionClient(...)' ou chame connect()/disconnect()")
        return self._client

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"apikey": self.api_key, "Content-Type": "application/json"},
            timeout=self.timeout,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ─── Instance ────────────────────────────────────────────────────────────

    async def create_instance(
        self,
        instance_name: str,
        webhook_url: str,
        webhook_events: WebhookEvents | None = None,
        webhook_secret: str | None = None,
    ) -> InstanceInfo:
        """Cria ou recria uma instância WhatsApp com QR code."""
        events = webhook_events or WebhookEvents()
        payload: dict[str, Any] = {
            "instanceName": instance_name,
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True,
            "webhook": {
                "url": webhook_url,
                "base64": False,
                "byEvents": False,
                "enabled": True,
                "events": [
                    k.upper()
                    for k, v in {
                        "MESSAGES_UPSERT": events.messages_upsert,
                        "MESSAGES_UPDATE": events.messages_update,
                        "MESSAGES_DELETE": events.messages_delete,
                        "SEND_MESSAGE": events.send_message,
                        "QRCODE_UPDATED": events.qrcode_updated,
                        "CONNECTION_UPDATE": events.connection_update,
                    }.items()
                    if v
                ],
            },
        }
        if webhook_secret:
            payload["webhook"]["headers"] = {"x-webhook-secret": webhook_secret}

        resp = await self._http.post("/instance/create", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return self._parse_instance_info(instance_name, data)

    async def get_instance_state(self, instance_name: str) -> ConnectionState:
        resp = await self._http.get(f"/instance/connectionState/{instance_name}")
        resp.raise_for_status()
        state = resp.json().get("instance", {}).get("state", "close")
        return ConnectionState(state)

    async def get_qrcode(self, instance_name: str) -> QRCodeData | None:
        """Retorna o QR code atual da instância (None se já conectada)."""
        resp = await self._http.get(f"/instance/connect/{instance_name}")
        resp.raise_for_status()
        data = resp.json()
        qr = data.get("qrcode") or data.get("base64")
        if not qr:
            return None
        if isinstance(qr, dict):
            return QRCodeData(code=qr.get("code", ""), base64=qr.get("base64", ""))
        return QRCodeData(code="", base64=qr)

    async def delete_instance(self, instance_name: str) -> None:
        resp = await self._http.delete(f"/instance/delete/{instance_name}")
        resp.raise_for_status()

    async def logout_instance(self, instance_name: str) -> None:
        resp = await self._http.delete(f"/instance/logout/{instance_name}")
        resp.raise_for_status()

    # ─── Messaging ───────────────────────────────────────────────────────────

    async def send_text(
        self,
        instance_name: str,
        phone: str,
        text: str,
        quoted_message_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Envia mensagem de texto.

        Args:
            instance_name: Nome da instância.
            phone:  Número no formato internacional sem '+', ex: '5511999999999'.
            text:   Texto a enviar (suporta *negrito*, _itálico_, ~tachado~).
            quoted_message_id: ID da mensagem a citar (opcional).
        """
        payload: dict[str, Any] = {
            "number": self._normalize_phone(phone),
            "text": text,
        }
        if quoted_message_id:
            payload["quoted"] = {"key": {"id": quoted_message_id}}

        resp = await self._http.post(f"/message/sendText/{instance_name}", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def send_typing(self, instance_name: str, phone: str, duration_ms: int = 3000) -> None:
        """Exibe o indicador 'digitando...' por N milissegundos."""
        payload = {
            "number": self._normalize_phone(phone),
            "delay": duration_ms,
            "presence": "composing",
        }
        resp = await self._http.post(f"/chat/presence/{instance_name}", json=payload)
        resp.raise_for_status()

    async def mark_as_read(self, instance_name: str, phone: str, message_id: str) -> None:
        payload = {
            "readMessages": [
                {"remoteJid": f"{self._normalize_phone(phone)}@s.whatsapp.net", "id": message_id}
            ]
        }
        resp = await self._http.post(f"/chat/markMessageAsRead/{instance_name}", json=payload)
        resp.raise_for_status()

    # ─── Webhook ─────────────────────────────────────────────────────────────

    async def set_webhook(
        self,
        instance_name: str,
        webhook_url: str,
        events: WebhookEvents | None = None,
        secret: str | None = None,
    ) -> None:
        ev = events or WebhookEvents()
        payload: dict[str, Any] = {
            "url": webhook_url,
            "enabled": True,
            "events": [
                k
                for k, v in {
                    "MESSAGES_UPSERT": ev.messages_upsert,
                    "MESSAGES_UPDATE": ev.messages_update,
                    "MESSAGES_DELETE": ev.messages_delete,
                    "SEND_MESSAGE": ev.send_message,
                    "QRCODE_UPDATED": ev.qrcode_updated,
                    "CONNECTION_UPDATE": ev.connection_update,
                }.items()
                if v
            ],
        }
        if secret:
            payload["headers"] = {"x-webhook-secret": secret}

        resp = await self._http.post(f"/webhook/set/{instance_name}", json=payload)
        resp.raise_for_status()

    # ─── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Remove caracteres não numéricos e garante formato internacional."""
        return "".join(c for c in phone if c.isdigit())

    @staticmethod
    def _parse_instance_info(instance_name: str, data: dict[str, Any]) -> InstanceInfo:
        state_raw = (
            data.get("instance", {}).get("state")
            or data.get("hash", {}).get("state")
            or "close"
        )
        try:
            state = ConnectionState(state_raw)
        except ValueError:
            state = ConnectionState.CLOSE

        qr_data = data.get("qrcode")
        qrcode: QRCodeData | None = None
        if qr_data and isinstance(qr_data, dict):
            qrcode = QRCodeData(
                code=qr_data.get("code", ""),
                base64=qr_data.get("base64", ""),
            )
        return InstanceInfo(instance_name=instance_name, state=state, qrcode=qrcode)

    @staticmethod
    def print_qrcode_terminal(qrcode: QRCodeData) -> None:
        """Imprime o QR code no terminal usando qrcode-terminal (se disponível)."""
        try:
            import qrcode as qr_lib  # type: ignore[import]
            import io

            raw = qrcode.code or base64.b64decode(qrcode.base64).decode()
            qr = qr_lib.QRCode()
            qr.add_data(raw)
            qr.make(fit=True)
            f = io.StringIO()
            qr.print_ascii(out=f)
            print(f.getvalue())
        except ImportError:
            print("[QR Code] Instale 'qrcode' para exibir no terminal: pip install qrcode")
            print(f"[QR Code base64]: {qrcode.base64[:60]}...")
