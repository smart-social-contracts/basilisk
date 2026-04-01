#!/bin/bash
# Create .dfx/local/canister_ids.json from icp CLI mappings
# for compatibility with azle's getCanisterId() function.
set -e

MAPPINGS_FILE=".icp/cache/mappings/local.ids.json"
if [ ! -f "$MAPPINGS_FILE" ]; then
    echo "Warning: $MAPPINGS_FILE not found"
    exit 0
fi

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
"
