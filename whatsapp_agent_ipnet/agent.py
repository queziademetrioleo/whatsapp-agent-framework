"""
Classe principal WhatsAppAgent.

Orquestra todos os componentes:
  EvolutionClient → webhook → debouncer → Agno Agent (Gemini) → memória → resposta
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Callable

import uvicorn
from agno.agent import Agent
from agno.models.google import Gemini
from agno.storage.postgres import PostgresStorage
from fastapi import FastAPI
from pydantic import BaseModel

from whatsapp_agent_ipnet.config import AgentConfig
from whatsapp_agent_ipnet.debouncer import BufferedMessage, MessageDebouncer
from whatsapp_agent_ipnet.evolution import EvolutionClient
from whatsapp_agent_ipnet.memory.history import ConversationHistory, MessageRole
from whatsapp_agent_ipnet.memory.session import SessionMemory
from whatsapp_agent_ipnet.webhook import create_webhook_router

logger = logging.getLogger(__name__)


class WhatsAppAgent:
    """
    Agente de IA para WhatsApp pronto para deploy.

    Uso mínimo:
        agent = WhatsAppAgent(
            name="Meu Agente",
            system_prompt="Você é um assistente...",
            gemini_api_key="...",
            evolution_api_url="https://evolution.meusite.com",
            evolution_api_key="...",
            instance_name="meu-agente",
            postgres_url="postgresql+asyncpg://agentuser:senha@127.0.0.1:5432/agentdb",
            redis_url="redis://10.x.x.x:6379/0",
        )

        @agent.tool
        def consultar_produto(nome: str) -> str:
            \"\"\"Busca preço de um produto pelo nome\"\"\"
            return f"R$ 99,90"

        agent.start()

    Também aceita um AgentConfig como argumento único:
        config = AgentConfig(...)
        agent = WhatsAppAgent.from_config("Meu Agente", "prompt...", config)
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        gemini_api_key: str,
        evolution_api_url: str,
        evolution_api_key: str,
        instance_name: str,
        postgres_url: str,
        redis_url: str,
        debounce_seconds: float = 5.0,
        gemini_model: str = "gemini-2.5-flash",
        gemini_temperature: float = 0.7,
        gemini_max_tokens: int = 2048,
        max_history_messages: int = 20,
        session_ttl_seconds: int = 3600,
        webhook_secret: str | None = None,
        host: str = "0.0.0.0",
        port: int = 8080,
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.host = host
        self.port = port

        self._config = AgentConfig(
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            gemini_temperature=gemini_temperature,
            gemini_max_tokens=gemini_max_tokens,
            evolution_api_url=evolution_api_url,
            evolution_api_key=evolution_api_key,
            instance_name=instance_name,
            postgres_url=postgres_url,
            redis_url=redis_url,
            debounce_seconds=debounce_seconds,
            max_history_messages=max_history_messages,
            session_ttl_seconds=session_ttl_seconds,
            webhook_secret=webhook_secret,
            host=host,
            port=port,
        )

        self._tools: list[Callable] = []
        self._extra_instructions: list[str] = []
        self._on_qrcode: Callable | None = None
        self._on_connection: Callable | None = None

        # Inicializados em _startup()
        self._evolution: EvolutionClient | None = None
        self._session_memory: SessionMemory | None = None
        self._history: ConversationHistory | None = None
        self._debouncer: MessageDebouncer | None = None
        self._agno_agent: Agent | None = None
        self._app: FastAPI | None = None

    @classmethod
    def from_config(cls, name: str, system_prompt: str, config: AgentConfig) -> "WhatsAppAgent":
        return cls(
            name=name,
            system_prompt=system_prompt,
            **config.model_dump(),
        )

    @classmethod
    def from_env(cls, name: str, system_prompt: str) -> "WhatsAppAgent":
        """Carrega toda a configuração de variáveis de ambiente (prefixo IPNET_)."""
        config = AgentConfig()  # type: ignore[call-arg]
        return cls.from_config(name, system_prompt, config)

    # ─── Decoradores ─────────────────────────────────────────────────────────

    def tool(self, fn: Callable) -> Callable:
        """
        Registra uma função Python como tool disponível para o agente.

        A docstring da função é usada como descrição da tool pelo LLM.
        Os type hints dos parâmetros são usados para gerar o schema.

        Exemplo:
            @agent.tool
            def buscar_cep(cep: str) -> str:
                \"\"\"Busca endereço a partir de um CEP brasileiro\"\"\"
                ...
        """
        if not callable(fn):
            raise TypeError(f"@agent.tool espera uma função, recebeu {type(fn)}")
        if not fn.__doc__:
            logger.warning("Tool '%s' sem docstring — o LLM pode não saber quando usá-la", fn.__name__)
        self._tools.append(fn)
        logger.debug("Tool registrada: %s", fn.__name__)
        return fn

    def add_instruction(self, instruction: str) -> None:
        """Adiciona instrução extra ao system prompt."""
        self._extra_instructions.append(instruction)

    def on_qrcode(self, fn: Callable) -> Callable:
        """Callback chamado quando um novo QR code é gerado. Recebe (instance_name, base64_qr)."""
        self._on_qrcode = fn
        return fn

    def on_connection_change(self, fn: Callable) -> Callable:
        """Callback chamado quando o estado da conexão muda. Recebe (instance_name, state)."""
        self._on_connection = fn
        return fn

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    def start(self, webhook_url: str | None = None) -> None:
        """
        Inicia o servidor. Bloqueia até Ctrl+C.

        Args:
            webhook_url: URL pública do webhook (ex: https://meuagente.run.app/webhook/meu-agente).
                         Se None, precisa configurar o webhook manualmente na Evolution API.
        """
        self._webhook_url_override = webhook_url
        uvicorn.run(
            self._create_app(),
            host=self.host,
            port=self.port,
            log_level="info",
        )

    def get_app(self, webhook_url: str | None = None) -> FastAPI:
        """
        Retorna a aplicação FastAPI sem iniciar o servidor.
        Útil para deploy com gunicorn ou testes.
        """
        self._webhook_url_override = webhook_url
        return self._create_app()

    def _create_app(self) -> FastAPI:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await self._startup()
            yield
            await self._shutdown()

        app = FastAPI(
            title=f"{self.name} — WhatsApp Agent",
            version="0.1.0",
            lifespan=lifespan,
        )

        # Webhook router montado aqui, mas o debouncer só existe após _startup
        # Solução: montar o router em _startup onde temos o debouncer
        app.state.agent = self
        self._app = app
        return app

    async def _startup(self) -> None:
        logger.info("Iniciando %s...", self.name)
        cfg = self._config

        # 1. Evolution API client
        self._evolution = EvolutionClient(cfg.evolution_api_url, cfg.evolution_api_key)
        await self._evolution.connect()

        # 2. Memória
        self._session_memory = SessionMemory(
            redis_url=cfg.redis_url,
            ttl_seconds=cfg.session_ttl_seconds,
        )
        await self._session_memory.connect()

        self._history = ConversationHistory(
            postgres_url=cfg.postgres_url,
            max_messages=cfg.max_history_messages,
        )
        await self._history.setup()

        # 3. Agno agent com Gemini
        self._agno_agent = self._build_agno_agent()

        # 4. Debouncer
        self._debouncer = MessageDebouncer(
            debounce_seconds=cfg.debounce_seconds,
            callback=self._on_messages_ready,
        )

        # 5. Webhook router
        if self._app is not None:
            router = create_webhook_router(
                debouncer=self._debouncer,
                webhook_secret=cfg.webhook_secret,
                on_qrcode=self._on_qrcode,
                on_connection_change=self._on_connection,
            )
            self._app.include_router(router)

        logger.info("%s pronto na porta %d", self.name, cfg.port)

    async def _shutdown(self) -> None:
        logger.info("Encerrando %s...", self.name)
        if self._debouncer:
            await self._debouncer.flush_all()
        if self._evolution:
            await self._evolution.disconnect()
        if self._session_memory:
            await self._session_memory.disconnect()
        if self._history:
            await self._history.teardown()

    def _build_agno_agent(self) -> Agent:
        cfg = self._config
        system = self.system_prompt
        if self._extra_instructions:
            system += "\n\n" + "\n".join(f"- {i}" for i in self._extra_instructions)

        # PostgresStorage do Agno para memória de longo prazo do agent loop
        storage = PostgresStorage(
            db_url=cfg.postgres_url.replace("postgresql+asyncpg://", "postgresql://"),
            table_name="ipnet_agno_sessions",
        )

        return Agent(
            name=self.name,
            model=Gemini(
                id=cfg.gemini_model,
                api_key=cfg.gemini_api_key,
            ),
            instructions=system,
            tools=self._tools or None,
            storage=storage,
            add_history_to_messages=True,
            num_history_responses=cfg.max_history_messages,
            markdown=False,
        )

    # ─── Processamento de mensagens ──────────────────────────────────────────

    async def _on_messages_ready(self, phone: str, messages: list[BufferedMessage]) -> None:
        """
        Callback do debouncer — chamado após a janela de 5s expirar.
        Aqui agregamos as mensagens, consultamos o agente e enviamos a resposta.
        """
        assert self._evolution is not None
        assert self._session_memory is not None
        assert self._history is not None
        assert self._agno_agent is not None

        # Lock para evitar respostas duplicadas se mensagens chegarem muito rápido
        if not await self._session_memory.acquire_lock(phone, ttl=60):
            logger.warning("Mensagem de %s ignorada — já está sendo processada", phone)
            return

        try:
            await self._session_memory.set_processing(phone)

            # Agregar todas as mensagens do buffer em um único texto
            user_text = "\n".join(m.text for m in messages)

            logger.info("Processando mensagem de %s: %s", phone, user_text[:100])

            # Salvar no histórico
            await self._history.add_user(phone, user_text)

            # Mostrar "digitando..." enquanto processa
            try:
                await self._evolution.send_typing(
                    self._config.instance_name,
                    phone,
                    duration_ms=int(self._config.debounce_seconds * 1000),
                )
            except Exception:
                pass  # typing indicator é best-effort

            # Chamar o agente (thread_id = número do usuário para memória persistente)
            response = await asyncio.to_thread(
                self._agno_agent.run,
                user_text,
                session_id=phone,
            )

            # Extrair texto da resposta do Agno
            response_text = self._extract_response_text(response)

            if not response_text:
                logger.warning("Agente retornou resposta vazia para %s", phone)
                return

            # Salvar resposta no histórico
            await self._history.add_assistant(phone, response_text)

            # Enviar resposta ao usuário via WhatsApp
            # Divide respostas longas em múltiplas mensagens (limite 4096 chars do WhatsApp)
            for chunk in self._split_message(response_text):
                await self._evolution.send_text(
                    self._config.instance_name,
                    phone,
                    chunk,
                    quoted_message_id=messages[-1].message_id or None,
                )
                if len(chunk) > 500:
                    # Pequena pausa entre mensagens longas para parecer mais natural
                    await asyncio.sleep(0.5)

        except Exception:
            logger.exception("Erro ao processar mensagem de %s", phone)
            try:
                await self._evolution.send_text(
                    self._config.instance_name,
                    phone,
                    "Desculpe, ocorreu um erro ao processar sua mensagem. Tente novamente em instantes.",
                )
            except Exception:
                pass
        finally:
            await self._session_memory.set_active(phone)
            await self._session_memory.release_lock(phone)

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        """Extrai o texto da resposta do Agno (compatível com diferentes versões)."""
        if isinstance(response, str):
            return response.strip()
        if hasattr(response, "content"):
            content = response.content
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                return " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                ).strip()
        return str(response).strip()

    @staticmethod
    def _split_message(text: str, max_len: int = 4000) -> list[str]:
        """Divide texto longo em chunks respeitando parágrafos."""
        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for paragraph in text.split("\n\n"):
            p_len = len(paragraph) + 2  # +2 para \n\n
            if current_len + p_len > max_len and current:
                chunks.append("\n\n".join(current))
                current = [paragraph]
                current_len = p_len
            else:
                current.append(paragraph)
                current_len += p_len

        if current:
            chunks.append("\n\n".join(current))

        return chunks or [text]

    # ─── Utilitários públicos ─────────────────────────────────────────────────

    async def send_message(self, phone: str, text: str) -> None:
        """Envia mensagem proativa para um número (fora do fluxo de webhook)."""
        if self._evolution is None:
            raise RuntimeError("Agente não iniciado.")
        await self._evolution.send_text(self._config.instance_name, phone, text)

    async def clear_history(self, phone: str) -> None:
        """Limpa histórico e sessão de um usuário."""
        if self._history:
            await self._history.clear(phone)
        if self._session_memory:
            await self._session_memory.delete(phone)
