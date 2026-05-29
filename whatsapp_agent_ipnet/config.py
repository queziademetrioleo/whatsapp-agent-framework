from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """
    Configuração do agente. Pode ser passada diretamente ou via variáveis de ambiente
    com prefixo IPNET_.

    Exemplo de .env:
        IPNET_GEMINI_API_KEY=AIza...
        IPNET_EVOLUTION_API_URL=https://evolution.meusite.com
        IPNET_EVOLUTION_API_KEY=minha-chave
        IPNET_INSTANCE_NAME=meu-agente
        IPNET_POSTGRES_URL=postgresql+asyncpg://user:pass@localhost/agentdb
        IPNET_REDIS_URL=redis://localhost:6379/0
    """

    model_config = SettingsConfigDict(env_prefix="IPNET_", env_file=".env", extra="ignore")

    # LLM
    gemini_api_key: str = Field(..., description="Google Gemini API Key")
    gemini_model: str = Field("gemini-2.5-flash", description="Modelo Gemini a usar")
    gemini_temperature: float = Field(0.7, ge=0.0, le=2.0)
    gemini_max_tokens: int = Field(2048, gt=0)

    # Evolution API (WhatsApp)
    evolution_api_url: str = Field(..., description="URL base da Evolution API (sem barra final)")
    evolution_api_key: str = Field(..., description="API Key da Evolution API")
    instance_name: str = Field(..., description="Nome da instância WhatsApp na Evolution API")

    # Banco de dados
    postgres_url: str = Field(
        ...,
        description="PostgreSQL connection string. Use asyncpg driver: postgresql+asyncpg://...",
    )
    redis_url: str = Field("redis://localhost:6379/0", description="Redis connection string")

    # Comportamento do agente
    debounce_seconds: float = Field(5.0, ge=0.5, le=30.0, description="Janela de debounce em segundos")
    max_history_messages: int = Field(20, ge=1, description="Máximo de msgs no histórico da sessão")
    session_ttl_seconds: int = Field(3600, ge=60, description="TTL da sessão no Redis (segundos)")

    # Servidor
    host: str = Field("0.0.0.0")
    port: int = Field(8080, ge=1, le=65535)
    webhook_secret: str | None = Field(None, description="Secret para validar webhooks (opcional)")

    @field_validator("evolution_api_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")
