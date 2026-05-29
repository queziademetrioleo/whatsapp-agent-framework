"""
Histórico persistente de conversas usando PostgreSQL.

Armazena todas as mensagens trocadas (usuário + agente) para:
- Recarregar contexto após expiração da sessão Redis
- Analytics e auditoria
- Fine-tuning futuro

Schema criado automaticamente no primeiro uso via `await history.setup()`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence

import asyncpg
from pydantic import BaseModel

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ipnet_conversation_history (
    id          BIGSERIAL PRIMARY KEY,
    phone       TEXT        NOT NULL,
    role        TEXT        NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata    JSONB       NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ipnet_history_phone_created
    ON ipnet_conversation_history (phone, created_at DESC);
"""


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageRecord(BaseModel):
    id: int | None = None
    phone: str
    role: MessageRole
    content: str
    created_at: datetime | None = None
    metadata: dict = {}

    def to_agno_message(self) -> dict:
        """Converte para formato de mensagem do Agno/LangChain."""
        return {"role": self.role.value, "content": self.content}


class ConversationHistory:
    """
    Repositório de histórico de conversas em PostgreSQL.

    Args:
        postgres_url: URL asyncpg (ex: postgresql://user:pass@host/db).
                      Nota: NÃO use +asyncpg no driver aqui, asyncpg é direto.
        max_messages: Máximo de mensagens retornadas por consulta de contexto.
    """

    def __init__(
        self,
        postgres_url: str,
        max_messages: int = 20,
    ) -> None:
        # asyncpg não aceita 'postgresql+asyncpg://', normalizar
        self.postgres_url = postgres_url.replace("postgresql+asyncpg://", "postgresql://")
        self.max_messages = max_messages
        self._pool: asyncpg.Pool | None = None

    async def setup(self) -> None:
        """Conecta ao banco e cria tabelas se necessário."""
        self._pool = await asyncpg.create_pool(
            self.postgres_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_SQL)
        logger.info("ConversationHistory pronto. Tabela: ipnet_conversation_history")

    async def teardown(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    @property
    def _db(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("ConversationHistory não inicializado. Chame await setup().")
        return self._pool

    # ─── Write ───────────────────────────────────────────────────────────────

    async def add(
        self,
        phone: str,
        role: MessageRole,
        content: str,
        metadata: dict | None = None,
    ) -> MessageRecord:
        row = await self._db.fetchrow(
            """
            INSERT INTO ipnet_conversation_history (phone, role, content, metadata)
            VALUES ($1, $2, $3, $4::jsonb)
            RETURNING id, created_at
            """,
            phone,
            role.value,
            content,
            metadata or {},
        )
        return MessageRecord(
            id=row["id"],
            phone=phone,
            role=role,
            content=content,
            created_at=row["created_at"],
            metadata=metadata or {},
        )

    async def add_user(self, phone: str, content: str, **meta) -> MessageRecord:
        return await self.add(phone, MessageRole.USER, content, meta or None)

    async def add_assistant(self, phone: str, content: str, **meta) -> MessageRecord:
        return await self.add(phone, MessageRole.ASSISTANT, content, meta or None)

    # ─── Read ────────────────────────────────────────────────────────────────

    async def get_recent(
        self,
        phone: str,
        limit: int | None = None,
    ) -> list[MessageRecord]:
        """Retorna as N mensagens mais recentes em ordem cronológica."""
        n = limit or self.max_messages
        rows = await self._db.fetch(
            """
            SELECT id, phone, role, content, created_at, metadata
            FROM (
                SELECT * FROM ipnet_conversation_history
                WHERE phone = $1
                ORDER BY created_at DESC
                LIMIT $2
            ) sub
            ORDER BY created_at ASC
            """,
            phone,
            n,
        )
        return [
            MessageRecord(
                id=r["id"],
                phone=r["phone"],
                role=MessageRole(r["role"]),
                content=r["content"],
                created_at=r["created_at"],
                metadata=dict(r["metadata"]) if r["metadata"] else {},
            )
            for r in rows
        ]

    async def get_context_messages(self, phone: str, limit: int | None = None) -> list[dict]:
        """
        Retorna histórico formatado para passar diretamente ao Agno/LLM.
        Formato: [{"role": "user", "content": "..."}, ...]
        """
        records = await self.get_recent(phone, limit)
        return [r.to_agno_message() for r in records]

    async def count(self, phone: str) -> int:
        row = await self._db.fetchrow(
            "SELECT COUNT(*) FROM ipnet_conversation_history WHERE phone = $1",
            phone,
        )
        return row[0] if row else 0

    # ─── Delete ──────────────────────────────────────────────────────────────

    async def clear(self, phone: str) -> int:
        """Apaga todo o histórico de um número. Retorna quantas linhas foram removidas."""
        result = await self._db.execute(
            "DELETE FROM ipnet_conversation_history WHERE phone = $1",
            phone,
        )
        deleted = int(result.split()[-1])
        logger.info("Histórico de %s limpo (%d registros)", phone, deleted)
        return deleted
