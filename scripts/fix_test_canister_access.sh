#!/usr/bin/env bash
# One-time repair for the shared Basilisk IC test canister.
#
# The CI deploy identity (IC_IDENTITY_PEM / ah6ac-cc73l-...) must be a controller
# to reinstall WASM in setup-ic-canister. If controllers were rotated, run this
# script with a current controller identity (cycleops-ii / mc3wb-vqdc4-...).
#
# Usage:
#   icp identity reauth cycleops-ii   # refresh Internet Identity delegation
#   icp identity default cycleops-ii
#   ./scripts/fix_test_canister_access.sh
#
# Optional: also grant the dedicated CI controller identity used by
# IC_CONTROLLER_PEM (basilisk-ic-controller).
set -euo pipefail

CANISTER_ID="${CANISTER_ID:-gfs5q-6qaaa-aaaae-ag5nq-cai}"
NETWORK="${NETWORK:-ic}"
DEPLOY_PRINCIPAL="${DEPLOY_PRINCIPAL:-ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae}"
CONTROLLER_PRINCIPAL="${CONTROLLER_PRINCIPAL:-iaxry-644yo-icgmh-ckljl-uj37l-un2qc-f6x3j-a2azi-jtec6-twdat-mae}"

CALLER="$(icp identity principal)"
echo "Caller: $CALLER"
echo "Target canister: $CANISTER_ID"

if ! icp canister status "$CANISTER_ID" -n "$NETWORK" 2>/dev/null | grep -q "$CALLER"; then
    echo "Error: $CALLER is not a controller of $CANISTER_ID." >&2
    icp canister status "$CANISTER_ID" -n "$NETWORK" || true
    exit 1
fi

echo "Adding deploy principal $DEPLOY_PRINCIPAL..."
icp canister settings update "$CANISTER_ID" \
    --add-controller "$DEPLOY_PRINCIPAL" \
    -n "$NETWORK"

if [ "$CONTROLLER_PRINCIPAL" != "$DEPLOY_PRINCIPAL" ]; then
    echo "Adding CI controller principal $CONTROLLER_PRINCIPAL..."
    icp canister settings update "$CANISTER_ID" \
        --add-controller "$CONTROLLER_PRINCIPAL" \
        -n "$NETWORK"
fi

echo "Starting canister (it may have been left stopped by CI teardown)..."
icp canister start "$CANISTER_ID" -n "$NETWORK" 2>/dev/null || true

icp canister status "$CANISTER_ID" -n "$NETWORK"
echo "Done. Controllers now include the CI deploy identity."
