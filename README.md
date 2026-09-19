# MVP Subscription API

Componente principal do MVP de controle de assinaturas digitais, desenvolvido para a disciplina de
**Arquitetura de Software** da PUC-Rio.

A aplicação registra assinaturas na moeda original, converte os custos para reais com as cotações
da API externa Frankfurter, confronta o gasto com metas por categoria na componente secundária e
aponta as assinaturas ociosas.

## Arquitetura

![Fluxograma da arquitetura do MVP](docs/architecture.png)

Três módulos com comunicação REST, um deles externo (Cenário 2 do enunciado):

| Componente | Responsabilidade |
|---|---|
| `mvp-subscription-api` (esta) | CRUD de assinaturas, normalização em BRL, relatório de desperdício, orquestração |
| `mvp-budget-api` (secundária) | metas por categoria, avaliação de estouro, projeção de desembolso |
| Frankfurter (externa) | cotações de câmbio do Banco Central Europeu |

Cada componente implementada tem repositório, banco SQLite e `Dockerfile` próprios, e nenhuma
acessa o banco da outra.

**Comunicação com a secundária:** cada serviço exige a sua própria chave no cabeçalho `X-API-Key`.
A principal propaga o `X-Request-ID` nas chamadas, com timeout de 3s e uma retentativa. Quando a
secundária fica indisponível, as rotas consolidadas respondem `200` com `budget_evaluation: null`
e a limitação declarada em `warnings`. Quando a API de câmbio falha, a última cotação conhecida é
usada, marcada com `stale: true`.

## API externa: Frankfurter

