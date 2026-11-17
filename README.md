# TaskFlow Backend API v2.0

API RESTful desenvolvida em Python com FastAPI, SQLAlchemy e Pydantic v2para gerenciamento de projetos e tarefas.

 Funcionalidades Principais

- CRUD Completo & Relacional: Projetos (1:N) e Tarefas com exclusão em cascata.
- Segurança & Rate Limiting: Autenticação via X-API-Key com validação criptográfica em tempo constante e limitação de requisições por IP (429 Too Many Requests).
- Observabilidade: Logs estruturados e cabeçalho X-Process-Time-Ms em todas as respostas.
- Métricas & Filtros:
- Paginação (skip/limit), busca textual, filtros combinados e dashboard consolidado em /api/v1/stats.
- Testes Integrados: Suíte automatizada de ponta a ponta embutida no próprio script.

 Como Executar Localmente

1. Instale as dependências:
   ```bash
   
