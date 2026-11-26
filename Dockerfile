FROM python:3.12-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.12-slim AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    DATABASE_URL=sqlite:////var/lib/taskflow/taskflow_v2.db
WORKDIR /app
RUN groupadd --gid 10001 taskflow && \
    useradd --uid 10001 --gid 10001 --no-create-home taskflow && \
    install -d -o taskflow -g taskflow /var/lib/taskflow
COPY --from=builder /opt/venv /opt/venv
COPY taskflow ./taskflow
COPY migrations ./migrations
COPY alembic.ini task_manager_api.py ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).close()"]
CMD ["uvicorn", "task_manager_api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
