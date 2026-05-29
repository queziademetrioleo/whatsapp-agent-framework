"""Gerador de projeto base (whatsapp-agent init)."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

ENV_TEMPLATE = """\
# ─── LLM ────────────────────────────────────────────────────────────────────
IPNET_GEMINI_API_KEY=SUA_GEMINI_API_KEY_AQUI
IPNET_GEMINI_MODEL=gemini-2.5-flash
IPNET_GEMINI_TEMPERATURE=0.7

# ─── WhatsApp (Evolution API) ────────────────────────────────────────────────
IPNET_EVOLUTION_API_URL=https://evolution.seudominio.com
IPNET_EVOLUTION_API_KEY=SUA_EVOLUTION_API_KEY_AQUI
IPNET_INSTANCE_NAME={project_name}

# ─── Banco de Dados ──────────────────────────────────────────────────────────
# Local:
IPNET_POSTGRES_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/agentdb
# Cloud SQL via Auth Proxy (Cloud Run):
# IPNET_POSTGRES_URL=postgresql+asyncpg://postgres:SENHA@localhost:5432/agentdb

IPNET_REDIS_URL=redis://localhost:6379/0

# ─── Agente ──────────────────────────────────────────────────────────────────
IPNET_DEBOUNCE_SECONDS=5
IPNET_MAX_HISTORY_MESSAGES=20
IPNET_SESSION_TTL_SECONDS=3600

# ─── Servidor ────────────────────────────────────────────────────────────────
IPNET_HOST=0.0.0.0
IPNET_PORT=8080
# IPNET_WEBHOOK_SECRET=seu-secret-opcional
"""

MAIN_TEMPLATE = """\
\"\"\"
Agente WhatsApp: {agent_name}
Gerado com whatsapp-agent-ipnet
\"\"\"

from whatsapp_agent_ipnet import WhatsAppAgent

agent = WhatsAppAgent.from_env(
    name="{agent_name}",
    system_prompt=\"\"\"
Você é um assistente virtual inteligente.
Responda sempre em português de forma clara e objetiva.
Seja cordial e prestativo.
\"\"\",
)


# ─── Tools ──────────────────────────────────────────────────────────────────
# Adicione aqui as funções que o agente pode chamar.
# A docstring é usada pelo LLM para entender quando usar a ferramenta.

@agent.tool
def consultar_horario() -> str:
    \"\"\"Retorna o horário atual de atendimento\"\"\"
    return "Atendemos de segunda a sexta, das 9h às 18h."


@agent.tool
def consultar_preco(produto: str) -> str:
    \"\"\"Consulta o preço de um produto pelo nome\"\"\"
    # Substitua pela sua lógica real (banco de dados, API, etc.)
    precos = {{
        "plano basic": "R$ 99/mês",
        "plano pro": "R$ 199/mês",
        "plano enterprise": "Consultar",
    }}
    return precos.get(produto.lower(), f"Produto '{produto}' não encontrado.")


# ─── Callbacks (opcional) ────────────────────────────────────────────────────

@agent.on_qrcode
async def handle_qrcode(instance_name: str, base64_qr: str):
    \"\"\"Chamado quando um novo QR code é gerado. Útil para notificar admins.\"\"\"
    print(f"Novo QR code para {{instance_name}}")


if __name__ == "__main__":
    agent.start()
"""

DOCKERFILE_TEMPLATE = """\
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "main.py"]
"""

REQUIREMENTS_TEMPLATE = """\
whatsapp-agent-ipnet>=0.1.0
"""

GITIGNORE_TEMPLATE = """\
.env
*.pyc
__pycache__/
.venv/
venv/
dist/
*.egg-info/
"""


def run_init(project_name: str, directory: Path, console: Console) -> None:
    target = directory / project_name
    if target.exists():
        console.print(f"[red]Diretório '{target}' já existe.[/red]")
        raise SystemExit(1)

    target.mkdir(parents=True)

    agent_name = project_name.replace("-", " ").replace("_", " ").title()

    files = {
        ".env": ENV_TEMPLATE.format(project_name=project_name),
        ".env.example": ENV_TEMPLATE.format(project_name=project_name),
        "main.py": MAIN_TEMPLATE.format(agent_name=agent_name),
        "Dockerfile": DOCKERFILE_TEMPLATE,
        "requirements.txt": REQUIREMENTS_TEMPLATE,
        ".gitignore": GITIGNORE_TEMPLATE,
    }

    for filename, content in files.items():
        (target / filename).write_text(content, encoding="utf-8")

    console.print(f"\n[green]✓ Projeto criado em {target}/[/green]\n")
    console.print("Próximos passos:")
    console.print(f"  1. [bold]cd {project_name}[/bold]")
    console.print("  2. Edite [bold].env[/bold] com suas credenciais")
    console.print("  3. [bold]pip install -r requirements.txt[/bold]")
    console.print("  4. [bold]python main.py[/bold]\n")
