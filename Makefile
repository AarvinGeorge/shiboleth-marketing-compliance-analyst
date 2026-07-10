# meta: developer entry points for the Shiboleth monorepo (07 §5 scaffold).

API_DIR = apps/api
WEB_DIR = apps/web

.PHONY: db-up db-down dev-api dev-web test lint smoke evals

db-up:
	docker compose up -d --wait postgres

db-down:
	docker compose down

dev-api:
	cd $(API_DIR) && uv run uvicorn shiboleth.main:app --reload --port 8000

dev-web:
	cd $(WEB_DIR) && npm run dev

test:
	cd $(API_DIR) && uv run pytest -q

lint:
	cd $(API_DIR) && uv run ruff check src tests

smoke:
	cd $(API_DIR) && uv run python -m shiboleth.smoke

evals:
	@echo "E3 harness lands at M3 (08 §4)." && exit 1
