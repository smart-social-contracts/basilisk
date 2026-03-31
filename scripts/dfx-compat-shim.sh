#!/bin/bash
# dfx compatibility shim for icp CLI environments.
# Translates common dfx commands to icp equivalents or reads from icp mappings.
# Used by azle and other tools that internally call dfx.

set -e

CMD="${1:-}"
SUB="${2:-}"

# Search for .icp mappings in current dir and up to 5 parent dirs
find_mappings() {
    local name="$1"
    local dir="$(pwd)"
    for i in 1 2 3 4 5; do
        for subdir in cache data; do
            local mappings="${dir}/.icp/${subdir}/mappings/local.ids.json"
            if [ -f "$mappings" ]; then
                local id
                id=$(python3 -c "import json; print(json.load(open('${mappings}')).get('${name}',''))" 2>/dev/null)
                if [ -n "$id" ]; then
                    echo "$id"
                    return 0
                fi
            fi
        done
        dir="$(dirname "$dir")"
    done
    return 1
}

case "$CMD" in
    canister)
        case "$SUB" in
            id)
                # dfx canister id <name> -> read from icp mappings
                NAME="${3:-}"
                if [ -z "$NAME" ]; then
                    echo "Error: canister name required" >&2
                    exit 1
                fi
                ID=$(find_mappings "$NAME")
                if [ -n "$ID" ]; then
                    echo "$ID"
                    exit 0
                fi
                echo "Error: Cannot find canister id for '${NAME}'" >&2
                exit 1
                ;;
            *)
                # Pass through to icp
                exec icp canister "$SUB" "${@:3}"
                ;;
        esac
        ;;
    identity)
        case "$SUB" in
            get-principal)
                exec icp identity principal "${@:3}"
                ;;
            *)
                exec icp identity "$SUB" "${@:3}"
                ;;
        esac
        ;;
    generate)
        # dfx generate -> run icp-generate.sh
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        exec bash "${SCRIPT_DIR}/icp-generate.sh" "${@:2}"
        ;;
    *)
        # Pass through everything else to icp
        exec icp "$@"
        ;;
esac
