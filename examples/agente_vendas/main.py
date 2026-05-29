"""
Exemplo completo: Agente de Vendas para WhatsApp
Demonstra tools, callbacks e configuração via .env
"""

from whatsapp_agent_ipnet import WhatsAppAgent

# ─────────────────────────────────────────────────────────────────────────────
# Configuração via variáveis de ambiente (arquivo .env)
# Veja .env.example para todas as opções disponíveis
# ─────────────────────────────────────────────────────────────────────────────

agent = WhatsAppAgent.from_env(
    name="Vendas Bot",
    system_prompt="""
Você é um assistente de vendas da IPNET Tecnologia.
Seu objetivo é ajudar clientes a encontrar o plano ideal e fechar vendas.

Regras:
- Responda sempre em português, de forma clara e objetiva
- Use emojis com moderação para ser mais amigável
- Nunca invente informações — use sempre as tools disponíveis
- Se não souber responder, diga que vai verificar e entre em contato
- Para fechar uma venda, colete: nome completo, email e plano escolhido
""",
)


# ─── Tools (funções que o agente pode chamar) ────────────────────────────────

@agent.tool
def listar_planos() -> str:
    """Lista todos os planos disponíveis com preços e benefícios"""
    return """
Planos disponíveis:

🥉 **Basic** — R$ 99/mês
  - Até 1.000 mensagens/mês
  - 1 agente
  - Suporte por email

🥈 **Pro** — R$ 199/mês
  - Mensagens ilimitadas
  - Até 3 agentes
  - Suporte prioritário
  - Relatórios avançados

🥇 **Enterprise** — Consultar
  - Agentes ilimitados
  - SLA garantido
  - Gerente de conta dedicado
  - Integrações customizadas
"""


@agent.tool
def consultar_disponibilidade(plano: str) -> str:
    """Verifica se um plano específico está disponível para contratação imediata"""
    disponivel = {"basic": True, "pro": True, "enterprise": False}
    plano_lower = plano.lower()
    if disponivel.get(plano_lower, False):
        return f"✅ O plano {plano.title()} está disponível para contratação imediata!"
    return f"⏳ O plano {plano.title()} requer análise. Nossa equipe entrará em contato em até 24h."


@agent.tool
def registrar_interesse(nome: str, email: str, plano: str) -> str:
    """
    Registra o interesse de um cliente em um plano.
    Use quando o cliente quiser fechar negócio ou pedir mais informações.
    Argumentos: nome completo do cliente, email e nome do plano
    """
    # Aqui você integraria com seu CRM, banco de dados, etc.
    print(f"[LEAD] Nome: {nome} | Email: {email} | Plano: {plano}")
    return (
        f"✅ Perfeito, {nome.split()[0]}! Seu interesse no plano {plano.title()} foi registrado.\n"
        f"Nossa equipe entrará em contato pelo email {email} em até 2 horas úteis."
    )


@agent.tool
def verificar_faq(pergunta: str) -> str:
    """
    Busca resposta em perguntas frequentes sobre a empresa e serviços.
    Use quando o cliente fizer perguntas gerais sobre a empresa.
    """
    faq = {
        "contrato": "Não temos fidelidade! Nossos planos são mensais e podem ser cancelados a qualquer momento.",
        "pagamento": "Aceitamos cartão de crédito, boleto bancário e PIX.",
        "instalacao": "A instalação é 100% online, feita em menos de 24h após a contratação.",
        "suporte": "Suporte disponível de segunda a sexta das 9h às 18h. Planos Pro e Enterprise têm suporte 24/7.",
        "teste": "Oferecemos 7 dias de teste gratuito sem precisar de cartão de crédito.",
    }
    for keyword, answer in faq.items():
        if keyword in pergunta.lower():
            return answer
    return "Para essa dúvida específica, recomendo falar com um de nossos especialistas. Posso registrar seu contato?"


# ─── Callbacks opcionais ─────────────────────────────────────────────────────

@agent.on_qrcode
async def novo_qrcode(instance_name: str, base64_qr: str):
    """Notifica quando um novo QR code é gerado (ex: enviar por email para o admin)"""
    print(f"⚠️  Novo QR code gerado para {instance_name}. Acesse o painel para escanear.")


@agent.on_connection_change
async def mudanca_conexao(instance_name: str, state: str):
    """Notifica quando o estado da conexão WhatsApp muda"""
    if state == "open":
        print(f"✅ WhatsApp conectado: {instance_name}")
    elif state == "close":
        print(f"❌ WhatsApp desconectado: {instance_name}")


# ─── Inicialização ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    agent.start()
