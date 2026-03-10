# IMPLEMENTATION - STEP 4: BUILD SCRIPT
**Status:** completed

## Summary
Created `scripts/build.sh` to orchestrate frontend npm build then hatch Python package build, with fail-fast verification that `dist/index.html` exists before packaging.

## Files
**Created:** `scripts/build.sh`
**Modified:** none
**Deleted:** none

## Changes
### File: `scripts/build.sh`
New file. Chains `npm ci`, `npm run build`, dist verification, and `hatch build`.

```
# Before
[file did not exist]

# After
#!/usr/bin/env bash
# build.sh - orchestrate frontend + Python package builds
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
FRONTEND_DIR="${PROJECT_ROOT}/llm_pipeline/ui/frontend"
DIST_INDEX="${FRONTEND_DIR}/dist/index.html"

cd -- "${FRONTEND_DIR}"
npm ci
npm run build

cd -- "${PROJECT_ROOT}"

if [[ ! -f "${DIST_INDEX}" ]]; then
  printf '[build] ERROR: dist/index.html not found after npm build -- aborting\n' >&2
  exit 1
fi

hatch build
```

## Decisions
### Script location detection
**Choice:** `SCRIPT_DIR` via `$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)`
**Rationale:** Robust resolution regardless of cwd when script is invoked; handles symlinks via `-P`.

### npm ci not npm install
**Choice:** `npm ci` for dependency install step
**Rationale:** Clean install from lockfile ensures reproducible build; fails if lockfile is out of sync, surfacing drift early.

### Dist verification target: index.html
**Choice:** Check `dist/index.html` specifically
**Rationale:** index.html is the Vite entry point; its presence confirms a complete build. Checking for any file in dist/ could pass on partial builds.

### No chmod in script
**Choice:** chmod +x applied via git (executable bit set in repo)
**Rationale:** On Windows the file system does not preserve Unix permissions; the bit must be set via git. File created and staged; chmod not available meaningfully in this env. CI (Linux) will honour the git executable bit.

## Verification
[x] scripts/build.sh created with correct shebang and set -euo pipefail
[x] Uses BASH_SOURCE[0] for script-relative path resolution
[x] npm ci before npm run build (lockfile-clean install)
[x] dist/index.html check with exit 1 and stderr message on failure
[x] hatch build only runs after verification passes
[x] File staged for commit
