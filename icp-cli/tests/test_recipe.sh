#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/../templates/hello-world"

cd "$PROJECT_DIR"

echo "==> Building template with recipe..."
icp build

echo "==> Starting local network..."
icp network start -d

cleanup() { icp network stop 2>/dev/null || true; }
trap cleanup EXIT

echo "==> Deploying canister..."
icp deploy

echo "==> Recipe test passed"
