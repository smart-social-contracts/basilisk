#!/usr/bin/env bash
# Benchmark runner for Basilisk (CPython) vs Kybra (RustPython)
#
# Usage:
#   ./run_benchmark.sh <backend> [--network <local|ic>] [--skip-build] [--skip-deploy]
#
# Examples:
#   ./run_benchmark.sh cpython                     # Build + deploy + bench locally
#   ./run_benchmark.sh rustpython                  # Build + deploy + bench locally
#   ./run_benchmark.sh cpython --network ic        # Build + deploy + bench on IC mainnet
#   ./run_benchmark.sh cpython --skip-build        # Skip build, just deploy + bench
#
set -euo pipefail

BACKEND="${1:-cpython}"
shift || true
NETWORK="local"
SKIP_BUILD=false
SKIP_DEPLOY=false
RUNS=5

while [[ $# -gt 0 ]]; do
    case "$1" in
        --network)  NETWORK="$2"; shift 2 ;;
        --skip-build)  SKIP_BUILD=true; shift ;;
        --skip-deploy) SKIP_DEPLOY=true; shift ;;
        --runs)     RUNS="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

NETWORK_FLAG=""
[ "$NETWORK" != "local" ] && NETWORK_FLAG="--network $NETWORK"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Benchmark: Counter                                        ║"
echo "║  Backend:   $BACKEND                                       ║"
echo "║  Network:   $NETWORK                                       ║"
echo "║  Runs:      $RUNS per benchmark                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# ─── Build ───────────────────────────────────────────────────────────────────
if [ "$SKIP_BUILD" = false ]; then
    echo ""
    echo "--- Building canister ($BACKEND) ---"
    BUILD_START=$(date +%s%N)

    if [ "$BACKEND" = "cpython" ]; then
        export BASILISK_PYTHON_BACKEND=cpython
        CANISTER_CANDID_PATH=benchmark_counter.did python -m basilisk benchmark_counter src/main.py
        cp .basilisk/benchmark_counter/benchmark_counter.wasm benchmark_counter.wasm
        cp .basilisk/benchmark_counter/benchmark_counter.did benchmark_counter.did 2>/dev/null || true
        # Convert WASI imports to IC-compatible imports (needed for local dev template)
        if command -v wasi2ic &>/dev/null; then
            wasi2ic benchmark_counter.wasm benchmark_counter.wasm
        fi
    else
        # RustPython build via basilisk
        export BASILISK_PYTHON_BACKEND=rustpython
        CANISTER_CANDID_PATH=benchmark_counter.did python -m basilisk benchmark_counter src/main.py
        cp .basilisk/benchmark_counter/benchmark_counter.wasm benchmark_counter.wasm
        # Generate .did from the build output if available
        if [ -f benchmark_counter.did ]; then
            echo "Using existing benchmark_counter.did"
        fi
    fi

    BUILD_END=$(date +%s%N)
    BUILD_MS=$(( (BUILD_END - BUILD_START) / 1000000 ))
    WASM_SIZE=$(wc -c < benchmark_counter.wasm)
    echo "Build time: ${BUILD_MS}ms"
    echo "Wasm size:  $WASM_SIZE bytes ($(( WASM_SIZE / 1024 )) KB)"
else
    WASM_SIZE=$(wc -c < benchmark_counter.wasm 2>/dev/null || echo "0")
    BUILD_MS="skipped"
fi

# ─── Deploy ──────────────────────────────────────────────────────────────────
if [ "$SKIP_DEPLOY" = false ]; then
    echo ""
    echo "--- Deploying canister ($NETWORK) ---"
    DEPLOY_START=$(date +%s%N)
    dfx deploy benchmark_counter --yes $NETWORK_FLAG 2>&1
    DEPLOY_END=$(date +%s%N)
    DEPLOY_MS=$(( (DEPLOY_END - DEPLOY_START) / 1000000 ))
    echo "Deploy time: ${DEPLOY_MS}ms"
else
    DEPLOY_MS="skipped"
