# One image with the gateway and the built web UI (served at `/`).
#   docker compose up --build        (see README.md)
#
# Stage 1 builds the React page; stage 2 installs the backend and copies the page next to it in
# the same relative place it has in the repository (code/frontend/dist), which is where
# gateway/web.py looks for it.

FROM node:24-alpine AS web
WORKDIR /src/code/frontend
COPY code/frontend/package.json code/frontend/package-lock.json ./
RUN npm ci
COPY code/frontend/ ./
RUN npm run build


FROM python:3.12-slim AS app
RUN pip install --no-cache-dir uv==0.13.0 \
    && useradd --create-home --uid 10001 app

WORKDIR /app/code/backend
COPY code/backend/pyproject.toml code/backend/uv.lock code/backend/.python-version ./
# Only the runtime dependencies; the lock file keeps the versions identical to development.
RUN UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --frozen --no-dev
ENV PATH="/opt/venv/bin:$PATH"

COPY code/backend/ ./
COPY --from=web /src/code/frontend/dist /app/code/frontend/dist

# Traces go to ./data (SQLite); mount a volume there to keep them across restarts.
RUN mkdir -p data && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "gateway.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
