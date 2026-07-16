# ---- stage 1: build the React control panel --------------------------------
FROM node:20-slim AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # -> /ui/dist

# ---- stage 2: the app ------------------------------------------------------
# Official Playwright image: Chromium + all system deps preinstalled. Avoids the
# classic "missing shared libraries" failure on Railway/Render.
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

COPY backend ./backend
COPY scripts ./scripts
COPY alembic.ini ./
# built SPA served same-origin by FastAPI (see main.py); path matches
# FRONTEND_DIST = <repo>/frontend/dist
COPY --from=frontend /ui/dist ./frontend/dist

ENV UNDERSTUDY_DATA=/srv/data \
    PYTHONPATH=/srv/backend \
    PORT=8000

# The demo seeds itself on boot (main.py lifespan). Bind BASE_URL to the
# container's own port so the executor drives the same process that serves the
# mock apps — no external round-trip, works regardless of the public URL.
CMD ["sh", "-c", "export UNDERSTUDY_BASE_URL=http://127.0.0.1:${PORT} && exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT}"]
