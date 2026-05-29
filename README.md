# 🤖 whatsapp-agent-ipnet

> Framework Python para criar e deployar agentes de Inteligência Artificial no WhatsApp — do zero ao ar em menos de 24 horas.

---

## 📋 Índice

- [O que é isso?](#-o-que-é-isso)
- [Como funciona por dentro?](#-como-funciona-por-dentro)
- [O que você vai precisar](#-o-que-você-vai-precisar)
- [Instalação passo a passo](#-instalação-passo-a-passo)
  - [1. Python](#1-instalar-o-python)
  - [2. Redis](#2-instalar-o-redis)
  - [3. PostgreSQL](#3-instalar-o-postgresql)
  - [4. Evolution API](#4-configurar-a-evolution-api)
  - [5. O pacote](#5-instalar-o-pacote)
- [Seu primeiro agente](#-seu-primeiro-agente)
- [Entendendo o system prompt](#-entendendo-o-system-prompt)
- [Adicionando ferramentas (Tools)](#-adicionando-ferramentas-tools)
- [Conectando o WhatsApp (QR Code)](#-conectando-o-whatsapp-qr-code)
- [Variáveis de ambiente](#-variáveis-de-ambiente-env)
- [Deploy em produção (Cloud Run)](#-deploy-em-produção-google-cloud-run)
- [CLI — todos os comandos](#-cli--todos-os-comandos)
- [Exemplos práticos](#-exemplos-práticos)
- [Perguntas frequentes](#-perguntas-frequentes)
- [Solução de problemas](#-solução-de-problemas)

---

## 💡 O que é isso?

O `whatsapp-agent-ipnet` é um **framework Python** que permite criar um **agente de Inteligência Artificial** que conversa com pessoas pelo **WhatsApp**.

### O que é um "agente de IA"?

Um agente de IA é diferente de um chatbot comum. Um chatbot segue um fluxo fixo de respostas pré-programadas ("se o usuário digitar X, responda Y"). Um **agente** é capaz de:

- Entender linguagem natural em qualquer formato
- Decidir sozinho qual ação tomar com base no contexto
- Chamar funções do seu sistema (consultar banco de dados, APIs externas, etc.)
- Lembrar do histórico da conversa
- Raciocinar para resolver problemas complexos

### O que este framework faz por você?

Sem ele, para criar um agente no WhatsApp você precisaria construir do zero:
- Integração com a API do WhatsApp
- Servidor web para receber mensagens
- Lógica para não responder antes do usuário terminar de digitar
- Banco de dados para guardar o histórico de cada conversa
- Integração com o modelo de IA (Gemini)
- Sistema de "ferramentas" que o agente pode usar
- Script de deploy para nuvem

Com o `whatsapp-agent-ipnet`, tudo isso já está pronto. Você só precisa escrever o **comportamento do seu agente** e as **funções** que ele pode usar.

---

## 🔍 Como funciona por dentro?

```
Usuário digita no WhatsApp
        │
        ▼
  Evolution API          ← Plataforma que conecta ao WhatsApp
        │ webhook (HTTP)
        ▼
  Seu servidor (FastAPI)
        │
        ▼
  Debouncer (5 segundos) ← Espera o usuário terminar de digitar
        │                   antes de processar
        ▼
  Agente Agno + Gemini   ← A IA pensa e decide o que fazer
        │
        ├──→ Consulta histórico da conversa (PostgreSQL)
        ├──→ Verifica sessão ativa (Redis)
        └──→ Chama suas ferramentas (funções Python)
        │
        ▼
  Evolution API          ← Envia a resposta de volta
        │
        ▼
  Usuário recebe a resposta no WhatsApp
```

### Por que o "Debouncer de 5 segundos"?

Imagine que o usuário está digitando:

```
[12:00:01] "oi"
[12:00:02] "quero saber"
[12:00:04] "sobre os planos"
[12:00:05] "disponíveis"
```

Sem o debouncer, o agente responderia 4 vezes, uma para cada mensagem, causando respostas estranhas e gastando tokens desnecessariamente.

**Com o debouncer**, o sistema aguarda 5 segundos após a última mensagem e só então processa tudo junto como uma única pergunta: `"oi\nquero saber\nsobre os planos\ndisponíveis"`.

---

## ✅ O que você vai precisar

| Requisito | Onde fica | Para que serve |
|-----------|-----------|----------------|
| Python 3.11+ | Sua máquina local | Escrever e testar o agente |
| Google Cloud Project | GCP | Onde tudo roda em produção |
| Google Gemini API Key | Google AI Studio | O cérebro do agente (IA) |
| Cloud SQL (PostgreSQL) | GCP — via gcloud CLI | Histórico de conversas |
| Memorystore (Redis) | GCP — via gcloud CLI | Sessões ativas em memória |
| Cloud Run | GCP — via gcloud CLI | Servidor do agente |
| Evolution API | VPS ou serviço externo | Conectar ao WhatsApp |
| Um número de WhatsApp | Seu chip | Para o agente operar |

> **Toda a infraestrutura de banco, cache e servidor fica no GCP.** Você não instala Redis nem PostgreSQL na sua máquina — apenas o Python para escrever o código.

---

## 🚀 Configuração passo a passo

### 1. Instalar o Python (na sua máquina)

O framework requer **Python 3.11 ou superior**.

**Verificar se já tem Python instalado:**
```bash
python3 --version
# Deve mostrar: Python 3.11.x ou superior
```

**Se não tiver ou a versão for antiga:**

- **macOS:** `brew install python@3.11`
- **Ubuntu/Debian:** `sudo apt install python3.11 python3.11-venv python3-pip`
- **Windows:** Baixe em [python.org/downloads](https://www.python.org/downloads/) e marque a opção "Add Python to PATH" durante a instalação

---

### 2. Instalar o gcloud CLI (na sua máquina)

O `gcloud` é a ferramenta de linha de comando do Google Cloud. Todos os comandos de infraestrutura são executados por ela.

**macOS:**
```bash
brew install --cask google-cloud-sdk
```

**Linux:**
```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL   # recarrega o terminal
```

**Windows:** Baixe o instalador em [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install)

**Autenticar e configurar o projeto:**
```bash
gcloud auth login
# Abre o navegador para login com sua conta Google

gcloud config set project SEU_PROJECT_ID
# Substitua SEU_PROJECT_ID pelo ID do seu projeto no GCP
# Ex: gcloud config set project minha-empresa-prod
```

> Não sabe o Project ID? Acesse [console.cloud.google.com](https://console.cloud.google.com) e ele aparece no topo da página.

---

### 3. Ativar as APIs necessárias no GCP

Execute este bloco de uma vez. Cada API habilita um serviço diferente:

```bash
gcloud services enable \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  vpcaccess.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  servicenetworking.googleapis.com \
  compute.googleapis.com
```

> Isso pode levar alguns minutos. Você só precisa fazer isso uma vez por projeto.

---

### 4. Criar a Service Account (identidade do agente no GCP)

A Service Account é a "identidade" que o Cloud Run usa para acessar os outros serviços do GCP com segurança.

```bash
# Criar a service account
gcloud iam service-accounts create whatsapp-agent-sa \
  --display-name="WhatsApp Agent Service Account"

# Dar permissão para acessar o Cloud SQL
gcloud projects add-iam-policy-binding SEU_PROJECT_ID \
  --member="serviceAccount:whatsapp-agent-sa@SEU_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

# Dar permissão para acessar o Memorystore (Redis)
gcloud projects add-iam-policy-binding SEU_PROJECT_ID \
  --member="serviceAccount:whatsapp-agent-sa@SEU_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/redis.viewer"

# Dar permissão para ler secrets do Secret Manager
gcloud projects add-iam-policy-binding SEU_PROJECT_ID \
  --member="serviceAccount:whatsapp-agent-sa@SEU_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

> Substitua `SEU_PROJECT_ID` em todos os comandos pelo seu Project ID real.

---

### 5. Criar o Cloud SQL — PostgreSQL (banco de dados)

O Cloud SQL é o PostgreSQL gerenciado do GCP. Guarda todo o histórico de conversas.

```bash
# Criar a instância PostgreSQL (leva ~5 minutos)
gcloud sql instances create whatsapp-agent-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --storage-type=SSD \
  --storage-size=10GB \
  --storage-auto-increase

# Criar o banco de dados dentro da instância
gcloud sql databases create agentdb \
  --instance=whatsapp-agent-db

# Criar o usuário do banco com senha
gcloud sql users create agentuser \
  --instance=whatsapp-agent-db \
  --password=TROQUE_POR_UMA_SENHA_FORTE

# Pegar o "connection name" (você vai precisar depois)
gcloud sql instances describe whatsapp-agent-db \
  --format='value(connectionName)'
# Saída: SEU_PROJECT_ID:us-central1:whatsapp-agent-db
# Guarde esse valor!
```

> **Tiers disponíveis:**
> - `db-f1-micro` — ~$7/mês, para desenvolvimento e baixo volume
> - `db-g1-small` — ~$25/mês, para produção com volume médio
> - `db-custom-2-8192` — 2 vCPU + 8GB RAM, para alto volume

---

### 6. Criar o Memorystore — Redis (cache de sessão)

O Memorystore é o Redis gerenciado do GCP. Guarda as sessões ativas das conversas em andamento.

> ⚠️ **Importante:** O Memorystore usa **IP interno** (VPC). O Cloud Run precisa de um **VPC Connector** para acessá-lo — veja o passo seguinte.

```bash
# Criar a instância Redis (leva ~3 minutos)
gcloud redis instances create whatsapp-agent-redis \
  --size=1 \
  --region=us-central1 \
  --tier=basic \
  --redis-version=redis_7_0 \
  --network=projects/SEU_PROJECT_ID/global/networks/default

# Pegar o IP interno do Redis (você vai precisar depois)
gcloud redis instances describe whatsapp-agent-redis \
  --region=us-central1 \
  --format='value(host)'
# Saída: 10.x.x.x
# Guarde esse IP!
```

> O Redis no GCP não tem URL como `redis://localhost` — ele tem um **IP interno** como `10.0.0.27`. A porta é sempre `6379`.

---

### 7. Criar o VPC Connector (ponte entre Cloud Run e Redis)

O Cloud Run roda em ambiente isolado. Para acessar o Memorystore (que está na VPC), precisa de um conector.

```bash
# Criar o VPC Connector
gcloud compute networks vpc-access connectors create whatsapp-agent-connector \
  --region=us-central1 \
  --network=default \
  --range=10.8.0.0/28 \
  --min-instances=2 \
  --max-instances=10 \
  --machine-type=e2-micro

# Verificar se foi criado corretamente
gcloud compute networks vpc-access connectors describe whatsapp-agent-connector \
  --region=us-central1
# O campo "state" deve mostrar: READY
```

> **O que é o `--range=10.8.0.0/28`?** É um bloco de IPs reservado para o conector dentro da sua rede. Certifique-se de que esse range não conflita com outros já usados na sua VPC. Se der erro, tente `10.9.0.0/28`.

---

### 8. Salvar credenciais no Secret Manager

Nunca coloque senhas diretamente em variáveis de ambiente ou código. O Secret Manager do GCP guarda tudo com segurança.

```bash
# URL do PostgreSQL (usando o IP do Cloud SQL Auth Proxy)
echo -n "postgresql+asyncpg://agentuser:TROQUE_POR_UMA_SENHA_FORTE@127.0.0.1:5432/agentdb" | \
  gcloud secrets create ipnet-postgres-url --data-file=-

# URL do Redis (substitua 10.x.x.x pelo IP que você obteve no passo 6)
echo -n "redis://10.x.x.x:6379/0" | \
  gcloud secrets create ipnet-redis-url --data-file=-

# Chave do Gemini (obtenha em https://aistudio.google.com/app/apikey)
echo -n "AIzaSy..." | \
  gcloud secrets create ipnet-gemini-key --data-file=-

# API Key da Evolution API
echo -n "sua-api-key-da-evolution" | \
  gcloud secrets create ipnet-evolution-key --data-file=-
```

**Dar permissão para a service account ler os secrets:**
```bash
for secret in ipnet-postgres-url ipnet-redis-url ipnet-gemini-key ipnet-evolution-key; do
  gcloud secrets add-iam-policy-binding $secret \
    --member="serviceAccount:whatsapp-agent-sa@SEU_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

---

### 9. Configurar a Evolution API

A Evolution API é o intermediário entre seu agente e o WhatsApp. Você precisa de uma instância rodando em algum lugar acessível publicamente (não pode ficar só dentro do GCP sem IP externo).

**Opção A — VPS com Docker (recomendado):**

Em qualquer VPS (DigitalOcean, Hetzner, etc.):
```bash
docker run -d \
  --name evolution-api \
  -p 8080:8080 \
  -e SERVER_URL=https://SEU_DOMINIO_OU_IP:8080 \
  -e AUTHENTICATION_API_KEY=TROQUE_POR_KEY_SEGURA \
  atendai/evolution-api:latest
```

**Opção B — Railway / Render:**
Consulte a documentação em [doc.evolution-api.com](https://doc.evolution-api.com) para deploy com um clique.

> Anote a **URL** e a **API Key** da Evolution API — você vai precisar no próximo passo.

---

### 5. Instalar o pacote

> 💡 **Todo esse processo é feito no terminal do VS Code.** Abra com `Ctrl + `` ` `` ` (backtick) ou pelo menu **Terminal → New Terminal**.

#### Passo 1 — Criar uma pasta para o projeto e abrir no VS Code

```bash
# Crie e entre na pasta onde ficará seu agente
mkdir meus-agentes
cd meus-agentes
code .
```

O VS Code vai abrir. A partir daqui, use o terminal integrado dele (**Ctrl + `` ` ``**).

#### Passo 2 — Criar um ambiente virtual isolado

O ambiente virtual evita conflitos com outros pacotes Python instalados no seu computador.

```bash
# No terminal do VS Code:
python3 -m venv .venv
```

#### Passo 3 — Ativar o ambiente virtual

**macOS/Linux:**
```bash
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
.venv\Scripts\activate.bat
```

Quando ativado corretamente, você verá **`(.venv)`** no início da linha do terminal:
```
(.venv) Usuario@MacBook meus-agentes %
```

> ⚠️ **Importante:** Sempre que abrir um novo terminal no VS Code, você precisa ativar o ambiente virtual novamente com o comando acima. O VS Code pode fazer isso automaticamente — veja abaixo.

#### Passo 4 — Configurar o VS Code para ativar automaticamente

1. Pressione `Ctrl+Shift+P` (ou `Cmd+Shift+P` no Mac)
2. Digite **"Python: Select Interpreter"**
3. Selecione a opção que mostra **`.venv`** na lista (ex: `Python 3.11.x ('.venv')`)

Pronto — o VS Code vai ativar o `.venv` automaticamente em todo novo terminal.

#### Passo 5 — Instalar o framework

Com o ambiente virtual **ativado** (veja o `(.venv)` no terminal):

```bash
pip install whatsapp-agent-ipnet
```

**Verificar a instalação:**
```bash
whatsapp-agent --help
# Deve mostrar os comandos disponíveis
```

> **Conflitos de versão?** Se aparecer um aviso `ERROR: pip's dependency resolver...`, pode ignorar com segurança. São avisos sobre outros pacotes instalados globalmente, não afetam o funcionamento do framework.

---

## 🛠️ Seu primeiro agente

> Todos os comandos abaixo são executados no **terminal do VS Code** (`Ctrl + `` ` ```) com o ambiente virtual **ativado** (você deve ver `(.venv)` no início da linha).

### Passo 1 — Criar o projeto

```bash
whatsapp-agent init meu-primeiro-agente
cd meu-primeiro-agente
```

> Após o `cd`, o VS Code pode perguntar se deseja abrir a pasta no explorer — clique em **"Sim"** para navegar pelos arquivos pelo painel lateral.

Isso vai criar a seguinte estrutura:
```
meu-primeiro-agente/
├── main.py          ← Seu agente (edite aqui)
├── .env             ← Configurações e senhas (NUNCA suba pro Git)
├── .env.example     ← Modelo de configuração sem senhas
├── .gitignore       ← Já ignora o .env automaticamente
├── Dockerfile       ← Para deploy em produção
└── requirements.txt ← Dependências do projeto
```

### Passo 2 — Configurar as credenciais

Abra o arquivo `.env` e preencha:

```env
# Sua chave do Google Gemini
# Obtenha em: https://aistudio.google.com/app/apikey
IPNET_GEMINI_API_KEY=AIzaSy...

# URL onde a Evolution API está rodando
IPNET_EVOLUTION_API_URL=http://localhost:8081

# A chave que você definiu na Evolution API
IPNET_EVOLUTION_API_KEY=minha-chave-secreta

# Nome único para sua instância do WhatsApp
IPNET_INSTANCE_NAME=meu-primeiro-agente

# Conexão com o PostgreSQL
# Formato: postgresql+asyncpg://USUARIO:SENHA@HOST:PORTA/BANCO
IPNET_POSTGRES_URL=postgresql+asyncpg://postgres:suasenha@localhost:5432/agentdb

# Conexão com o Redis
IPNET_REDIS_URL=redis://localhost:6379/0
```

### Passo 3 — Escrever o agente

Abra o `main.py`. Você vai ver algo assim:

```python
from whatsapp_agent_ipnet import WhatsAppAgent

agent = WhatsAppAgent.from_env(
    name="Meu Agente",
    system_prompt="""
Você é um assistente virtual inteligente.
Responda sempre em português de forma clara e objetiva.
""",
)

if __name__ == "__main__":
    agent.start()
```

### Passo 4 — Rodar localmente

```bash
python main.py
```

Você verá no terminal:
```
INFO:     Iniciando Meu Agente...
INFO:     Redis conectado: redis://localhost:6379/0
INFO:     ConversationHistory pronto.
INFO:     Meu Agente pronto na porta 8080
INFO:     Uvicorn running on http://0.0.0.0:8080
```

### Passo 5 — Escanear o QR Code

Em outro terminal (com o ambiente virtual ativado):

```bash
whatsapp-agent qrcode
```

Um QR Code vai aparecer no terminal. **Escaneie com o WhatsApp do celular** que vai ser usado pelo agente:

```
WhatsApp → Menu (3 pontinhos) → Dispositivos conectados → Conectar dispositivo
```

> ⚠️ **Importante:** Use um número separado para o agente, não o seu número pessoal principal. Uma vez conectado, o WhatsApp vai operar como um dispositivo vinculado.

---

## 📝 Entendendo o System Prompt

O `system_prompt` é a **instrução principal** que define como o agente vai se comportar. É como um "manual de conduta" que o agente segue em todas as conversas.

### Como escrever um bom system prompt

**Estrutura recomendada:**

```python
system_prompt="""
[IDENTIDADE]
Você é [nome/papel] da empresa [nome da empresa].

[OBJETIVO]
Seu objetivo principal é [o que o agente deve fazer].

[REGRAS DE COMPORTAMENTO]
- Regra 1
- Regra 2
- Regra 3

[TOM DE VOZ]
- [Como deve falar]

[LIMITAÇÕES]
- Nunca [o que não deve fazer]
- Sempre [o que sempre deve fazer]
"""
```

**Exemplo completo para uma clínica:**

```python
system_prompt="""
Você é a assistente virtual da Clínica Saúde Total, chamada Sofia.

Seu objetivo é ajudar pacientes a:
- Agendar, remarcar e cancelar consultas
- Informar sobre especialidades disponíveis
- Explicar como funciona o convênio
- Tirar dúvidas gerais sobre a clínica

Regras de comportamento:
- Sempre se apresente pelo nome "Sofia" no primeiro contato
- Trate todos com muito respeito, usando "senhor" ou "senhora"
- Nunca dê diagnósticos médicos ou conselhos de saúde
- Se não souber a resposta, diga que vai verificar com a equipe

Tom de voz: acolhedor, profissional e empático.

Horário de atendimento: segunda a sexta, das 8h às 18h, sábados das 8h às 12h.
"""
```

### Dicas importantes

- **Seja específico:** Quanto mais detalhado o prompt, mais previsível o comportamento
- **Defina limitações:** Diga o que o agente NÃO deve fazer
- **Use português claro:** O modelo entende bem PT-BR
- **Teste bastante:** Simule conversas reais para ajustar o comportamento

---

## 🔧 Adicionando ferramentas (Tools)

**Ferramentas** são funções Python que você dá ao agente para que ele possa executar ações no mundo real. O agente decide sozinho quando e como usar cada ferramenta com base no contexto da conversa.

### Como funciona na prática

```python
@agent.tool
def consultar_saldo(cpf: str) -> str:
    """Consulta o saldo disponível de um cliente pelo CPF"""
    # Aqui você coloca sua lógica real
    saldo = seu_banco_de_dados.buscar_saldo(cpf)
    return f"Saldo disponível: R$ {saldo:.2f}"
```

Quando o usuário disser *"qual meu saldo?"* e fornecer o CPF, o agente vai automaticamente chamar essa função e usar o resultado para formular a resposta.

### Regras para escrever boas ferramentas

**1. A docstring é obrigatória e crucial**

O LLM usa a docstring para decidir *quando* chamar a ferramenta. Seja descritivo:

```python
# ❌ Ruim — docstring vaga
@agent.tool
def buscar(x: str) -> str:
    """Busca algo"""
    ...

# ✅ Bom — docstring clara
@agent.tool
def buscar_produto_por_nome(nome_produto: str) -> str:
    """
    Busca informações detalhadas de um produto pelo nome exato ou parcial.
    Retorna preço, disponibilidade em estoque e prazo de entrega.
    Use quando o cliente perguntar sobre um produto específico.
    """
    ...
```

**2. Use type hints nos parâmetros**

O framework usa os tipos para gerar o schema da ferramenta automaticamente:

```python
@agent.tool
def agendar_consulta(
    nome_paciente: str,
    data: str,          # formato: DD/MM/AAAA
    horario: str,       # formato: HH:MM
    especialidade: str,
) -> str:
    """Agenda uma consulta médica para o paciente"""
    ...
```

**3. Sempre retorne strings descritivas**

O retorno da função é o que o agente vai receber como resultado. Seja informativo:

```python
# ❌ Ruim — retorno obscuro
return True

# ✅ Bom — retorno descritivo
return "Consulta agendada com sucesso para 15/06/2025 às 14:30 com Dr. Silva (Cardiologia). ID de confirmação: #4821"
```

**4. Trate erros dentro da ferramenta**

```python
@agent.tool
def consultar_cep(cep: str) -> str:
    """Busca o endereço completo a partir de um CEP brasileiro"""
    import httpx
    try:
        cep_limpo = "".join(c for c in cep if c.isdigit())
        if len(cep_limpo) != 8:
            return "CEP inválido. Por favor, informe um CEP com 8 dígitos."
        resp = httpx.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=5)
        data = resp.json()
        if data.get("erro"):
            return f"CEP {cep} não encontrado."
        return f"{data['logradouro']}, {data['bairro']}, {data['localidade']}-{data['uf']}, CEP: {data['cep']}"
    except Exception as e:
        return f"Não foi possível consultar o CEP no momento. Tente novamente em instantes."
```

### Exemplos de tools comuns

**Consultar banco de dados:**
```python
@agent.tool
def buscar_pedido(numero_pedido: str) -> str:
    """Busca o status e informações de um pedido pelo número"""
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT status, data_entrega FROM pedidos WHERE numero = %s", (numero_pedido,))
    row = cur.fetchone()
    if not row:
        return f"Pedido {numero_pedido} não encontrado."
    status, data_entrega = row
    return f"Pedido {numero_pedido}: {status}. Previsão de entrega: {data_entrega}"
```

**Chamar uma API externa:**
```python
@agent.tool
def verificar_clima(cidade: str) -> str:
    """Verifica a previsão do tempo para uma cidade brasileira"""
    import httpx
    resp = httpx.get(
        "https://wttr.in/{cidade}?format=3&lang=pt".format(cidade=cidade),
        timeout=5
    )
    return resp.text
```

**Enviar e-mail:**
```python
@agent.tool
def enviar_confirmacao_email(email: str, mensagem: str) -> str:
    """Envia um e-mail de confirmação para o cliente"""
    import smtplib
    # sua lógica de envio de e-mail
    return f"E-mail de confirmação enviado para {email}"
```

---

## 📱 Conectando o WhatsApp (QR Code)

### Como funciona a conexão

O framework usa a **Evolution API** que, por sua vez, usa a biblioteca **Baileys** para conectar ao WhatsApp Web. Isso significa que você precisa de um número de WhatsApp real (não é a API oficial do Meta para empresas).

### Passo a passo

**1. Com o servidor rodando** (`python main.py`), execute:

```bash
whatsapp-agent qrcode
```

**2. No celular:**
- Abra o WhatsApp
- Toque nos 3 pontinhos (Android) ou em "Configurações" (iPhone)
- Selecione **"Dispositivos conectados"**
- Toque em **"Conectar dispositivo"**
- Aponte a câmera para o QR Code no terminal

**3. Aguarde a confirmação:**
```
✅ WhatsApp conectado: meu-primeiro-agente
```

### Configurar o webhook

Após conectar, você precisa dizer para a Evolution API para onde enviar as mensagens recebidas. Isso é feito automaticamente quando você cria a instância, mas verifique se o webhook está configurado:

**URL do webhook** (onde seu servidor está rodando):
```
http://SEU_IP_OU_DOMINIO:8080/webhook/NOME_DA_INSTANCIA
```

Exemplo local (usando ngrok para expor localmente):
```bash
# Instale ngrok: https://ngrok.com/download
ngrok http 8080
# Vai gerar uma URL como: https://abc123.ngrok.io
# Webhook: https://abc123.ngrok.io/webhook/meu-primeiro-agente
```

> **Por que preciso do ngrok localmente?** A Evolution API precisa conseguir enviar mensagens para o seu servidor. Como seu computador não tem um IP público direto, o ngrok cria um "túnel" temporário.

---

## ⚙️ Variáveis de ambiente (.env)

O arquivo `.env` guarda todas as configurações e credenciais do seu agente. **Nunca suba esse arquivo para o Git** (o `.gitignore` já cuida disso automaticamente).

### Todas as variáveis disponíveis

```env
# ─── Inteligência Artificial (Gemini) ────────────────────────────────────────
# Obtenha em: https://aistudio.google.com/app/apikey
IPNET_GEMINI_API_KEY=AIzaSy...

# Modelo a usar (gemini-2.5-flash é o recomendado: rápido e barato)
IPNET_GEMINI_MODEL=gemini-2.5-flash

# Criatividade das respostas: 0.0 = mais preciso/previsível, 2.0 = mais criativo
# Para atendimento: 0.5 a 0.8 | Para conteúdo criativo: 1.0 a 1.5
IPNET_GEMINI_TEMPERATURE=0.7

# Tamanho máximo das respostas (em tokens, ~1 token = 0.75 palavra)
IPNET_GEMINI_MAX_TOKENS=2048

# ─── WhatsApp (Evolution API) ─────────────────────────────────────────────────
# URL onde a Evolution API está rodando
IPNET_EVOLUTION_API_URL=https://evolution.seudominio.com

# Chave de autenticação da Evolution API
IPNET_EVOLUTION_API_KEY=sua-api-key-aqui

# Nome único desta instância (use só letras, números e hífens)
IPNET_INSTANCE_NAME=meu-agente

# ─── Banco de dados (PostgreSQL) ─────────────────────────────────────────────
# Formato: postgresql+asyncpg://USUARIO:SENHA@HOST:PORTA/BANCO
# Local:
IPNET_POSTGRES_URL=postgresql+asyncpg://postgres:suasenha@localhost:5432/agentdb
# Cloud SQL no Cloud Run (via Auth Proxy sidecar):
# IPNET_POSTGRES_URL=postgresql+asyncpg://postgres:suasenha@127.0.0.1:5432/agentdb

# ─── Cache de sessão (Redis) ──────────────────────────────────────────────────
# Formato: redis://HOST:PORTA/BANCO_NUMERO
IPNET_REDIS_URL=redis://localhost:6379/0

# ─── Comportamento do Agente ─────────────────────────────────────────────────
# Tempo de espera após a última mensagem antes de processar (segundos)
# Aumente se seus usuários costumam enviar muitas mensagens rápidas
IPNET_DEBOUNCE_SECONDS=5

# Quantas mensagens anteriores o agente "lembra" por conversa
IPNET_MAX_HISTORY_MESSAGES=20

# Por quanto tempo manter a sessão ativa no Redis (segundos)
# 3600 = 1 hora | 86400 = 1 dia
IPNET_SESSION_TTL_SECONDS=3600

# ─── Segurança ────────────────────────────────────────────────────────────────
# Secret opcional para validar que o webhook vem da Evolution API
# Se definido, a Evolution API deve enviar este valor no header x-webhook-secret
# IPNET_WEBHOOK_SECRET=um-secret-bem-longo-e-aleatorio

# ─── Servidor ─────────────────────────────────────────────────────────────────
IPNET_HOST=0.0.0.0
IPNET_PORT=8080
```

### Como obter a chave do Gemini

1. Acesse [aistudio.google.com](https://aistudio.google.com/app/apikey)
2. Faça login com sua conta Google
3. Clique em **"Create API Key"**
4. Copie a chave e cole no `.env`

> O Google oferece um plano gratuito generoso para o Gemini. Para produção com volume alto, verifique os limites em [ai.google.dev/pricing](https://ai.google.dev/pricing).

---

## ☁️ Deploy no Google Cloud Run

Com toda a infraestrutura criada (passos 3 a 9 da seção anterior), o deploy é feito com um único comando.

### Arquitetura final

```
Internet
   │
   ▼
Cloud Run (seu agente Python)
   │
   ├─→ Cloud SQL Auth Proxy ──→ Cloud SQL PostgreSQL (histórico)
   │
   ├─→ VPC Connector ──────────→ Memorystore Redis (sessões)
   │
   └─→ Evolution API (externa) ─→ WhatsApp
```

### Passo 1 — Build e deploy

```bash
whatsapp-agent deploy \
  --project-id SEU_PROJECT_ID \
  --region us-central1 \
  --service meu-agente \
  --sql-instance SEU_PROJECT_ID:us-central1:whatsapp-agent-db
```

O comando faz automaticamente:
1. ✅ Build da imagem Docker via Cloud Build
2. ✅ Push para o Container Registry
3. ✅ Deploy no Cloud Run com Cloud SQL Auth Proxy
4. ✅ Retorna a URL pública do agente

### Passo 2 — Conectar o Redis via VPC (complementar ao deploy)

O comando `deploy` cuida do Cloud SQL, mas o Redis precisa ser configurado manualmente uma vez via `gcloud run services update`:

```bash
# Substituia 10.x.x.x pelo IP do Redis obtido no passo 6
gcloud run services update meu-agente \
  --region=us-central1 \
  --vpc-connector=whatsapp-agent-connector \
  --vpc-egress=private-ranges-only \
  --update-env-vars="IPNET_REDIS_URL=redis://10.x.x.x:6379/0" \
  --service-account=whatsapp-agent-sa@SEU_PROJECT_ID.iam.gserviceaccount.com
```

### Passo 3 — Configurar o webhook na Evolution API

Após o deploy, você verá no terminal:
```
✓ Agente online: https://meu-agente-xyz.run.app

Configure o webhook da Evolution API para:
  https://meu-agente-xyz.run.app/webhook/meu-agente
```

Configure essa URL na sua instância da Evolution API e o agente começa a receber mensagens.

### Passo 4 — Verificar se tudo está funcionando

```bash
# Ver logs do Cloud Run em tempo real
gcloud run services logs tail meu-agente --region=us-central1

# Verificar estado do Cloud SQL
gcloud sql instances describe whatsapp-agent-db \
  --format='value(state)'
# Deve retornar: RUNNABLE

# Verificar estado do Redis
gcloud redis instances describe whatsapp-agent-redis \
  --region=us-central1 \
  --format='value(state)'
# Deve retornar: READY
```

### Custos estimados (GCP)

| Serviço | Tier | Custo estimado |
|---------|------|----------------|
| Cloud Run | Escala para zero | ~$0–5/mês (baixo volume) |
| Cloud SQL | `db-f1-micro` | ~$7/mês |
| Memorystore Redis | 1GB Basic | ~$35/mês |
| VPC Connector | `e2-micro` x2 | ~$15/mês |
| Cloud Build | 120 min/dia grátis | ~$0/mês |

> O Memorystore tem custo fixo mesmo sem uso. Para projetos em fase inicial, você pode usar um Redis externo (ex: [Upstash](https://upstash.com) tem plano gratuito) e pular os passos 6 e 7.

---

## 💻 CLI — Todos os comandos

### `whatsapp-agent init`

Cria a estrutura de um novo projeto.

```bash
whatsapp-agent init NOME_DO_PROJETO [--dir DIRETÓRIO]
```

| Argumento | Obrigatório | Descrição |
|-----------|-------------|-----------|
| `NOME_DO_PROJETO` | Sim | Nome do projeto (ex: `agente-vendas`) |
| `--dir` | Não | Diretório onde criar (padrão: pasta atual) |

```bash
# Exemplos:
whatsapp-agent init agente-suporte
whatsapp-agent init agente-vendas --dir /projetos
```

---

### `whatsapp-agent deploy`

Realiza o build e deploy no Google Cloud Run.

```bash
whatsapp-agent deploy \
  --project-id PROJETO \
  --region REGIAO \
  [--service NOME_SERVICO] \
  [--instance NOME_INSTANCIA] \
  [--sql-instance CONNECTION_NAME] \
  [--tag TAG_IMAGEM] \
  [--skip-build] \
  [--skip-push]
```

| Flag | Obrigatório | Padrão | Descrição |
|------|-------------|--------|-----------|
| `--project-id` | ✅ Sim | — | ID do projeto Google Cloud |
| `--region` | Não | `us-central1` | Região do Cloud Run |
| `--service` | Não | valor de `IPNET_INSTANCE_NAME` | Nome do serviço Cloud Run |
| `--sql-instance` | Não | — | Connection name do Cloud SQL |
| `--tag` | Não | `latest` | Tag da imagem Docker |
| `--skip-build` | Não | false | Pula a etapa de build |
| `--skip-push` | Não | false | Pula o push da imagem |

---

### `whatsapp-agent qrcode`

Exibe o QR Code da instância no terminal para escanear com o WhatsApp.

```bash
whatsapp-agent qrcode \
  [--url URL_EVOLUTION] \
  [--key API_KEY] \
  [--instance NOME_INSTANCIA]
```

Se as variáveis de ambiente `IPNET_EVOLUTION_API_URL`, `IPNET_EVOLUTION_API_KEY` e `IPNET_INSTANCE_NAME` estiverem configuradas no `.env`, basta rodar:

```bash
whatsapp-agent qrcode
```

---

### `whatsapp-agent status`

Verifica o estado atual da conexão WhatsApp.

```bash
whatsapp-agent status
```

Saída esperada quando conectado:
```
╭─────────────────────────╮
│      WhatsApp Status    │
│  Instância  meu-agente  │
│  Estado     OPEN        │
│  URL        http://...  │
╰─────────────────────────╯
```

Estados possíveis:
- **OPEN** — Conectado e funcionando ✅
- **CLOSE** — Desconectado ❌ (precisa escanear o QR novamente)
- **CONNECTING** — Tentando reconectar ⏳

---

## 📚 Exemplos práticos

### Agente de Suporte ao Cliente

```python
from whatsapp_agent_ipnet import WhatsAppAgent

agent = WhatsAppAgent.from_env(
    name="Suporte TechCorp",
    system_prompt="""
Você é o assistente de suporte da TechCorp, chamado Max.

Seu trabalho é:
- Ajudar clientes com problemas técnicos
- Registrar chamados de suporte
- Consultar o status de chamados existentes
- Escalar para humanos quando necessário

Regras:
- Seja empático — o cliente pode estar frustrado
- Peça o número do pedido antes de consultar qualquer coisa
- Se não conseguir resolver em 3 tentativas, ofereça falar com um humano
- Nunca prometa prazos sem consultar o sistema
""",
)

@agent.tool
def abrir_chamado(nome: str, email: str, descricao_problema: str) -> str:
    """Abre um novo chamado de suporte técnico com os dados do cliente"""
    # Aqui você integraria com seu sistema de tickets (Zendesk, Jira, etc.)
    numero = "TKT-" + str(hash(email + descricao_problema))[-6:]
    return f"Chamado {numero} aberto com sucesso! Você receberá atualizações no email {email}."

@agent.tool
def consultar_chamado(numero_chamado: str) -> str:
    """Consulta o status atual de um chamado de suporte pelo número"""
    # Consulta no seu banco de dados
    return f"Chamado {numero_chamado}: Em análise pela equipe técnica. Previsão: 2 horas úteis."

@agent.tool
def escalar_para_humano(motivo: str) -> str:
    """Escala a conversa para um atendente humano quando o problema é complexo"""
    # Dispara notificação para a equipe
    return "Transferindo para um especialista. Você será atendido em até 5 minutos."

agent.start()
```

---

### Agente de Agendamentos

```python
from whatsapp_agent_ipnet import WhatsAppAgent
from datetime import datetime

agent = WhatsAppAgent.from_env(
    name="Agenda Fácil",
    system_prompt="""
Você é o assistente de agendamentos da Barbearia do Zé.

Você pode:
- Mostrar horários disponíveis
- Agendar cortes
- Confirmar e cancelar agendamentos

Serviços disponíveis:
- Corte simples: R$ 35 (30 min)
- Corte + barba: R$ 55 (1 hora)
- Barba: R$ 25 (30 min)

Funcionamento: Segunda a sábado, 9h às 19h.

Sempre confirme o nome do cliente e o serviço antes de agendar.
""",
)

@agent.tool
def verificar_horarios_disponiveis(data: str) -> str:
    """
    Verifica horários livres para agendamento em uma data específica.
    A data deve estar no formato DD/MM/AAAA.
    """
    # Consulta no seu sistema de agenda
    horarios = ["09:00", "10:30", "14:00", "15:30", "17:00"]
    return f"Horários disponíveis em {data}: {', '.join(horarios)}"

@agent.tool
def criar_agendamento(
    nome_cliente: str,
    telefone: str,
    servico: str,
    data: str,
    horario: str,
) -> str:
    """
    Cria um novo agendamento para o cliente.
    Requer: nome, telefone, serviço desejado, data (DD/MM/AAAA) e horário (HH:MM).
    """
    # Salva no banco de dados
    codigo = f"AG{hash(nome_cliente + data + horario) % 10000:04d}"
    return (
        f"✅ Agendamento confirmado!\n"
        f"Código: {codigo}\n"
        f"Cliente: {nome_cliente}\n"
        f"Serviço: {servico}\n"
        f"Data: {data} às {horario}\n"
        f"Endereço: Rua das Flores, 123 — Centro"
    )

agent.start()
```

---

### Agente com notificação de QR Code por e-mail

```python
import smtplib
from email.mime.text import MIMEText
from whatsapp_agent_ipnet import WhatsAppAgent

agent = WhatsAppAgent.from_env(
    name="Meu Agente",
    system_prompt="Você é um assistente virtual...",
)

@agent.on_qrcode
async def notificar_qrcode(instance_name: str, base64_qr: str):
    """Envia e-mail para o admin quando o QR Code precisar ser escaneado novamente"""
    msg = MIMEText(
        f"O agente '{instance_name}' precisa ser reconectado.\n"
        f"Escaneie o QR Code no painel da Evolution API."
    )
    msg["Subject"] = f"⚠️ Agente {instance_name} desconectado"
    msg["From"] = "sistema@suaempresa.com"
    msg["To"] = "admin@suaempresa.com"

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login("sistema@suaempresa.com", "sua-senha-app")
        s.send_message(msg)

@agent.on_connection_change
async def monitorar_conexao(instance_name: str, state: str):
    """Loga mudanças de estado para monitoramento"""
    print(f"[{instance_name}] Estado: {state.upper()}")

agent.start()
```

---

## ❓ Perguntas frequentes

### O agente pode responder mais de um usuário ao mesmo tempo?

**Sim.** Cada número de telefone tem seu próprio contexto, sessão e histórico. O sistema processa múltiplas conversas em paralelo sem conflito.

### O agente lembra de conversas anteriores?

**Sim.** Cada conversa é salva no PostgreSQL com o número do usuário como identificador. Nas próximas mensagens, o agente carrega o histórico recente (configurável via `IPNET_MAX_HISTORY_MESSAGES`). Após o `IPNET_SESSION_TTL_SECONDS` sem mensagens, a sessão Redis expira, mas o histórico do banco permanece.

### Posso usar grupos do WhatsApp?

O framework atualmente processa mensagens de **conversas individuais**. Mensagens de grupos são ignoradas por padrão (o `remoteJid` de grupos termina em `@g.us`).

### Qual é o custo?

- **Gemini 2.5 Flash:** ~$0.075 por 1 milhão de tokens de entrada / ~$0.30 por 1 milhão de saída. Um atendimento médio de 10 mensagens custa frações de centavo.
- **Cloud Run:** Cobra por requisição. Com escala para zero quando inativo, o custo pode ser de poucos dólares por mês para volumes médios.
- **Cloud SQL:** A partir de ~$7/mês para a menor instância.

### Posso usar outro modelo de IA além do Gemini?

A versão atual usa o Gemini via Agno. O Agno suporta outros modelos (OpenAI, Anthropic, etc.). Contribuições são bem-vindas!

### O número fica banido no WhatsApp?

O risco existe em qualquer integração não-oficial. Recomendações para minimizar o risco:
- Use um número específico para o agente (não o seu pessoal)
- Não envie mensagens em massa ou spam
- Mantenha um comportamento humano (não responda instantaneamente a todos — o debouncer ajuda nisso)
- Evite enviar muitas mensagens seguidas para o mesmo número em pouco tempo

---

## 🔧 Solução de problemas

### `ModuleNotFoundError: No module named 'whatsapp_agent_ipnet'`

O ambiente virtual não está ativado ou o pacote não foi instalado. No terminal do VS Code:
```bash
source .venv/bin/activate        # macOS/Linux
# ou
.venv\Scripts\Activate.ps1       # Windows PowerShell

pip install whatsapp-agent-ipnet
```

### O terminal do VS Code não mostra `(.venv)` ao abrir

O interpretador Python não foi selecionado corretamente:
1. `Ctrl+Shift+P` → **"Python: Select Interpreter"**
2. Escolha a opção com `.venv` na lista
3. Feche o terminal (`Ctrl+`` ` ``) e abra um novo

Se `.venv` não aparecer na lista:
```bash
python3 -m venv .venv
```
E repita os passos acima.

### `pip install` instala mas `whatsapp-agent` não é encontrado

O executável foi instalado no ambiente errado. Certifique-se de que o `(.venv)` está visível antes de instalar:
```bash
# Verificar qual pip está sendo usado:
which pip      # macOS/Linux — deve mostrar um caminho com .venv
where pip      # Windows — deve mostrar um caminho com .venv

# Se não estiver no .venv, ative e reinstale:
source .venv/bin/activate
pip install --force-reinstall whatsapp-agent-ipnet
```

### Aviso `dependency resolver` ao instalar

```
ERROR: pip's dependency resolver does not currently take into account...
```

Isso é apenas um **aviso**, não um erro. O pacote foi instalado corretamente. Acontece quando há outros pacotes instalados globalmente que têm versões conflitantes. O ambiente virtual isola o seu projeto e o agente funcionará normalmente.

### Erro de conexão com o Redis (Memorystore)

O Cloud Run não consegue atingir o Redis. Verifique:

1. O VPC Connector está com `state: READY`?
```bash
gcloud compute networks vpc-access connectors describe whatsapp-agent-connector \
  --region=us-central1 --format='value(state)'
# Deve retornar: READY
```

2. O `--vpc-connector` foi aplicado ao serviço?
```bash
gcloud run services describe meu-agente \
  --region=us-central1 \
  --format='value(spec.template.metadata.annotations)'
# Deve conter: run.googleapis.com/vpc-access-connector
```

3. O IP do Redis na variável `IPNET_REDIS_URL` está correto?
```bash
gcloud redis instances describe whatsapp-agent-redis \
  --region=us-central1 --format='value(host)'
```

### Erro de conexão com o PostgreSQL (Cloud SQL)

1. O connection name está correto?
```bash
gcloud sql instances describe whatsapp-agent-db \
  --format='value(connectionName)'
# Formato: SEU_PROJECT_ID:us-central1:whatsapp-agent-db
```

2. A service account tem permissão `roles/cloudsql.client`?
```bash
gcloud projects get-iam-policy SEU_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:whatsapp-agent-sa" \
  --format='table(bindings.role)'
```

3. O `--add-cloudsql-instances` foi passado no deploy?
```bash
gcloud run services describe meu-agente \
  --region=us-central1 \
  --format='value(spec.template.metadata.annotations)'
# Deve conter: run.googleapis.com/cloudsql-instances
```

### QR Code não aparece ou dá erro 404

A instância ainda não existe na Evolution API. Verifique se:
1. A Evolution API está acessível na URL configurada em `IPNET_EVOLUTION_API_URL`
2. A `IPNET_EVOLUTION_API_KEY` está correta
3. O servidor do agente está rodando (`python main.py`)

Tente criar a instância manualmente:
```bash
curl -X POST "http://localhost:8081/instance/create" \
  -H "apikey: minha-chave-secreta" \
  -H "Content-Type: application/json" \
  -d '{"instanceName": "meu-agente", "qrcode": true}'
```

### Agente não responde às mensagens

Verifique nessa ordem:

1. **Webhook configurado?** A Evolution API precisa saber para onde enviar as mensagens.
2. **URL acessível?** O servidor precisa ser acessível pela Evolution API (use ngrok localmente).
3. **Logs do servidor:** `python main.py` mostra os eventos recebidos.
4. **Estado do WhatsApp:** `whatsapp-agent status` — deve mostrar `OPEN`.

### `Error: gcloud CLI não encontrado` ao fazer deploy

Instale o gcloud CLI:
- [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install)

Após instalar:
```bash
gcloud auth login
gcloud config set project SEU_PROJECT_ID
```

### Respostas lentas ou timeout

O Gemini 2.5 Flash geralmente responde em 2-5 segundos. Se estiver mais lento:
- Reduza `IPNET_MAX_HISTORY_MESSAGES` (menos contexto = resposta mais rápida)
- Reduza `IPNET_GEMINI_MAX_TOKENS` se as respostas estiverem muito longas
- Verifique sua conexão com a internet e a latência para a API do Gemini

---

## 🤝 Contribuindo

Contribuições são bem-vindas! Para reportar bugs, sugerir funcionalidades ou enviar código:

1. Abra uma issue descrevendo o problema ou sugestão
2. Fork o repositório
3. Crie uma branch: `git checkout -b feature/minha-feature`
4. Faça suas alterações com testes
5. Abra um Pull Request

---

## 📄 Licença

MIT License — veja o arquivo [LICENSE](LICENSE) para detalhes.

---

*Desenvolvido por [IPNET Tecnologia](https://ipnet.com.br)*
