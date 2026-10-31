#!/usr/bin/env bash
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


# Start the harness backend (port 8000) and the research UI dev server (port 5173).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

[ -d apps/research_ui/node_modules ] || npm ci --prefix apps/research_ui

uv run python -m apps.harness_server.server --host 127.0.0.1 --port 8000 &
server=$!
trap 'kill "$server" 2>/dev/null || true' EXIT INT TERM

echo "Backend: http://127.0.0.1:8000   Research UI: http://127.0.0.1:5173"
npm run dev --prefix apps/research_ui
