#!/usr/bin/env bash
# Prepare the shared Basilisk IC test canister for CI (setup-ic-canister job).
#
# Uses IC_IDENTITY_PEM (ci-deploy) for routine calls. When that principal is not
# a canister controller, falls back to IC_CONTROLLER_PEM (or IC_IDENTITY_PEM_2)
# to add ci-deploy as a controller and perform stop/install/start.
set -euo pipefail

CANISTER_ID="${CANISTER_ID:?CANISTER_ID is required}"
NETWORK="${NETWORK:-ic}"
WASM_PATH="${WASM_PATH:?WASM_PATH is required}"
DEPLOY_IDENTITY="${DEPLOY_IDENTITY:-ci-deploy}"
CONTROLLER_IDENTITY="${CONTROLLER_IDENTITY:-ci-controller}"

import_identity() {
    local name="$1"
    local pem="$2"
    if [ -z "$pem" ]; then
        return 1
    fi
    umask 077
    printf '%s' "$pem" > "/tmp/${name}.pem"
    icp identity import --from-pem "/tmp/${name}.pem" --storage plaintext "$name" 2>/dev/null || true
    rm -f "/tmp/${name}.pem"
}

import_identity "$DEPLOY_IDENTITY" "${IC_IDENTITY_PEM:-}"
if [ -z "${IC_IDENTITY_PEM:-}" ]; then
    echo "::error::IC_IDENTITY_PEM secret is not set."
    exit 1
fi

CONTROLLER_PEM="${IC_CONTROLLER_PEM:-${IC_IDENTITY_PEM_2:-}}"
HAS_CONTROLLER_IDENTITY=0
if [ -n "$CONTROLLER_PEM" ]; then
    import_identity "$CONTROLLER_IDENTITY" "$CONTROLLER_PEM"
    HAS_CONTROLLER_IDENTITY=1
fi

icp identity default "$DEPLOY_IDENTITY"
DEPLOY_PRINCIPAL="$(icp identity principal)"
echo "Deploy identity ($DEPLOY_IDENTITY): $DEPLOY_PRINCIPAL"

is_controller() {
    local principal="$1"
    icp canister status "$CANISTER_ID" -n "$NETWORK" 2>/dev/null \
        | grep -q "$principal"
}

mgmt_identity() {
    if is_controller "$DEPLOY_PRINCIPAL"; then
        echo "$DEPLOY_IDENTITY"
        return
    fi
    if [ "$HAS_CONTROLLER_IDENTITY" -eq 1 ]; then
        local controller_principal
        icp identity default "$CONTROLLER_IDENTITY"
        controller_principal="$(icp identity principal)"
        echo "Controller identity ($CONTROLLER_IDENTITY): $controller_principal"
        if ! is_controller "$controller_principal"; then
            echo "::error::$CONTROLLER_IDENTITY ($controller_principal) is not a controller of $CANISTER_ID."
            echo "Current controllers:"
            icp canister status "$CANISTER_ID" -n "$NETWORK" || true
            exit 1
        fi
        if ! is_controller "$DEPLOY_PRINCIPAL"; then
            echo "Adding $DEPLOY_PRINCIPAL as controller via $CONTROLLER_IDENTITY..."
            icp canister settings update "$CANISTER_ID" \
                --add-controller "$DEPLOY_PRINCIPAL" \
                -n "$NETWORK" \
                --identity "$CONTROLLER_IDENTITY"
        fi
        icp identity default "$DEPLOY_IDENTITY"
        echo "$DEPLOY_IDENTITY"
        return
    fi
    echo "::error::$DEPLOY_IDENTITY ($DEPLOY_PRINCIPAL) is not a controller of $CANISTER_ID."
    echo "Set IC_CONTROLLER_PEM (or IC_IDENTITY_PEM_2) to a controller identity, or add"
    echo "$DEPLOY_PRINCIPAL manually: icp canister settings update $CANISTER_ID \\"
    echo "  --add-controller $DEPLOY_PRINCIPAL -n $NETWORK"
    echo "Current controllers:"
    icp canister status "$CANISTER_ID" -n "$NETWORK" || true
    exit 1
}

MGMT="$(mgmt_identity)"
echo "Using $MGMT for canister management operations."

echo "Stopping canister $CANISTER_ID..."
icp canister stop "$CANISTER_ID" -n "$NETWORK" --identity "$MGMT" 2>/dev/null || true
sleep 3

echo "Reinstalling canister with fresh WASM..."
icp canister install "$CANISTER_ID" \
    --mode reinstall \
    -y \
    -n "$NETWORK" \
    --identity "$MGMT" \
    --wasm "$WASM_PATH"

echo "Starting canister..."
icp canister start "$CANISTER_ID" -n "$NETWORK" --identity "$MGMT"

icp identity default "$DEPLOY_IDENTITY"
echo "Verifying canister is reachable..."
icp canister call "$CANISTER_ID" status '()' -n "$NETWORK" --query
echo "Test canister $CANISTER_ID is ready."
