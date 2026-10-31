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


.PHONY: help install install-deps emulator doctor test lint format typecheck clean

help: ## Show available benchmark development commands
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install Python dependencies
	uv sync --dev

install-deps: ## Install Android device tools
	bash scripts/install_deps.sh

emulator: ## Start the AndroidWorld emulator
	bash scripts/start_androidworld_emulator.sh

doctor: ## Check host and Android device readiness
	uv run bagel doctor

test: ## Run deterministic tests
	uv run pytest

lint: ## Check style and imports
	uv run ruff check
	uv run ruff format --check

format: ## Format source files
	uv run ruff format

typecheck: ## Check the benchmark and device interfaces
	uv run pyright --project pyright-core.json

clean: ## Remove generated Python build output
	rm -rf .pytest_cache .ruff_cache build dist
