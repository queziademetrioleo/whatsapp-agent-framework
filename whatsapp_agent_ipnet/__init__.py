"""
whatsapp-agent-ipnet
Framework Python para deployar agentes de IA no WhatsApp em menos de 24h.

Uso básico:
    from whatsapp_agent_ipnet import WhatsAppAgent

    agent = WhatsAppAgent(
        name="Meu Agente",
        system_prompt="Você é um assistente...",
        gemini_api_key="...",
        evolution_api_url="https://evolution.meusite.com",
        evolution_api_key="...",
        instance_name="meu-agente",
        postgres_url="postgresql+asyncpg://...",
        redis_url="redis://...",
    )

    @agent.tool
    def consultar_estoque(produto: str) -> str:
        \"\"\"Consulta estoque pelo nome\"\"\"
        return "10 unidades"

    agent.start()
"""

from whatsapp_agent_ipnet.agent import WhatsAppAgent
from whatsapp_agent_ipnet.config import AgentConfig
from whatsapp_agent_ipnet.evolution import EvolutionClient

__version__ = "0.1.0"
__all__ = ["WhatsAppAgent", "AgentConfig", "EvolutionClient"]
