#!/usr/bin/env bash
# Dev/demo launcher: activate the venv, load .env (for ANTHROPIC_API_KEY), and
# serve the API + built SPA on one port.
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
set -a; [ -f .env ] && . ./.env; set +a
exec uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
