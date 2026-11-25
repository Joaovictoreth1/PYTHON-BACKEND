# TaskFlow Backend API v2.1

API RESTful em Python com FastAPI, SQLAlchemy 2.0 e Pydantic v2 para gerenciamento de projetos e tarefas.

## Funcionalidades

- **CRUD completo:** Projetos e Tarefas (relação 1:N), com exclusão em cascata.
- **Segurança:** autenticação via `X-API-Key` (comparação em tempo constante) e rate limiting por IP (`429` + `Retry-After`).
- **Erros padronizados:** `{"detail": ...}` para 4xx, `{"error", "path"}` para 500, sem expor dados internos.
- **Observabilidade:** logs estruturados (sem chaves nem parâmetros SQL) e header `X-Process-Time-Ms`.
- **Consultas:** paginação (`skip`/`limit`), busca textual, filtros combinados e dashboard em `/api/v1/stats`.

## Estrutura

```
app/
├── main.py            # create_app(): middlewares, handlers e routers
├── core/              # config (env vars), logging, erros, segurança, rate limit
├── db/                # engine/sessão, tipo UTCDateTime
├── models.py          # ORM (ProjectModel, TaskModel)
├── schemas/           # Pydantic (entrada/saída)
├── repositories/      # acesso a dados
├── services/          # regras de negócio
└── routers/           # endpoints HTTP
task_manager_api.py    # ponto de entrada (compatível com versões anteriores)
tests/                 # pytest
```

## Como executar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # opcional; exporte as variáveis no shell
uvicorn task_manager_api:app --reload
```

Documentação interativa: http://localhost:8000/docs

## Configuração

Veja `.env.example`. Principais variáveis:

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `ENVIRONMENT` | `development` | Em `production`, a API não inicia com a chave padrão |
| `DATABASE_URL` | `sqlite:///./taskflow_v2.db` | URL SQLAlchemy |
| `API_SECRET_KEY` | `dev-secret-key-2026` (só dev) | Valor do header `X-API-Key` (mín. 16 caracteres) |
| `CORS_ORIGINS` | `*` | Lista separada por vírgula |
| `RATE_LIMIT_MAX_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | `120` / `60` | Limite por IP |
| `LOG_LEVEL` | `INFO` | Nível de log |

## Endpoints (`/api/v1`, exigem `X-API-Key`)

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health` | Health check (público) |
| GET | `/stats` | Indicadores consolidados |
| POST / GET | `/projects` | Criar / listar (`skip`, `limit`) |
| GET / PATCH / DELETE | `/projects/{id}` | Detalhar / atualizar / remover (cascata) |
| POST / GET | `/tasks` | Criar / listar (`status`, `priority`, `project_id`, `assignee`, `search`, `skip`, `limit`) |
| GET / PATCH / DELETE | `/tasks/{id}` | Detalhar / atualizar parcialmente / remover |

## Qualidade

```bash
pytest           # testes
ruff check .     # lint
ruff format .    # formatação
mypy             # tipos (strict)
```
