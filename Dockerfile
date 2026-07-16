# Official Playwright image: Chromium + all system deps preinstalled.
# Avoids the classic "missing shared libraries" failure on Railway/Render.
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

COPY backend ./backend
COPY scripts ./scripts

ENV UNDERSTUDY_DATA=/srv/data \
    PYTHONPATH=/srv/backend \
    PORT=8000

# seed the demo trace + workflow so the deployed instance is usable immediately
RUN python scripts/seed_demo.py || true

# --shm-size is set by the platform; --disable-dev-shm-usage is the fallback
# handled inside Playwright launch args if needed.
CMD uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT}
