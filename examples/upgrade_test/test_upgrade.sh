#!/bin/bash
set -e
set -x

echo "=== Testing Decentralized Canister Upgrade ==="

# 1. Start dfx if not running
dfx stop 2>/dev/null || true
dfx start --clean --background
sleep 3

# 2. Deploy all canisters
echo "Deploying canisters..."
dfx deploy

# 3. Get canister IDs
CONTROLLER_ID=$(dfx canister id controller)
TARGET_ID=$(dfx canister id target)

echo "Controller: $CONTROLLER_ID"
echo "Target: $TARGET_ID"

# 4. Check initial version
echo ""
echo "=== Initial state ==="
INITIAL_VERSION=$(dfx canister call target get_version '()')
echo "Initial version: $INITIAL_VERSION"

if [[ "$INITIAL_VERSION" != *"v1"* ]]; then
    echo "ERROR: Expected initial version to contain 'v1', got: $INITIAL_VERSION"
    exit 1
fi

# 5. Add controller canister as a controller of target
echo ""
echo "=== Setting controller canister as controller of target ==="
dfx canister update-settings target --add-controller "$CONTROLLER_ID"

# 6. Build target_v2 to get the WASM
echo ""
echo "=== Building target_v2 WASM ==="
dfx build target_v2

# 7. Get the WASM file path and convert to hex for candid
WASM_PATH=".basilisk/target_v2/target_v2.wasm"
echo "WASM path: $WASM_PATH"
echo "WASM size: $(wc -c < "$WASM_PATH") bytes"

# 8. Upload chunks and execute upgrade via Python script
echo ""
echo "=== Uploading WASM chunks and executing upgrade ==="
python call_upgrade.py "$TARGET_ID" "$WASM_PATH"

# 9. Verify upgrade worked
echo ""
echo "=== After upgrade ==="
FINAL_VERSION=$(dfx canister call target get_version '()')
echo "Final version: $FINAL_VERSION"

if [[ "$FINAL_VERSION" != *"v2"* ]]; then
    echo "ERROR: Expected final version to contain 'v2', got: $FINAL_VERSION"
    exit 1
fi

GREET_RESULT=$(dfx canister call target greet '("World")')
echo "Greet result: $GREET_RESULT"

if [[ "$GREET_RESULT" != *"upgraded"* ]]; then
    echo "ERROR: Expected greet result to contain 'upgraded', got: $GREET_RESULT"
    exit 1
fi

echo ""
echo "=== Test PASSED ==="
