.PHONY: dev test cov lint format typecheck migrate check

PYTHON ?= .venv/bin/python

dev:
	$(PYTHON) -m uvicorn task_manager_api:app --reload

test:
	$(PYTHON) -m pytest

cov:
	$(PYTHON) -m pytest --cov=app --cov-report=term-missing

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

format:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

typecheck:
	.venv/bin/mypy

migrate:
	.venv/bin/alembic upgrade head

check: lint typecheck cov
