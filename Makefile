# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


.PHONY: help install install-deps emulator server ui dev build-ui doctor test lint format typecheck clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install Python and research UI dependencies
	@uv sync --dev
	@npm ci --prefix apps/research_ui

install-deps: ## Install system dependencies (ADB, FFmpeg, scrcpy, Python, uv, Node)
	@bash scripts/install_deps.sh

emulator: ## Start the dedicated AndroidWorld emulator (emulator-5554)
	@bash scripts/start_androidworld_emulator.sh

server: ## Start the harness backend on http://127.0.0.1:8000
	@uv run python -m apps.harness_server.server --host 127.0.0.1 --port 8000

ui: ## Start the research UI dev server on http://127.0.0.1:5173
	@npm run dev --prefix apps/research_ui

dev: ## Start backend and research UI together
	@bash start.sh

build-ui: ## Build the research UI; the backend then serves it on port 8000
	@npm run build --prefix apps/research_ui

doctor: ## Check system prerequisites, device status and configuration
	@uv run artemis doctor

test: ## Run deterministic tests that need no device or credentials
	@uv run pytest

lint: ## Run linting checks
	@uv run ruff format --check
	@uv run ruff check

format: ## Format code
	@uv run ruff format
	@uv run ruff check --fix

typecheck: ## Type-check Python and the research UI
	@uv run pyright --project pyright-core.json
	@cd apps/research_ui && npx tsc -b --noEmit

clean: ## Remove caches and build output (keeps traces)
	@rm -rf .pytest_cache .ruff_cache build dist apps/research_ui/dist
	@find . -path ./apps/research_ui/node_modules -prune -o -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
