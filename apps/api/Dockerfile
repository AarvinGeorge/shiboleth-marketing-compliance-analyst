# meta: production image for the Adlign API (deploy plan 2026-07-13).
# Source lives at /app/code/apps/api so config.py's parents[4] REPO_ROOT
# resolves to /app/code and the optional corpus mount lands at
# /app/ground-truth (mirrors the dev layout). Chromium via playwright is
# for crawl4ai live-mode crawling. Entrypoint migrates (alembic upgrade
# head — a no-op on the seeded demo DB) then serves uvicorn.

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app/code/apps/api

# dependency layer (cache-friendly: only lockfile changes invalidate it)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# browser layer for crawl4ai (big; kept above the source layer on purpose)
RUN .venv/bin/playwright install --with-deps chromium

COPY . .

ENV PATH="/app/code/apps/api/.venv/bin:$PATH" \
    PYTHONPATH=/app/code/apps/api/src

EXPOSE 8000
CMD ["./docker-entrypoint.sh"]
