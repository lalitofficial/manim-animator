# Manim Animator — developer task runner.
# Every target is a one-liner so you (and the coding agent) never have to
# remember invocations. `make` or `make help` lists them.

PORT ?= 8000
HOST ?= 127.0.0.1
BIOME := npx --yes @biomejs/biome

.DEFAULT_GOAL := help

.PHONY: help setup hooks dev lint fmt fix typecheck test check web web-fix bench lock clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Create/sync the venv with all deps (runtime + dev) from the lockfile
	uv sync
	$(MAKE) hooks

hooks: ## Install the git pre-commit hooks
	uv run pre-commit install

dev: ## Run the API + live board with autoreload (http://$(HOST):$(PORT))
	uv run uvicorn app:app --reload --app-dir backend --host $(HOST) --port $(PORT)

lint: ## Lint Python (ruff) — report only
	uv run ruff check backend tests

fmt: ## Format Python (ruff format) + sort imports
	uv run ruff format backend tests
	uv run ruff check --select I --fix backend tests

fix: ## Auto-fix everything ruff safely can, then format
	uv run ruff check --fix backend tests
	uv run ruff format backend tests

typecheck: ## Static type check (pyright)
	uv run pyright

test: ## Run the test suite
	uv run pytest

bench-pos: ## Run the Positioning benchmark (the Phase-1 ruler)
	PYTHONPATH=backend uv run python -m engine.bench

bench-draw: ## Render the drawing scenes to build/engine/*.svg + check the Phase-2 gate
	PYTHONPATH=backend uv run python -m engine.bench_draw

vendor-icons: ## Vendor more Tabler line icons (MIT) into the catalog + alias index
	PYTHONPATH=backend uv run python scripts/vendor_tabler.py

sync-excalidraw: ## Sync ALL Excalidraw libraries (MIT) into normalized candidate packs (pass N=10 to limit)
	PYTHONPATH=backend uv run python scripts/sync_excalidraw.py $(N)

sync-bioicons: ## Sync Bioicons scientific SVGs into COLORED candidate packs (pass D=biology|chemistry, N=20 to limit)
	PYTHONPATH=backend uv run python scripts/sync_bioicons.py $(D) $(N)

lesson: ## Render a full lesson end-to-end (pass T="a topic") -> build/engine/lesson.svg
	PYTHONPATH=backend uv run python -m engine.bench_lesson $(T)

ui: ## Run the Svelte Studio dev server (proxies /api to uvicorn on :8000)
	cd frontend && npm run dev

ui-build: ## Build the Studio -> frontend/dist (served by the backend at /)
	cd frontend && npm install && npm run build

check: lint test web ## Everything CI gates on: lint + tests + JS (blocking)
	@echo "── types (advisory, non-blocking) ──"
	-@uv run pyright

web: ## Lint/format-check the board frontend (Biome)
	$(BIOME) check board

web-fix: ## Auto-fix + format the board frontend (Biome)
	$(BIOME) check --write board

bench: ## Live-board latency benchmark (pass T="a topic")
	uv run python backend/bench_live.py $(T)

lock: ## Re-resolve the lockfile and regenerate requirements.txt for compatibility
	uv lock
	uv export --no-dev --no-hashes --format requirements-txt -o requirements.txt

clean: ## Remove caches and generated media
	rm -rf .ruff_cache .pytest_cache .mypy_cache **/__pycache__ media backend/media
