#!/bin/sh
# meta: API container entrypoint — migrate then serve. --proxy-headers +
# forwarded-allow-ips '*' is safe here because the API port is never
# published; only Caddy (inside the compose network) can reach it, and the
# rate limiter keys on the X-Forwarded-For hop Caddy sets.
set -e

alembic upgrade head
exec uvicorn adlign.main:app --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips '*'
