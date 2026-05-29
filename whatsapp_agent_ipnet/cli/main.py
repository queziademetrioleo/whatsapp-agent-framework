"""
CLI do whatsapp-agent-ipnet.

Comandos:
  whatsapp-agent init     — Cria projeto base com .env e main.py
  whatsapp-agent deploy   — Build + push + deploy no Cloud Run
  whatsapp-agent qrcode   — Mostra QR code da instância no terminal
  whatsapp-agent status   — Verifica estado da conexão WhatsApp
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from whatsapp_agent_ipnet.cli.deploy import run_deploy
from whatsapp_agent_ipnet.cli.scaffold import run_init

app = typer.Typer(
    name="whatsapp-agent",
    help="🤖 IPNET WhatsApp Agent — Deploy de agentes de IA no WhatsApp em < 24h",
    add_completion=False,
)
console = Console()


@app.command()
def init(
    project_name: str = typer.Argument("meu-agente", help="Nome do projeto"),
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Diretório de destino"),
) -> None:
    """Cria a estrutura de um novo projeto de agente WhatsApp."""
    run_init(project_name, directory, console)


@app.command()
def deploy(
    project_id: str = typer.Option(..., "--project-id", "-p", help="Google Cloud Project ID"),
    region: str = typer.Option("us-central1", "--region", "-r", help="Região do Cloud Run"),
    service_name: str = typer.Option(None, "--service", "-s", help="Nome do serviço Cloud Run"),
    instance_name: str = typer.Option(None, "--instance", "-i", help="Nome da instância WhatsApp"),
    cloud_sql_instance: str = typer.Option(None, "--sql-instance", help="Cloud SQL instance connection name"),
    image_tag: str = typer.Option("latest", "--tag", "-t", help="Tag da imagem Docker"),
    skip_build: bool = typer.Option(False, "--skip-build", help="Pula build da imagem"),
    skip_push: bool = typer.Option(False, "--skip-push", help="Pula push da imagem"),
) -> None:
    """Build, push e deploy do agente no Google Cloud Run."""
    run_deploy(
        project_id=project_id,
        region=region,
        service_name=service_name,
        instance_name=instance_name,
        cloud_sql_instance=cloud_sql_instance,
        image_tag=image_tag,
        skip_build=skip_build,
        skip_push=skip_push,
        console=console,
    )


@app.command()
def qrcode(
    evolution_url: str = typer.Option(None, "--url", "-u", envvar="IPNET_EVOLUTION_API_URL"),
    api_key: str = typer.Option(None, "--key", "-k", envvar="IPNET_EVOLUTION_API_KEY"),
    instance: str = typer.Option(None, "--instance", "-i", envvar="IPNET_INSTANCE_NAME"),
) -> None:
    """Exibe o QR code da instância WhatsApp no terminal."""
    from whatsapp_agent_ipnet.evolution import EvolutionClient

    if not all([evolution_url, api_key, instance]):
        console.print(
            "[red]Erro:[/red] Configure IPNET_EVOLUTION_API_URL, IPNET_EVOLUTION_API_KEY e IPNET_INSTANCE_NAME"
            "\nou passe via flags --url, --key, --instance"
        )
        raise typer.Exit(1)

    async def _get_qr():
        client = EvolutionClient(evolution_url, api_key)
        await client.connect()
        try:
            qr = await client.get_qrcode(instance)
            if qr:
                console.print(Panel(f"[green]QR Code para instância: {instance}[/green]"))
                EvolutionClient.print_qrcode_terminal(qr)
                console.print("\n[dim]Base64:[/dim]", qr.base64[:60] + "...")
            else:
                console.print(f"[yellow]Instância '{instance}' já está conectada ou não tem QR disponível.[/yellow]")
        finally:
            await client.disconnect()

    asyncio.run(_get_qr())


@app.command()
def status(
    evolution_url: str = typer.Option(None, "--url", envvar="IPNET_EVOLUTION_API_URL"),
    api_key: str = typer.Option(None, "--key", envvar="IPNET_EVOLUTION_API_KEY"),
    instance: str = typer.Option(None, "--instance", envvar="IPNET_INSTANCE_NAME"),
) -> None:
    """Verifica o estado da conexão WhatsApp."""
    from whatsapp_agent_ipnet.evolution import EvolutionClient

    if not all([evolution_url, api_key, instance]):
        console.print("[red]Erro:[/red] Variáveis de ambiente não configuradas.")
        raise typer.Exit(1)

    async def _check():
        client = EvolutionClient(evolution_url, api_key)
        await client.connect()
        try:
            state = await client.get_instance_state(instance)
            color = "green" if state.value == "open" else "yellow"
            table = Table(show_header=False, box=None)
            table.add_row("Instância", f"[bold]{instance}[/bold]")
            table.add_row("Estado", f"[{color}]{state.value.upper()}[/{color}]")
            table.add_row("URL", evolution_url)
            console.print(Panel(table, title="WhatsApp Status"))
        finally:
            await client.disconnect()

    asyncio.run(_check())


if __name__ == "__main__":
    app()
