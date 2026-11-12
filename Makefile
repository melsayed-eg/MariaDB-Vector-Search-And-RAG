
# Convenient development and reproduction commands for WikiRAG.

.DEFAULT_GOAL := help

PYTHON := uv run --extra dev --extra embeddings python
SNAPSHOT := data/snapshot/wikipedia_snapshot.jsonl

.PHONY: help check-env check-snapshot up down ps version \
        setup setup-test-db test test-unit test-db lint eval

help:
	@echo "WikiRAG development commands:"
	@echo "  make setup          Install, start MariaDB, initialize and ingest"
	@echo "  make up             Start MariaDB"
	@echo "  make down           Stop MariaDB without deleting volumes"
	@echo "  make ps             Show database containers"
	@echo "  make version        Show MariaDB server version"
	@echo "  make setup-test-db  Prepare the isolated integration-test database"
	@echo "  make test           Run all tests"
	@echo "  make test-unit      Run unit tests"
	@echo "  make test-db        Run database integration tests"
	@echo "  make lint           Check Python linting and formatting"
	@echo "  make eval           Regenerate retrieval evaluation reports"

check-env:
	@if [ ! -f .env ]; then \
		echo "Error: .env is missing." >&2; \
		echo "Copy .env.example to .env and configure your credentials." >&2; \
		exit 1; \
	fi
	@if grep -Eq '^(DB_PASSWORD|MARIADB_ROOT_PASSWORD)=replace_with_' .env; then \
		echo "Error: Replace the example database passwords in .env." >&2; \
		exit 1; \
	fi

check-snapshot:
	@if [ ! -s "$(SNAPSHOT)" ]; then \
		echo "Error: Wikipedia snapshot is missing or empty: $(SNAPSHOT)" >&2; \
		exit 1; \
	fi

up: check-env
	docker compose up -d --wait db

down:
	docker compose down

ps:
	docker compose ps

version: check-env
	docker compose exec -T db sh -c 'MYSQL_PWD="$$MARIADB_ROOT_PASSWORD" mariadb -u root -e "SELECT VERSION() AS mariadb_version;"'

# Install dependencies and reproduce the Wikipedia database.
# Existing schemas are verified, and unchanged articles are skipped.
setup: check-env check-snapshot
	uv sync --extra dev --extra embeddings --locked
	$(MAKE) up
	$(PYTHON) -m wikirag.cli init-db
	$(PYTHON) -m wikirag.cli ingest --snapshot "$(SNAPSHOT)"
	$(MAKE) setup-test-db
	$(PYTHON) -m wikirag.cli stats

# Create or verify the separate test database without resetting it.
setup-test-db:
	bash scripts/create-test-db.sh

test:
	uv run --extra dev python -m pytest -q

test-unit:
	uv run --extra dev python -m pytest -m unit -q

test-db:
	uv run --extra dev python -m pytest -m integration -q

lint:
	uv run --extra dev ruff check .
	uv run --extra dev ruff format --check .

# Evaluation regenerates reports for the full Wikipedia corpus.
eval:
	$(PYTHON) scripts/run_retrieval_benchmark.py
