#!/usr/bin/env bash
# build.sh - orchestrate frontend + Python package builds
# Usage: bash scripts/build.sh
# Requires: node/npm (for frontend), hatch (for Python package)
# Windows: run via WSL or Git Bash; CI runs on Linux

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
FRONTEND_DIR="${PROJECT_ROOT}/llm_pipeline/ui/frontend"
DIST_INDEX="${FRONTEND_DIR}/dist/index.html"

printf '[build] frontend dir: %s\n' "${FRONTEND_DIR}"

cd -- "${FRONTEND_DIR}"
printf '[build] npm ci\n'
npm ci

printf '[build] npm run build\n'
npm run build

cd -- "${PROJECT_ROOT}"

if [[ ! -f "${DIST_INDEX}" ]]; then
  printf '[build] ERROR: dist/index.html not found after npm build -- aborting\n' >&2
  exit 1
fi

printf '[build] dist/index.html verified\n'
printf '[build] hatch build\n'
hatch build

printf '[build] done\n'
