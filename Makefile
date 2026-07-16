# Understudy — common tasks. `make install` then `make dev`.
.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help install seed dev test lint typecheck build ci eval clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create venv, install backend + frontend deps, browser, build UI
	python3 -m venv $(VENV)
	$(PIP) install -q -r requirements-dev.txt
	$(PY) -m playwright install chromium
	cd frontend && npm install && npm run build

seed: ## Seed the demo trace + workflow into the database
	$(PY) scripts/seed_demo.py

dev: ## Run the API + built UI on http://localhost:8000
	$(VENV)/bin/uvicorn app.main:app --app-dir backend --reload

test: ## Run the test suite (incl. the real-browser e2e)
	$(PY) -m pytest -q

lint: ## Lint with ruff
	$(VENV)/bin/ruff check backend scripts tests

typecheck: ## Type-check with mypy
	$(VENV)/bin/mypy backend

build: ## Build the frontend
	cd frontend && npm run build

ci: lint typecheck test ## Everything CI runs (backend side)

eval: ## Run the success-rate harness across all invoices
	$(PY) scripts/eval.py

clean: ## Remove the local database and build artifacts
	rm -f data/understudy.db
	rm -rf frontend/dist
