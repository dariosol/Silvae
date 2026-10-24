#!/usr/bin/env bash
# Esegue le verifiche del frontend su jsdom, dentro un container Node.
set -euo pipefail
cd "$(dirname "$0")"
docker run --rm \
  -v "$(pwd)/..:/w:ro" -v "$(pwd):/t:ro" \
  -w /tmp -e NODE_PATH=/tmp/node_modules node:22-alpine \
  sh -c "npm install --silent jsdom 2>&1 | tail -1; node /t/runner.js"
