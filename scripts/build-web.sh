#!/bin/bash
# Build the web pages into v2/ under agent/static, which the agent embeds.
# Every build of the agent runs this first.
set -euo pipefail
WEB=$(cd "$(dirname "$(realpath "$0")")/../agent/web" && pwd)

command -v npm >/dev/null || {
    echo "build-web: npm not found; it builds the agent's web pages." >&2
    echo "  Use the SDK devcontainer, or install Node.js and re-run." >&2
    exit 1
}

cd "$WEB"
# Install when the lock file is newer than what is installed.
[ node_modules/.package-lock.json -nt package-lock.json ] || npm ci --no-fund --no-audit
npm run build
