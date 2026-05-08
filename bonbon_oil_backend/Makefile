.PHONY: help install dev up down logs migrate migrate-new seed superadmin test lint format typecheck clean

PYTHON := python
DOCKER_COMPOSE := docker compose
ALEMBIC := alembic

help:
	@echo "Bon Bon Oil ERP Backend"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Development:"
	@echo "  install        Install Python dependencies"
	@echo "  dev            Start all services in development mode"
	@echo "  up             Start services detached"
	@echo "  down           Stop and remove containers"
	@echo "  logs           Tail API container logs"
	@echo ""
	@echo "Database:"
	@echo "  migrate        Apply pending Alembic migrations"
	@echo "  migrate-new    Create a new migration (MSG=<description>)"
	@echo "  seed           Load seed reference data"
	@echo "  superadmin     Create initial super admin user"
	@echo ""
	@echo "Quality:"
	@echo "  test           Run test suite"
	@echo "  test-unit      Run unit tests only"
	@echo "  test-int       Run integration tests only"
	@echo "  lint           Run ruff linter"
	@echo "  format         Run ruff formatter"
	@echo "  typecheck      Run mypy type checker"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean          Remove __pycache__ and .pytest_cache"

install:
	pip install -e ".[dev]"
	pre-commit install

dev:
	$(DOCKER_COMPOSE) up --build

up:
	$(DOCKER_COMPOSE) up -d --build

down:
	$(DOCKER_COMPOSE) down

logs:
	$(DOCKER_COMPOSE) logs -f api

migrate:
	$(ALEMBIC) upgrade head

migrate-new:
	@test -n "$(MSG)" || (echo "Usage: make migrate-new MSG='describe the change'"; exit 1)
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

seed:
	$(PYTHON) scripts/seed_data.py

superadmin:
	$(PYTHON) scripts/create_superadmin.py

test:
	pytest

test-unit:
	pytest -m unit

test-int:
	pytest -m integration

lint:
	ruff check app tests

format:
	ruff format app tests

typecheck:
	mypy app

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
