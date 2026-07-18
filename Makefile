# Understudy — developer commands.
#
# Two ways to run:
#   • Docker (recommended): `make dev` brings up the full stack with live reload.
#   • Native:              `make install` then `make dev-native`.
.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help \
        dev up down restart logs ps build sh-backend sh-frontend \
        install dev-native seed test test-docker lint typecheck lint-imports \
        ci eval clean nuke

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---------- docker (recommended) ----------
dev: ## Build + start the full stack (backend :8000, frontend :5173) with live reload
	docker compose up -d --build
	@echo "✓ Understudy is up.  app: http://localhost:5173  api: http://localhost:8000"

up: ## Start the stack
	docker compose up -d

down: ## Stop the stack (keep volumes)
	docker compose down

restart: ## Restart the stack
	docker compose restart

build: ## Rebuild images without starting
	docker compose build

ps: ## List running services
	docker compose ps

logs: ## Tail logs from all services
	docker compose logs -f --tail=100

sh-backend: ## Shell into the backend container
	docker compose exec backend bash

sh-frontend: ## Shell into the frontend container
	docker compose exec frontend sh

test-docker: ## Run the test suite inside the backend container
	docker compose exec backend python -m pytest -q

# ---------- native (no docker) ----------
install: ## Create venv, install backend + frontend deps, browser, build UI
	python3 -m venv $(VENV)
	$(PIP) install -q -r requirements-dev.txt
	$(PY) -m playwright install chromium
	cd frontend && npm install && npm run build

dev-native: ## Run API + built UI on http://localhost:8000 (no docker)
	$(VENV)/bin/uvicorn app.main:app --app-dir backend --reload

seed: ## Seed the demo traces + workflows into the database
	$(PY) scripts/seed_demo.py

# ---------- quality gates ----------
test: ## Run the test suite (incl. the real-browser e2e)
	$(PY) -m pytest -q

lint: ## Lint with ruff
	$(VENV)/bin/ruff check backend scripts tests

typecheck: ## Type-check with mypy
	$(VENV)/bin/mypy backend

lint-imports: ## Enforce the layered-architecture import contracts
	PYTHONPATH=backend UNDERSTUDY_AGENT_MOCK=1 $(VENV)/bin/lint-imports

ci: lint typecheck lint-imports test ## Everything CI runs

eval: ## Run the success-rate harness across all invoices
	$(PY) scripts/eval.py

# ---------- cleanup ----------
clean: ## Remove the local database and build artifacts
	rm -f data/understudy.db
	rm -rf frontend/dist

nuke: ## Stop the stack and delete its volumes (loses DB + node_modules)
	docker compose down -v --remove-orphans
