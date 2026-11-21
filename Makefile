.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help setup up down logs org demo admin loadtest lan lan-off catalog catalog-export catalog-full migrate migration test test-backend test-frontend e2e lint format typecheck api-types trust-cert clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Create .env and install local dependencies
	@test -f .env || cp .env.example .env
	cd backend && uv sync
	cd frontend && npm ci

up: ## Start the whole platform (https://localhost)
	$(COMPOSE) up --build -d
	@echo "App: https://localhost  ·  Mail: http://localhost:8025  ·  S3: http://localhost:8333"

down: ## Stop all services
	$(COMPOSE) down

logs: ## Follow the logs of all services
	$(COMPOSE) logs -f --tail=100

org: ## Create an organization: make org name="Atelier Example" email=admin@example.com
	$(COMPOSE) exec api python -m app.cli create-organization --name "$(name)" --admin-email "$(email)"

demo: ## Create a demo organization with invented data and print its logins
	$(COMPOSE) exec api python -m app.cli seed-demo

admin: ## Make an account a platform admin: make admin email=you@example.com
	$(COMPOSE) exec api python -m app.cli grant-platform-admin --email "$(email)"

loadtest: ## Load test against the stack: make loadtest email=... password=...
	cd backend && uv run python scripts/loadtest.py --email "$(email)" --password "$(password)"

CATALOG := cd tools/feature_catalog && uv run python -m feature_catalog

catalog: ## Check the feature catalog against the code (static; see docs/feature-katalog.md)
	$(CATALOG) check --root ../..

catalog-export: ## Refresh catalog/discovered/ after changing routes, jobs, commands or pages
	cd backend && UPDATE_SNAPSHOTS=1 uv run pytest -q tests/test_catalog_export.py
	cd frontend && UPDATE_SNAPSHOTS=1 npx vitest run src/app/routes.catalog.test.tsx

catalog-full: ## Run all tests with reports, check the catalog and build catalog/dist/index.html
	rm -rf reports && mkdir -p reports
	cd backend && uv run pytest -q -o junit_suite_name=backend --junitxml=../reports/backend.xml
	cd frontend && JUNIT_DIR=$(CURDIR)/reports npm test
	cd frontend && JUNIT_DIR=$(CURDIR)/reports npx playwright test --trace off
	cd tools/feature_catalog && uv run pytest -q --junitxml=../../reports/catalog-tool.xml
	$(CATALOG) build --root ../.. --reports ../../reports --out catalog/dist
	$(CATALOG) check --root ../.. --reports ../../reports

migrate: ## Apply database migrations
	$(COMPOSE) exec api alembic upgrade head

migration: ## Create a migration: make migration m="add projects"
	$(COMPOSE) exec api alembic revision -m "$(m)"

test: test-backend test-frontend ## Run all unit and integration tests

test-backend: ## Backend tests (starts a PostgreSQL test container)
	cd backend && uv run pytest

test-frontend: ## Frontend unit tests
	cd frontend && npm test

e2e: ## Playwright end-to-end tests (desktop and phone)
	cd frontend && npx playwright test --trace off

lint: ## Lint backend and frontend
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint && npm run format:check

format: ## Format all code
	cd backend && uv run ruff format . && uv run ruff check --fix .
	cd frontend && npm run format

typecheck: ## Static type checks
	cd backend && uv run mypy app tests
	cd frontend && npm run typecheck

api-types: ## Regenerate the frontend API client types from the backend
	cd backend && PYTHONPATH=. uv run python scripts/export_openapi.py ../frontend/openapi.json
	cd frontend && npm run api:generate

lan: ## Make the app reachable from phones in the same Wi-Fi (my-mac.local)
	./scripts/lan.sh

lan-off: ## Back to https://localhost only
	./scripts/lan.sh off

trust-cert: ## Export Caddy's local root certificate to ./caddy-root.crt (then trust it, see README)
	$(COMPOSE) cp proxy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
	@echo "Saved caddy-root.crt. Add it to your system's trusted certificates (see README)."

clean: ## Stop services and delete all local data volumes
	$(COMPOSE) down -v
