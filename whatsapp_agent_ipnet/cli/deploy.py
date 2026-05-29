"""
Deploy para Google Cloud Run via gcloud CLI.

Fluxo:
  1. Build da imagem Docker via Cloud Build (ou local)
  2. Push para Artifact Registry / Container Registry
  3. Deploy do serviço Cloud Run com sidecar Cloud SQL Auth Proxy
  4. Retorna a URL do serviço deployado
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn


def run_deploy(
    project_id: str,
    region: str,
    service_name: str | None,
    instance_name: str | None,
    cloud_sql_instance: str | None,
    image_tag: str,
    skip_build: bool,
    skip_push: bool,
    console: Console,
) -> None:
    # Resolve defaults
    svc = service_name or _read_env("IPNET_INSTANCE_NAME", "whatsapp-agent")
    inst = instance_name or svc
    image = f"gcr.io/{project_id}/{svc}:{image_tag}"

    console.print(Panel(
        f"[bold]Deploy:[/bold] {svc}\n"
        f"[dim]Projeto:[/dim] {project_id}\n"
        f"[dim]Região:[/dim] {region}\n"
        f"[dim]Imagem:[/dim] {image}",
        title="🚀 IPNET WhatsApp Agent Deploy",
    ))

    _check_gcloud(console)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        # 1. Build
        if not skip_build:
            task = progress.add_task("Buildando imagem via Cloud Build...", total=None)
            _run(
                ["gcloud", "builds", "submit", "--tag", image, "--project", project_id],
                console,
            )
            progress.update(task, description="[green]✓ Build concluído[/green]")

        # 2. Deploy no Cloud Run
        task = progress.add_task("Deployando no Cloud Run...", total=None)

        deploy_cmd = [
            "gcloud", "run", "deploy", svc,
            "--image", image,
            "--region", region,
            "--project", project_id,
            "--platform", "managed",
            "--allow-unauthenticated",
            "--port", "8080",
            "--timeout", "300",
            "--concurrency", "80",
            "--min-instances", "0",
            "--max-instances", "10",
            "--set-env-vars", _build_env_vars(inst),
        ]

        if cloud_sql_instance:
            deploy_cmd += ["--add-cloudsql-instances", cloud_sql_instance]

        # Service account (se existir)
        sa = _read_env("IPNET_SERVICE_ACCOUNT", "")
        if sa:
            deploy_cmd += ["--service-account", sa]

        _run(deploy_cmd, console)
        progress.update(task, description="[green]✓ Deploy concluído[/green]")

    # Pega URL do serviço
    url = _get_service_url(svc, region, project_id, console)
    if url:
        console.print(f"\n[green bold]✓ Agente online:[/green bold] {url}")
        console.print(f"\n[dim]Configure o webhook da Evolution API para:[/dim]")
        console.print(f"[bold]  {url}/webhook/{inst}[/bold]\n")


def _build_env_vars(instance_name: str) -> str:
    """Lê variáveis do .env e formata para o --set-env-vars do gcloud."""
    env_vars: dict[str, str] = {"IPNET_INSTANCE_NAME": instance_name}

    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key.startswith("IPNET_"):
                env_vars[key] = value

    return ",".join(f"{k}={v}" for k, v in env_vars.items())


def _get_service_url(service: str, region: str, project: str, console: Console) -> str | None:
    try:
        result = subprocess.run(
            [
                "gcloud", "run", "services", "describe", service,
                "--region", region,
                "--project", project,
                "--format", "value(status.url)",
            ],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _check_gcloud(console: Console) -> None:
    try:
        subprocess.run(["gcloud", "version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("[red]Erro:[/red] gcloud CLI não encontrado.")
        console.print("Instale em: https://cloud.google.com/sdk/docs/install")
        raise SystemExit(1)


def _run(cmd: list[str], console: Console) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]Erro:[/red]\n{result.stderr}")
        raise SystemExit(result.returncode)


def _read_env(key: str, default: str = "") -> str:
    val = os.environ.get(key, default)
    if not val:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith(f"{key}="):
                    return line.partition("=")[2].strip().strip('"').strip("'")
    return val or default
