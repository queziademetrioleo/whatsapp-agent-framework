"""
Memória de sessão ativa usando Redis.

Armazena contexto quente da conversa em andamento:
- Estado da sessão (ativa, aguardando, etc.)
- Metadados do usuário (nome, preferências)
- Flag de "agente processando" para evitar respostas duplicadas

TTL configurável (padrão 1h). Após expirar, a sessão é recriada do histórico Postgres.
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any

import redis.asyncio as aioredis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SessionState(str, Enum):
    ACTIVE = "active"
    PROCESSING = "processing"  # agente está gerando resposta
    WAITING = "waiting"        # aguardando input do usuário


class SessionData(BaseModel):
    phone: str
    state: SessionState = SessionState.ACTIVE
    user_name: str | None = None
    metadata: dict[str, Any] = {}
    message_count: int = 0


class SessionMemory:
    """
    Cache de sessão por número de telefone usando Redis.

    Args:
        redis_url: URL de conexão Redis (ex: redis://localhost:6379/0).
        ttl_seconds: TTL da sessão (padrão: 3600s = 1h).
        key_prefix: Prefixo das chaves Redis.
    """

    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int = 3600,
        key_prefix: str = "ipnet:session:",
    ) -> None:
        self.redis_url = redis_url
        self.ttl = ttl_seconds
        self.prefix = key_prefix
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._redis = await aioredis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await self._redis.ping()
        logger.info("Redis conectado: %s", self.redis_url)

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    @property
    def _r(self) -> aioredis.Redis:
        if self._redis is None:
            raise RuntimeError("SessionMemory não conectado. Chame await connect() primeiro.")
        return self._redis

    def _key(self, phone: str) -> str:
        return f"{self.prefix}{phone}"

    # ─── CRUD ────────────────────────────────────────────────────────────────

    async def get(self, phone: str) -> SessionData | None:
        raw = await self._r.get(self._key(phone))
        if not raw:
            return None
        try:
            return SessionData.model_validate_json(raw)
        except Exception:
            logger.warning("Sessão corrompida para %s — removendo", phone)
            await self._r.delete(self._key(phone))
            return None

    async def set(self, session: SessionData) -> None:
        await self._r.set(
            self._key(session.phone),
            session.model_dump_json(),
            ex=self.ttl,
        )

    async def get_or_create(self, phone: str, user_name: str | None = None) -> SessionData:
        session = await self.get(phone)
        if session is None:
            session = SessionData(phone=phone, user_name=user_name)
            await self.set(session)
        return session

    async def delete(self, phone: str) -> None:
        await self._r.delete(self._key(phone))

    async def exists(self, phone: str) -> bool:
        return bool(await self._r.exists(self._key(phone)))

    # ─── Helpers de estado ───────────────────────────────────────────────────

    async def set_processing(self, phone: str) -> None:
        """Marca sessão como 'processando' para evitar respostas duplicadas."""
        session = await self.get_or_create(phone)
        session.state = SessionState.PROCESSING
        await self.set(session)

    async def set_active(self, phone: str) -> None:
        session = await self.get_or_create(phone)
        session.state = SessionState.ACTIVE
        await self.set(session)

    async def is_processing(self, phone: str) -> bool:
        session = await self.get(phone)
        return session is not None and session.state == SessionState.PROCESSING

    async def increment_message_count(self, phone: str) -> int:
        session = await self.get_or_create(phone)
        session.message_count += 1
        await self.set(session)
        return session.message_count

    async def set_metadata(self, phone: str, key: str, value: Any) -> None:
        session = await self.get_or_create(phone)
        session.metadata[key] = value
        await self.set(session)

    async def get_metadata(self, phone: str, key: str, default: Any = None) -> Any:
        session = await self.get(phone)
        if session is None:
            return default
        return session.metadata.get(key, default)

    # ─── Distributed lock ────────────────────────────────────────────────────

    async def acquire_lock(self, phone: str, ttl: int = 30) -> bool:
        """
        Tenta adquirir lock exclusivo de processamento para um número.
        Retorna True se conseguiu, False se já está sendo processado.
        Usa SET NX para garantir atomicidade.
        """
        lock_key = f"{self.prefix}lock:{phone}"
        result = await self._r.set(lock_key, "1", ex=ttl, nx=True)
        return result is not None

    async def release_lock(self, phone: str) -> None:
        lock_key = f"{self.prefix}lock:{phone}"
        await self._r.delete(lock_key)
