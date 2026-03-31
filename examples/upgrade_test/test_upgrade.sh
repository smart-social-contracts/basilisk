#!/bin/bash
set -e
set -x

echo "=== Testing Decentralized Canister Upgrade ==="

# 1. Start icp if not running
icp network stop 2>/dev/null || true
icp network start -d
sleep 3

# Helper: extract canister ID from 'icp canister create' output
extract_id() {
    echo "$1" | grep -oP 'with ID \K\S+'
}

# 2. Create canisters individually (icp CLI has no --all flag)
echo "Creating canisters..."
CREATE_OUT=$(icp canister create controller)
echo "$CREATE_OUT"
CONTROLLER_ID=$(extract_id "$CREATE_OUT")

CREATE_OUT=$(icp canister create target)
echo "$CREATE_OUT"
TARGET_ID=$(extract_id "$CREATE_OUT")

CREATE_OUT=$(icp canister create target_v2)
echo "$CREATE_OUT"

# 3. Build and deploy with per-canister backends
# Controller needs RustPython (uses basilisk.canisters.management, async/yield)
# Target canisters use CPython template mode (default) for StableBTreeMap persistence
echo ""
echo "=== Building controller (rustpython backend) ==="
BASILISK_PYTHON_BACKEND=rustpython BASILISK_COMPILE_RUST_PYTHON_STDLIB=true icp build controller
echo "=== Building target (cpython backend) ==="
icp build target
echo "=== Installing controller and target canisters ==="
icp canister install controller
icp canister install target

echo "Controller: $CONTROLLER_ID"
echo "Target: $TARGET_ID"

# 4. Check initial version
echo ""
echo "=== Initial state ==="
INITIAL_VERSION=$(icp canister call target get_version '()')
echo "Initial version: $INITIAL_VERSION"

if [[ "$INITIAL_VERSION" != *"v1"* ]]; then
    echo "ERROR: Expected initial version to contain 'v1', got: $INITIAL_VERSION"
    exit 1
fi

# 4b. Insert StableBTreeMap data BEFORE upgrade
echo ""
echo "=== Inserting StableBTreeMap data (pre-upgrade) ==="

icp canister call target set_value '("name", "Alice")'
icp canister call target set_value '("color", "blue")'
icp canister call target set_value '("city", "Zurich")'

RESULT=$(icp canister call target get_value '("name")')
echo "get_value('name'): $RESULT"
if [[ "$RESULT" != *"Alice"* ]]; then
    echo "ERROR: Expected 'Alice', got: $RESULT"
    exit 1
fi

icp canister call target increment '("visits")'
icp canister call target increment '("visits")'
icp canister call target increment '("visits")'
icp canister call target increment '("clicks")'

COUNTER_RESULT=$(icp canister call target get_counter '("visits")')
echo "get_counter('visits'): $COUNTER_RESULT"
if [[ "$COUNTER_RESULT" != *"3"* ]]; then
    echo "ERROR: Expected visits=3, got: $COUNTER_RESULT"
    exit 1
fi

DB_LEN=$(icp canister call target db_len '()')
echo "db_len: $DB_LEN"
if [[ "$DB_LEN" != *"3"* ]]; then
    echo "ERROR: Expected db_len=3, got: $DB_LEN"
    exit 1
fi

echo "Pre-upgrade data verified OK"

# 5. Add controller canister as a controller of target
echo ""
echo "=== Setting controller canister as controller of target ==="
icp canister settings update target --add-controller "$CONTROLLER_ID"

# 6. Build target_v2 to get the WASM
echo ""
echo "=== Building target_v2 WASM ==="
icp build target_v2

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
FINAL_VERSION=$(icp canister call target get_version '()')
echo "Final version: $FINAL_VERSION"

if [[ "$FINAL_VERSION" != *"v2"* ]]; then
    echo "ERROR: Expected final version to contain 'v2', got: $FINAL_VERSION"
    exit 1
