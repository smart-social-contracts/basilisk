#!/bin/bash
# Generate TypeScript/JS declarations from canister .did files.
# Replacement for `dfx generate` when using the icp CLI.
#
# Usage:
#   ./scripts/icp-generate.sh [canister_name]
#
# If canister_name is given, generate only for that canister.
# Otherwise, generate for all canisters in icp.yaml.
#
# Requires: didc (Candid compiler) on PATH.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Determine canister names
if [ -n "$1" ]; then
    CANISTERS="$1"
else
    # Read all canister names from icp.yaml
    if [ -f "icp.yaml" ]; then
        CANISTERS=$(python3 -c "
import yaml, sys
with open('icp.yaml') as f:
    data = yaml.safe_load(f)
for c in data.get('canisters', []):
    print(c['name'])
" 2>/dev/null || yq -r '.canisters[].name' icp.yaml 2>/dev/null || echo "")
    else
        echo "Error: icp.yaml not found in $(pwd)"
        exit 1
    fi
fi

# Also create .dfx/local/canister_ids.json for azle compatibility
MAPPINGS_FILE=".icp/cache/mappings/local.ids.json"
if [ -f "$MAPPINGS_FILE" ]; then
    mkdir -p .dfx/local
    python3 -c "
import json
with open('$MAPPINGS_FILE') as f:
    ids = json.load(f)
out = {}
for name, cid in ids.items():
    out[name] = {'local': cid}
with open('.dfx/local/canister_ids.json', 'w') as f:
    json.dump(out, f, indent=2)
print('Created .dfx/local/canister_ids.json')
"
fi

for CANISTER in $CANISTERS; do
    DID_FILE=".basilisk/${CANISTER}/${CANISTER}.did"
    if [ ! -f "$DID_FILE" ]; then
        echo "Warning: $DID_FILE not found, skipping $CANISTER"
        continue
    fi

    # Determine output directory from icp.yaml declarations or default
    OUTPUT_DIR="test/dfx_generated/${CANISTER}"
    mkdir -p "$OUTPUT_DIR"

    # Generate .did.js (IDL factory) using didc
    if command -v didc &>/dev/null; then
        didc bind "$DID_FILE" --target js > "$OUTPUT_DIR/${CANISTER}.did.js"
        didc bind "$DID_FILE" --target ts > "$OUTPUT_DIR/${CANISTER}.did.d.ts"
    else
        echo "Warning: didc not found, generating minimal stub for $CANISTER"
        # Minimal stub — tests may fail without proper IDL
        cat > "$OUTPUT_DIR/${CANISTER}.did.js" << 'EOF'
export const idlFactory = ({ IDL }) => { return IDL.Service({}); };
export const init = ({ IDL }) => { return []; };
EOF
        cat > "$OUTPUT_DIR/${CANISTER}.did.d.ts" << 'EOF'
import type { ActorMethod } from '@dfinity/agent';
export interface _SERVICE {}
EOF
    fi

    # Generate index.js (createActor helper)
    cat > "$OUTPUT_DIR/index.js" << INDEXEOF
import { Actor, HttpAgent } from "@dfinity/agent";
import { idlFactory } from "./${CANISTER}.did.js";

export { idlFactory };

export const createActor = (canisterId, options = {}) => {
    const agent = options.agent || new HttpAgent({ ...options.agentOptions });
    if (options.agent && options.agentOptions) {
        console.warn("Detected both agent and agentOptions passed to createActor.");
    }
    // Fetch root key for local development
    if (process.env.DFX_NETWORK !== "ic") {
        agent.fetchRootKey().catch(err => {
            console.warn("Unable to fetch root key. Is the replica running?");
            console.error(err);
        });
    }
    return Actor.createActor(idlFactory, {
        agent,
        canisterId,
        ...options.actorOptions,
    });
};
INDEXEOF

    echo "Generated declarations for ${CANISTER} → ${OUTPUT_DIR}"
done
