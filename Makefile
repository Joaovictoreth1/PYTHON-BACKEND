PYTHON ?= .venv/bin/python
.DEFAULT_GOAL := check

.PHONY: install migrate run lint type test audit check build

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements-dev.txt

migrate:
	$(PYTHON) -m taskflow.migrate

run:
	$(PYTHON) -m uvicorn task_manager_api:app --reload --no-access-log

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

type:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest --cov=taskflow --cov-report=term-missing

audit:
	$(PYTHON) -m pip_audit -r requirements.txt -r requirements-dev.txt

check: lint type test

build:
	docker build -t taskflow:local .
