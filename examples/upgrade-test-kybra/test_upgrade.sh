#!/bin/bash
set -e
set -x

echo "=== Testing Decentralized Canister Upgrade ==="

# 1. Start dfx if not running
if ! dfx ping &>/dev/null; then
    echo "Starting dfx..."
    dfx start --clean --background
    sleep 3
else
    echo "dfx is already running"
fi

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
dfx canister call target get_version '()'
dfx canister call target get_lib_version '()'
dfx canister call target greet '("World")'

# 5. Add controller canister as a controller of target
echo ""
echo "=== Setting controller canister as controller of target ==="
dfx canister update-settings target --add-controller "$CONTROLLER_ID"

# 6. Build target_v2 to get the WASM
echo ""
echo "=== Building target_v2 WASM ==="
dfx build target_v2

# 7. Get the WASM file path and convert to hex for candid
WASM_PATH=".kybra/target_v2/target_v2.wasm"
echo "WASM path: $WASM_PATH"
echo "WASM size: $(wc -c < "$WASM_PATH") bytes"

# 8. Upload chunks and execute upgrade via Python script
echo ""
echo "=== Uploading WASM chunks and executing upgrade ==="
python call_upgrade.py "$TARGET_ID" "$WASM_PATH"

# 9. Verify upgrade worked
echo ""
echo "=== After upgrade ==="
dfx canister call target get_version '()'
dfx canister call target get_lib_version '()'
dfx canister call target greet '("World")'

echo ""
echo "=== Test complete ==="