fi

GREET_RESULT=$(icp canister call target greet '("World")')
echo "Greet result: $GREET_RESULT"

if [[ "$GREET_RESULT" != *"upgraded"* ]]; then
    echo "ERROR: Expected greet result to contain 'upgraded', got: $GREET_RESULT"
    exit 1
fi

# 10. Verify StableBTreeMap data persisted AFTER upgrade
echo ""
echo "=== Verifying StableBTreeMap persistence (post-upgrade) ==="

RESULT=$(icp canister call target get_value '("name")')
echo "get_value('name') after upgrade: $RESULT"
if [[ "$RESULT" != *"Alice"* ]]; then
    echo "ERROR: StableBTreeMap data LOST after upgrade! Expected 'Alice', got: $RESULT"
    exit 1
fi

RESULT=$(icp canister call target get_value '("color")')
echo "get_value('color') after upgrade: $RESULT"
if [[ "$RESULT" != *"blue"* ]]; then
    echo "ERROR: StableBTreeMap data LOST after upgrade! Expected 'blue', got: $RESULT"
    exit 1
fi

RESULT=$(icp canister call target get_value '("city")')
echo "get_value('city') after upgrade: $RESULT"
if [[ "$RESULT" != *"Zurich"* ]]; then
    echo "ERROR: StableBTreeMap data LOST after upgrade! Expected 'Zurich', got: $RESULT"
    exit 1
fi

RESULT=$(icp canister call target has_key '("name")')
echo "has_key('name') after upgrade: $RESULT"
if [[ "$RESULT" != *"true"* ]]; then
    echo "ERROR: has_key failed after upgrade! Expected true, got: $RESULT"
    exit 1
fi

DB_LEN=$(icp canister call target db_len '()')
echo "db_len after upgrade: $DB_LEN"
if [[ "$DB_LEN" != *"3"* ]]; then
    echo "ERROR: db_len changed after upgrade! Expected 3, got: $DB_LEN"
    exit 1
fi

COUNTER_RESULT=$(icp canister call target get_counter '("visits")')
echo "get_counter('visits') after upgrade: $COUNTER_RESULT"
if [[ "$COUNTER_RESULT" != *"3"* ]]; then
    echo "ERROR: Counter data LOST after upgrade! Expected visits=3, got: $COUNTER_RESULT"
    exit 1
fi

COUNTER_RESULT=$(icp canister call target get_counter '("clicks")')
echo "get_counter('clicks') after upgrade: $COUNTER_RESULT"
if [[ "$COUNTER_RESULT" != *"1"* ]]; then
    echo "ERROR: Counter data LOST after upgrade! Expected clicks=1, got: $COUNTER_RESULT"
    exit 1
fi

# 11. Verify post-upgrade mutations still work
icp canister call target increment '("visits")'
COUNTER_RESULT=$(icp canister call target get_counter '("visits")')
echo "get_counter('visits') after post-upgrade increment: $COUNTER_RESULT"
if [[ "$COUNTER_RESULT" != *"4"* ]]; then
    echo "ERROR: Post-upgrade mutation failed! Expected visits=4, got: $COUNTER_RESULT"
    exit 1
fi

icp canister call target set_value '("new_key", "post_upgrade_value")'
RESULT=$(icp canister call target get_value '("new_key")')
echo "get_value('new_key') set after upgrade: $RESULT"
if [[ "$RESULT" != *"post_upgrade_value"* ]]; then
    echo "ERROR: Post-upgrade insert failed! Expected 'post_upgrade_value', got: $RESULT"
    exit 1
fi

echo ""
echo "=== All Tests PASSED ==="
echo "  - Version upgraded from v1 to v2"
echo "  - StableBTreeMap[str, str] data persisted across upgrade (3 entries)"
echo "  - StableBTreeMap[str, nat64] counter data persisted across upgrade"
echo "  - Post-upgrade mutations work correctly"
