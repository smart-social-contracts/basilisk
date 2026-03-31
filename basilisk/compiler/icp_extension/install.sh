#!/bin/bash

# The icp CLI uses explicit build steps in icp.yaml instead of extensions.
# This install script is kept for backward compatibility but is a no-op
# when using the icp CLI. The extension is only needed for legacy dfx.

# Try dfx cache first (legacy support)
if command -v dfx &>/dev/null; then
    DFX_CACHE_DIR="$(dfx cache show 2>/dev/null)"
    if [ -n "$DFX_CACHE_DIR" ]; then
        if [ ! -d "$DFX_CACHE_DIR" ]; then
            dfx cache install
        fi
        mkdir -p "$DFX_CACHE_DIR/extensions/basilisk"
        cp extension.json "$DFX_CACHE_DIR/extensions/basilisk/extension.json"
        echo "Basilisk extension installed to dfx cache."
        exit 0
    fi
fi

echo "Note: icp CLI uses explicit build steps in icp.yaml — extension installation not required."
