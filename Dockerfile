FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip==26.3 \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && mkdir /data \
    && chown 10001:10001 /data

COPY task_manager_api.py taskflow_config.py taskflow_models.py taskflow_rate_limit.py ./

USER 10001:10001
ENV DATABASE_URL=sqlite:////data/taskflow_v2.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=3).close()"]
CMD ["uvicorn", "task_manager_api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
