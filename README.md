# TaskFlow Backend API

TaskFlow é uma API REST para organizar projetos e tarefas. FastAPI e Pydantic v2 validam as requisições; SQLAlchemy 2 persiste em SQLite; Alembic gerencia o schema. A API usa Python 3.12 e Uvicorn.

## Arquitetura

- `task_manager_api:app` é o ponto de entrada ASGI compatível com a versão anterior; a fábrica fica em `taskflow/main.py`.
- `taskflow/routers/` traduz o contrato HTTP. `services.py` valida operações de domínio e define os limites de transação. `repositories.py` concentra consultas, agregações e mutações SQL.
- `models.py` e `database.py` mantêm os modelos, a sessão por requisição, a integridade referencial e a conversão de timestamps para UTC. A remoção de um projeto usa `ON DELETE CASCADE`; excluir a associação por PATCH preserva a tarefa.
- `migrations/` controla o schema. O servidor não cria tabelas ao importar o aplicativo.

## Desenvolvimento local

```sh
make install
cp .env.example .env
export API_SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
make migrate
make run
```

Abra [Swagger UI](http://localhost:8000/docs) ou consulte `/health`. O exemplo acima configura a chave apenas no shell atual; mantenha credenciais fora do Git. O servidor inicia sem uma chave em desenvolvimento, mas nega todas as rotas privadas. O comando ASGI continua sendo `.venv/bin/python -m uvicorn task_manager_api:app`.

| Variável | Padrão | Uso |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development`, `test` ou `production`. Use `production` em implantações. |
| `API_SECRET_KEY` | nenhuma | Segredo compartilhado, ASCII imprimível sem espaços; produção exige pelo menos 32 caracteres. Gere um valor aleatório e use um gerenciador de segredos. |
| `DATABASE_URL` | `sqlite:///./taskflow_v2.db` | URL SQLAlchemy. SQLite deve ser persistente em produção. O container usa `sqlite:////var/lib/taskflow/taskflow_v2.db`. |
| `CORS_ORIGINS` | `[]` | Lista JSON de origens HTTP(S) completas, sem barra final, por exemplo `["https://app.example.com"]`. |
| `RATE_LIMIT_MAX_REQUESTS` | `120` | Máximo por IP em cada janela. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Janela móvel em segundos. |
| `RATE_LIMIT_MAX_CLIENTS` | `4096` | Máximo de IPs ativos por processo. Ao esgotar a capacidade, novos IPs recebem 429 até um registro expirar. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` ou `ERROR`. Logs de requisição não incluem chaves, corpos nem parâmetros. |

As variáveis do processo têm precedência sobre `.env`. Esta API foi desenhada para **um domínio de confiança**: a chave dá acesso a todos os recursos. Não entregue a chave a clientes não confiáveis, não a inclua em frontend público e não compartilhe uma instância entre tenants. Coloque a API atrás de HTTPS, restrinja o acesso de rede e aplique limites distribuídos no proxy se houver mais de um processo. Ao usar cabeçalhos de encaminhamento, configure o Uvicorn para confiar apenas nos endereços dos seus proxies. SQLite é indicado para uma instância de escrita por volume; não compartilhe o arquivo por NFS entre réplicas.

## API

```sh
base=http://localhost:8000
curl -fsS "$base/health"
curl -fsS "$base/api/v1/projects" -H "X-API-Key: $API_SECRET_KEY" \
  -H 'Content-Type: application/json' -d '{"name":"Plataforma Core"}'
curl -fsS "$base/api/v1/tasks" -H "X-API-Key: $API_SECRET_KEY" \
  -H 'Content-Type: application/json' -d '{"title":"Configurar CI/CD","priority":"urgente"}'
curl -fsS "$base/api/v1/tasks?status=pendente&sort=oldest&skip=0&limit=10" \
  -H "X-API-Key: $API_SECRET_KEY"
curl -fsS "$base/api/v1/stats" -H "X-API-Key: $API_SECRET_KEY"
```

- `POST/GET /api/v1/projects` cria/lista projetos; `DELETE /api/v1/projects/{id}` remove projeto e tarefas dependentes. A lista continua sendo um array; novos clientes podem informar `skip`, `limit` (1–100), `sort=newest|oldest` e `search`.
- `POST/GET /api/v1/tasks` cria/lista tarefas. A lista retorna `total`, `skip`, `limit` e `items`, aceita `status`, `priority`, `project_id`, `assignee`, `search` e `sort`. A busca usa texto literal, não curingas SQL. `GET/PATCH/DELETE /api/v1/tasks/{id}` opera em uma tarefa.
- `PATCH` modifica só os campos enviados. `null` pode limpar `description`, `assignee`, `due_date` e `project_id`. Para evitar sobrescrever uma atualização concorrente, reenvie o `ETag` recebido no GET no cabeçalho `If-Match`; um valor desatualizado retorna 412. Um PATCH sem esse cabeçalho mantém o comportamento anterior.
- Erros preservam `detail` e incluem `error.code` e `error.path`, por exemplo `{"detail":"Projeto não encontrado.","error":{"code":"not_found","path":"/api/v1/projects/999"}}`. Projetos com nomes duplicados retornam 409; clientes limitados recebem `Retry-After`. `/health` retorna 503 quando as tabelas ainda não estão disponíveis.

## Implantação e migrações

Deploy novo: configure o segredo e o armazenamento persistente, execute `python -m taskflow.migrate` **uma vez antes de subir a API**, e só encaminhe tráfego quando `/health` retornar 200. Migrações e serviço são containers separados no Compose:

```sh
docker compose up --build -d
docker compose ps
curl -fsS http://127.0.0.1:8000/health
```

Para atualizar um banco SQLite da versão monolítica, pare escritores e faça um backup consistente (por exemplo, `sqlite3 taskflow_v2.db '.backup taskflow_v2.backup.db'`). Teste primeiro em uma cópia:

```sh
export DATABASE_URL=sqlite:///./taskflow_v2.backup.db
.venv/bin/python -m taskflow.migrate --adopt-legacy
.venv/bin/alembic current
```

A adoção valida schema, índices, enums armazenados e chaves estrangeiras antes de marcar a revisão inicial e criar os índices novos. Se houver inconsistências ou referências órfãs, corrija os dados no banco original antes de refazer o backup e tentar novamente; nada é removido automaticamente. Verifique contagens, amostras de registros e a aplicação na cópia antes de repetir no banco que será implantado. Preserve o backup para recuperação; não faça downgrade para o banco vazio em produção. Rotacione quaisquer chaves de desenvolvimento utilizadas na versão anterior.

## Verificação

```sh
make check  # Ruff, formatação, mypy estrito e pytest com gate de cobertura
make audit  # advisories para dependências de runtime e desenvolvimento
make build  # imagem multi-stage, usuário sem privilégios
```

Os testes fazem requisições ASGI reais via HTTPX, usam um banco SQLite isolado por teste e exercitam migrações, validação, autenticação, integridade, concorrência, limites e erros. O GitHub Actions roda as mesmas verificações e testa a imagem construída.
