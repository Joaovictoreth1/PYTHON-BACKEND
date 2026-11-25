# TaskFlow Backend API v2.2

API RESTful em Python com FastAPI, SQLAlchemy 2.0, Alembic e Pydantic v2 para gerenciamento de projetos, tarefas, tags e comentários.

## Funcionalidades

- **CRUD completo & relacional:** Projetos (`1:N` Tarefas), Comentários (`1:N` em Tarefas) e Tags (`M:N`), com exclusão em cascata e índices compostos.
- **Concorrência segura:** *optimistic locking* via campo `version` no `PATCH /api/v1/tasks/{id}` (retorna `409 Conflict` em caso de edição concorrente) e `completed_at` gerenciado automaticamente.
- **Consultas avançadas:** paginação (`skip`/`limit`), busca textual segura contra curingas `LIKE`, filtros combinados (`status`, `priority`, `project_id`, `assignee`, `tag`, `overdue`, `due_before`, `due_after`) e ordenação (`sort_by`, `sort_order`).
- **Segurança:** `X-API-Key` em tempo constante, rate limiting por IP com headers `X-RateLimit-*` + `Retry-After` + limpeza de IPs inativos, suporte configurável a `X-Forwarded-For` e headers de segurança HTTP (`nosniff`, `DENY`, `no-referrer`, `no-store`).
- **Observabilidade:** `X-Request-ID` em logs e respostas, formato de log configurável (`text` ou `json`), header `X-Process-Time-Ms` e probes `/health/live` e `/health/ready` (503 se o banco cair).
- **Migrações & Infra:** Alembic, `Dockerfile` multi-stage (usuário não-root) e `docker-compose.yml` com PostgreSQL 16.

## Estrutura

```
app/
├── main.py            # create_app(): middlewares, handlers e routers
├── core/              # config, context (request_id), logging, erros, segurança, rate limit
├── db/                # engine/sessão (WAL no SQLite, pre-ping no Postgres), UTCDateTime
├── models.py          # ORM (Project, Task, Tag, TaskComment)
├── schemas/           # Pydantic v2 (entrada/saída)
├── repositories/      # acesso a dados (sem N+1)
├── services/          # regras de negócio
└── routers/           # endpoints HTTP
alembic/               # migrações de schema
task_manager_api.py    # ponto de entrada
tests/                 # pytest (cobertura >= 90%)
```

## Como executar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn task_manager_api:app --reload
```

Com Docker + PostgreSQL:

```bash
docker compose up --build
```

Documentação interativa: http://localhost:8000/docs

## Configuração

Veja `.env.example`. Principais variáveis:

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `ENVIRONMENT` | `development` | Em `production`, a API não inicia com a chave padrão |
| `DATABASE_URL` | `sqlite:///./taskflow_v2.db` | URL SQLAlchemy (SQLite ou PostgreSQL) |
| `API_SECRET_KEY` | `dev-secret-key-2026` (só dev) | Valor do header `X-API-Key` (mín. 16 caracteres) |
| `CORS_ORIGINS` | `*` | Origens permitidas separadas por vírgula |
| `RATE_LIMIT_MAX_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | `120` / `60` | Limite por IP |
| `TRUST_PROXY_HEADERS` | `false` | Se `true`, lê `X-Forwarded-For` atrás de proxy |
| `AUTO_CREATE_TABLES` | `true` | Defina `false` em produção com Alembic |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `text` | Nível e formato (`text` ou `json`) |

## Endpoints (`/api/v1`, exigem `X-API-Key`)

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health`, `/health/live`, `/health/ready` | Probes de saúde (públicos) |
| GET | `/api/v1/stats` | Indicadores consolidados |
| POST / GET | `/api/v1/projects` | Criar / listar projetos (`skip`, `limit`) |
| GET / PATCH / DELETE | `/api/v1/projects/{id}` | Detalhar / atualizar / remover (cascata) |
| POST / GET | `/api/v1/tasks` | Criar / listar tarefas com filtros e ordenação |
| GET / PATCH / DELETE | `/api/v1/tasks/{id}` | Detalhar / atualizar (com `version` opcional) / remover |
| POST / GET / DELETE | `/api/v1/tasks/{id}/comments[/{comment_id}]` | Comentários da tarefa |
| POST / GET / DELETE | `/api/v1/tags[/{tag_id}]` | Gerenciar tags |

## Qualidade

```bash
make check       # roda lint, format check, mypy (strict) e pytest com cobertura
make migrate     # aplica migrações Alembic
```
