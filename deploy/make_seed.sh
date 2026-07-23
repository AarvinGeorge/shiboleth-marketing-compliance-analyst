#!/bin/sh
# meta: builds the demo-data seed for the Adlign production stack (deploy plan
# 2026-07-13). Dumps the LOCAL dev database (the certified TurboTax runs,
# flags, clusters, issue groupings, dispositions, scorecard) into
# deploy/seed/01_demo.sql.gz — the pgvector container auto-loads it on the
# VPS's FIRST boot (empty pgdata volume only; wipe with
# `docker compose -f docker-compose.prod.yml down -v` to re-seed).
# Also prints the run ids to paste into PROTECTED_RUN_IDS in the server .env.
set -e
cd "$(dirname "$0")/.."

mkdir -p deploy/seed
docker exec shiboleth-postgres pg_dump -U shiboleth -d shiboleth \
  --no-owner --no-privileges | gzip > deploy/seed/01_demo.sql.gz

echo "Seed written: $(ls -lh deploy/seed/01_demo.sql.gz | awk '{print $9, "("$5")"}')"
echo
echo "PROTECTED_RUN_IDS for the server .env (all runs in this seed):"
docker exec shiboleth-postgres psql -U shiboleth -d shiboleth -t -A \
  -c "select string_agg(id, ',') from runs;"