fi

# ─── Run benchmarks ─────────────────────────────────────────────────────────
echo ""
echo "--- Running benchmarks ($RUNS runs each, median reported) ---"
echo ""

BENCHMARKS=(
    bench_noop
    bench_increment
    bench_fibonacci
    bench_fibonacci_recursive
    bench_string_ops
    bench_list_ops
    bench_dict_ops
    bench_method_overhead
)

# Warm up: two calls to ensure interpreter is fully initialized
dfx canister call benchmark_counter bench_noop '()' $NETWORK_FLAG > /dev/null 2>&1 || true
dfx canister call benchmark_counter bench_noop '()' $NETWORK_FLAG > /dev/null 2>&1 || true

RESULTS_FILE="benchmark_results_${BACKEND}_${NETWORK}.txt"
{
    echo "Backend: $BACKEND"
    echo "Network: $NETWORK"
    echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Wasm size: $WASM_SIZE bytes"
    echo "Build time: ${BUILD_MS}ms"
    echo "Deploy time: ${DEPLOY_MS}ms"
    echo "Runs per benchmark: $RUNS"
    echo ""
} > "$RESULTS_FILE"

HEADER=$(printf "%-28s %16s %16s %12s" "Benchmark" "Body Instr." "Total Instr." "Time (ms)")
echo "$HEADER" | tee -a "$RESULTS_FILE"
printf '%.0s─' {1..74} | tee -a "$RESULTS_FILE"
echo "" | tee -a "$RESULTS_FILE"

for bench in "${BENCHMARKS[@]}"; do
    BODY_VALUES=()
    TOTAL_VALUES=()
    TIME_VALUES=()

    for ((run=1; run<=RUNS; run++)); do
        # Measure wall-clock time around the call
        T_START=$(date +%s%N)
        OUTPUT=$(dfx canister call benchmark_counter "$bench" '()' $NETWORK_FLAG 2>&1)
        T_END=$(date +%s%N)
        T_MS=$(( (T_END - T_START) / 1000000 ))
        TIME_VALUES+=("$T_MS")

        # Parse body_instructions and total_instructions from Candid record output
        BODY=$(echo "$OUTPUT" | grep -oP 'body_instructions\s*=\s*\K[0-9_]+' | tr -d '_')
        TOTAL=$(echo "$OUTPUT" | grep -oP 'total_instructions\s*=\s*\K[0-9_]+' | tr -d '_')
        [ -n "$BODY" ] && BODY_VALUES+=("$BODY")
        [ -n "$TOTAL" ] && TOTAL_VALUES+=("$TOTAL")
    done

    # Compute medians (sort numerically, pick middle)
    median() {
        local arr=("$@")
        local n=${#arr[@]}
        if [ "$n" -eq 0 ]; then echo "ERROR"; return; fi
        local sorted=($(printf '%s\n' "${arr[@]}" | sort -n))
        echo "${sorted[$(( n / 2 ))]}"
    }

    BODY_MED=$(median "${BODY_VALUES[@]}")
    TOTAL_MED=$(median "${TOTAL_VALUES[@]}")
    TIME_MED=$(median "${TIME_VALUES[@]}")

    # Format with thousands separators
    fmt_num() {
        if [ "$1" = "ERROR" ]; then echo "ERROR"; else printf "%'d" "$1"; fi
    }

    BODY_FMT=$(fmt_num "$BODY_MED")
    TOTAL_FMT=$(fmt_num "$TOTAL_MED")
    TIME_FMT=$(fmt_num "$TIME_MED")

    printf "%-28s %16s %16s %12s\n" "$bench" "$BODY_FMT" "$TOTAL_FMT" "$TIME_FMT" | tee -a "$RESULTS_FILE"
done

echo "" | tee -a "$RESULTS_FILE"
echo "Results saved to $RESULTS_FILE"
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Benchmark complete: $BACKEND on $NETWORK"
echo "╚══════════════════════════════════════════════════════════════╝"
