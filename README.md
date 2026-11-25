# TaskFlow Backend API v3.0

API RESTful multi-tenant em Python com FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, autenticação JWT (com rotação de refresh token) e rate limiting distribuído opcional via Redis.

## Funcionalidades

- **Autenticação & Segurança:** cadastro e login com hash Argon2id (`pwdlib`), JWT de curta duração (`access_token`) e `refresh_token` opaco com rotação e detecção de reuso (*replay attack* revoga toda a família do token).
- **Multi-tenancy:** projetos, tarefas, tags, comentários e exportações são isolados por `user_id`, com unicidade de nome por tenant e resposta `404` sem vazamento entre usuários.
- **Domínio avançado:** *optimistic locking* (`version` -> `409 Conflict`), `completed_at` automático, ordenação (`sort_by`/`sort_order`) e filtros (`overdue`, `tag`, `due_before`, `due_after`).
- **Processamento em background & Resiliência:** exportação assíncrona de tarefas em CSV/JSON (`202 Accepted` + download) e rate limiting via Redis (`REDIS_URL`) com fallback automático em memória.
- **Observabilidade:** `X-Request-ID`, logs em `text` ou `json`, `X-Process-Time-Ms`, headers `X-RateLimit-*`, headers HTTP de segurança e probes `/health/live` e `/health/ready` (`503` se o banco cair).

## Como executar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn task_manager_api:app --reload
```

Com Docker + PostgreSQL + Redis:

```bash
docker compose up --build
```

## Fluxo de Autenticação (exemplo)

```bash
# 1. Registrar
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","password":"StrongPass123","full_name":"Dev User"}'

# 2. Login -> retorna access_token e refresh_token
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","password":"StrongPass123"}'

# 3. Usar endpoints protegidos
curl -s http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <ACCESS_TOKEN>"

# 4. Rotacionar refresh token / fazer logout
curl -s -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<REFRESH_TOKEN>"}'
```

## Configuração

Veja `.env.example`. Principais variáveis:

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `ENVIRONMENT` | `development` | Em `production`, falha ao iniciar se `SECRET_KEY` for a padrão |
| `DATABASE_URL` | `sqlite:///./taskflow_v2.db` | URL SQLAlchemy (SQLite ou PostgreSQL) |
| `SECRET_KEY` | chave dev (só dev) | Chave JWT HS256 (mín. 32 caracteres) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | `15` / `7` | Validade dos tokens |
| `REDIS_URL` | *(vazio)* | Opcional; ativa rate limit distribuído (fallback em memória) |
| `CORS_ORIGINS` | `*` | Origens permitidas separadas por vírgula |
| `TRUST_PROXY_HEADERS` | `false` | Lê `X-Forwarded-For` atrás de proxy |
| `AUTO_CREATE_TABLES` | `true` | Defina `false` em produção com Alembic |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `text` | Nível e formato (`text` ou `json`) |

## Endpoints (`/api/v1`)

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health`, `/health/live`, `/health/ready` | Probes de saúde (públicos) |
| POST | `/api/v1/auth/register`, `/login`, `/refresh`, `/logout` | Fluxo completo JWT + refresh rotation |
| GET | `/api/v1/auth/me` | Perfil do usuário autenticado |
| GET | `/api/v1/stats` | Indicadores consolidados do tenant |
| POST / GET / PATCH / DELETE | `/api/v1/projects[/{id}]` | CRUD de projetos |
| POST / GET / PATCH / DELETE | `/api/v1/tasks[/{id}]` | CRUD de tarefas, filtros, ordenação e *optimistic locking* |
| POST / GET / DELETE | `/api/v1/tasks/{id}/comments[/{comment_id}]` | Comentários da tarefa |
| POST / GET / DELETE | `/api/v1/tags[/{tag_id}]` | Gerenciar tags |
| POST / GET | `/api/v1/exports[/{id}][/download]` | Exportação assíncrona em CSV/JSON |

## Qualidade

```bash
make check       # ruff check, ruff format --check, mypy --strict e pytest com cobertura (>= 95%)
make migrate     # alembic upgrade head
```