| Item | Detalhe |
|---|---|
| Serviço | [Frankfurter](https://frankfurter.dev) |
| O que fornece | Taxas de câmbio de referência publicadas pelo Banco Central Europeu |
| Versão | v2, nas rotas do provedor `ecb` |
| Custo | Gratuito |
| Cadastro | Não é necessário |
| Chave de API | Não utiliza |
| Licença | Código sob Apache 2.0; dados públicos, publicados pelo BCE |
| Base URL | `https://api.frankfurter.dev/v2` |

Rotas consumidas:

| Rota | Uso nesta aplicação |
|---|---|
| `GET /v2/providers/ecb/rate/{moeda}/brl` | cotação gravada ao cadastrar ou reprecificar uma assinatura |
| `GET /v2/providers/ecb/rates?base=EUR` | moedas cotadas pelo BCE, usadas para validar o cadastro |

A cotação é buscada pelo servidor, convertida para `Decimal`, gravada junto da assinatura em
`fx_rate_to_brl` e combinada com o ciclo de cobrança para produzir o custo mensal em reais. A rota
`GET /api/v1/fx/rates` devolve as cotações já no formato da aplicação. O usuário nunca é
redirecionado para a API externa.

## Tecnologias

Python 3.13, FastAPI, SQLAlchemy 2 (async, `aiosqlite`), httpx, Redis com queda para cache em
memória, pytest e Docker.

## Pré-requisitos

| Ferramenta | Versão |
|---|---|
| [Docker](https://docs.docker.com/get-docker/) + Docker Compose | Docker 24+, Compose v2 |
| [Git](https://git-scm.com/downloads) | qualquer versão recente |
| [Python](https://www.python.org/downloads/) (só para execução local) | 3.13, mínimo 3.10 |

No macOS, o `python3` do sistema é o 3.9 e não instala as dependências. Confira com
`python3 --version` e use `python3.13` se necessário. Antes de subir os containers, verifique que o
Docker está em execução com `docker info`.

## Como executar

### Os dois serviços juntos

O `docker-compose.yml` está na raiz deste repositório e sobe as duas componentes com o Redis. Clone
os dois repositórios lado a lado, porque o compose usa `../mvp-budget-api` como contexto de build:

```bash
git clone https://github.com/vtsouza29/mvp-subscription-api.git
git clone https://github.com/vtsouza29/mvp-budget-api.git
cd mvp-subscription-api
docker compose up --build
```

| Serviço | Porta | Documentação |
|---|---|---|
| `subscription-api` (principal) | 8000 | <http://localhost:8000/docs> |
| `budget-api` (secundária) | 8001 | <http://localhost:8001/docs> |
| `redis` | interno | |

As chaves de API têm valores de desenvolvimento no compose. Para usar chaves próprias, crie um
`.env` nesta pasta, que não é versionado:

```bash
SUBSCRIPTION_API_KEY=uma-chave-sua
BUDGET_API_KEY=outra-chave-diferente
```

### Somente esta componente

```bash
docker build -t mvp-subscription-api .
docker run --rm -p 8000:8000 \
  -e API_KEY=minha-chave \
  -e BUDGET_API_URL=http://host.docker.internal:8001 \
  -e BUDGET_API_KEY=chave-do-servico-de-metas \
  -e SEED_ON_STARTUP=true \
  mvp-subscription-api
```

### Execução local

```bash
python3.13 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
python -m seeds.seed               # dados de demonstração, idempotente
```

A componente secundária roda em outro terminal, na porta `8001`. Sem ela, as rotas consolidadas
respondem em modo degradado.

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `API_KEY` | `subscription-local-dev-key` | Chave exigida por esta API. |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/subscription.db` | Banco do serviço. |
| `BUDGET_API_URL` | `http://localhost:8001` | Endereço da componente secundária. |
| `BUDGET_API_KEY` | `budget-local-dev-key` | Chave própria do serviço de metas. |
| `BUDGET_API_TIMEOUT_SECONDS` | `3.0` | Timeout das chamadas à secundária. |
| `BUDGET_API_RETRIES` | `1` | Retentativas em falha de transporte. |
| `FRANKFURTER_URL` | `https://api.frankfurter.dev/v2` | Base da API externa. |
| `FX_FEE_PCT` | `0` | Encargos sobre moeda estrangeira (IOF e spread), em pontos percentuais. |
| `FX_CACHE_TTL_SECONDS` | `900` | Validade da cotação em cache. |
| `FX_FALLBACK_TTL_SECONDS` | `604800` | Validade do cache de emergência. |
| `REDIS_URL` | vazio | Se ausente, o cache usa memória. |
| `SEED_ON_STARTUP` | `false` | Cria assinaturas sintéticas no start. |
| `IDLE_DAYS_THRESHOLD` | `30` | Dias sem uso para entrar no relatório de desperdício. |
| `LOG_LEVEL` | `INFO` | Nível de log. |

## Rotas

Todas as rotas de negócio exigem o cabeçalho `X-API-Key`. A rota `/health` é aberta.

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/v1/subscriptions` | Cadastra uma assinatura e grava o snapshot da cotação. |
| `GET` | `/api/v1/subscriptions` | Lista com busca, filtros, ordenação e paginação. |
| `GET` | `/api/v1/subscriptions/{id}` | Consulta uma assinatura. |
| `PUT` | `/api/v1/subscriptions/{id}` | Substitui uma assinatura. |
| `PATCH` | `/api/v1/subscriptions/{id}/usage` | Registra o uso da assinatura. |
| `DELETE` | `/api/v1/subscriptions/{id}` | Remove uma assinatura. |
| `GET` | `/api/v1/insights/overview` | Gasto por categoria confrontado com as metas. |
| `GET` | `/api/v1/insights/waste` | Relatório de assinaturas ociosas. |
| `GET` | `/api/v1/insights/projection` | Projeção de desembolso, delegada à secundária. |
| `GET` | `/api/v1/fx/rates` | Cotações das moedas em uso. |
| `GET` | `/health` | Saúde do serviço e de cada dependência. |

Exemplo de cadastro em dólar:

```bash
curl -X POST http://localhost:8000/api/v1/subscriptions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: minha-chave" \
  -d '{
    "name": "Cloud Backup",
    "vendor": "Nimbus",
    "category": "SAAS",
    "amount": 11.99,
    "currency": "USD",
    "billing_cycle": "QUARTERLY",
    "started_on": "2025-04-01",
    "next_renewal_on": "2026-10-01"
  }'
```

A resposta traz `fx_rate_to_brl`, `fx_fee_pct` e o custo normalizado em `monthly_amount_brl` e
`yearly_amount_brl`.

## Regras de negócio

**Normalização.** O custo mensal é `amount × fx_rate_to_brl ÷ meses_do_ciclo`, o que torna
comparável uma assinatura anual em euro e uma mensal em real.

**Snapshot de câmbio.** A cotação é gravada no cadastro e só é buscada de novo quando o valor ou a
moeda mudam.

**Encargos de câmbio.** A taxa do BCE é de referência, sem impostos. `FX_FEE_PCT` aplica IOF e
spread do emissor sobre o valor convertido, apenas em moeda estrangeira. A resposta traz
`fx_fee_pct` com o encargo aplicado.

**Desperdício.** Uma assinatura ativa entra no relatório quando está sem uso há mais dias que
`IDLE_DAYS_THRESHOLD`. Assinaturas nunca usadas contam desde a data de início.

## Observabilidade e testes

Cada requisição recebe ou herda um `X-Request-ID`, propagado na chamada à secundária e devolvido no
cabeçalho da resposta. Os erros seguem o formato Problem Details (RFC 7807).

```bash
pytest
```

## Estrutura

```
app/
├── main.py            # criação da aplicação e ciclo de vida
├── config.py          # settings via variáveis de ambiente
├── database.py        # engine, sessão e criação do schema
├── security.py        # autenticação por API key
├── clients/           # HTTP: API externa de câmbio e serviço de metas
├── core/              # enums, cache, erros, correlação, tipos, encargos
├── models/            # mapeamento ORM do agregado Subscription
├── schemas/           # contratos de entrada e saída
├── repositories/      # acesso a dados
├── routers/           # rotas HTTP
└── services/          # regras de negócio e orquestração
seeds/                 # dados sintéticos idempotentes
tests/                 # testes automatizados
```

## Repositórios do MVP

| Componente | Repositório |
|---|---|
| Principal, `mvp-subscription-api` (esta) | https://github.com/vtsouza29/mvp-subscription-api |
| Secundária, `mvp-budget-api` | https://github.com/vtsouza29/mvp-budget-api |
| API externa, Frankfurter | https://frankfurter.dev |

## Licença

MIT.
