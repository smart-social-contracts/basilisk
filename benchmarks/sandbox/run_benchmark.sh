#!/usr/bin/env bash
# Benchmark runner for the Basilisk subinterpreter sandbox (issue #52)
#
# Usage:
#   ./run_benchmark.sh [--network <local|ic>] [--skip-build] [--skip-deploy] [--runs N] [--soak-cycles N]
#
# Examples:
#   ./run_benchmark.sh                     # Build + deploy + bench locally
#   ./run_benchmark.sh --network ic        # Build + deploy + bench on IC mainnet
#   ./run_benchmark.sh --skip-build        # Skip build, just deploy + bench
#
set -euo pipefail

NETWORK="local"
SKIP_BUILD=false
SKIP_DEPLOY=false
RUNS=5
SOAK_CYCLES=100

while [[ $# -gt 0 ]]; do
    case "$1" in
        --network)  NETWORK="$2"; shift 2 ;;
        --skip-build)  SKIP_BUILD=true; shift ;;
        --skip-deploy) SKIP_DEPLOY=true; shift ;;
        --runs)     RUNS="$2"; shift 2 ;;
        --soak-cycles) SOAK_CYCLES="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

NETWORK_FLAG=""
[ "$NETWORK" != "local" ] && NETWORK_FLAG="--network $NETWORK"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Benchmark: Subinterpreter sandbox                           ║"
echo "║  Network:   $NETWORK                                         ║"
echo "║  Runs:      $RUNS per benchmark                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# ─── Build ───────────────────────────────────────────────────────────────────
if [ "$SKIP_BUILD" = false ]; then
    echo ""
    echo "--- Building canister ---"
    BUILD_START=$(date +%s%N)

    CANISTER_CANDID_PATH=benchmark_sandbox.did python -m basilisk benchmark_sandbox src/main.py
    cp .basilisk/benchmark_sandbox/benchmark_sandbox.wasm benchmark_sandbox.wasm
    cp .basilisk/benchmark_sandbox/benchmark_sandbox.did benchmark_sandbox.did 2>/dev/null || true
    # Convert WASI imports to IC-compatible imports (needed for local dev template)
    if command -v wasi2ic &>/dev/null; then
        wasi2ic benchmark_sandbox.wasm benchmark_sandbox.wasm
    fi

    BUILD_END=$(date +%s%N)
    BUILD_MS=$(( (BUILD_END - BUILD_START) / 1000000 ))
    WASM_SIZE=$(wc -c < benchmark_sandbox.wasm)
    echo "Build time: ${BUILD_MS}ms"
    echo "Wasm size:  $WASM_SIZE bytes ($(( WASM_SIZE / 1024 )) KB)"
else
    WASM_SIZE=$(wc -c < benchmark_sandbox.wasm 2>/dev/null || echo "0")
    BUILD_MS="skipped"
fi

# ─── Deploy ──────────────────────────────────────────────────────────────────
if [ "$SKIP_DEPLOY" = false ]; then
    echo ""
    echo "--- Deploying canister ($NETWORK) ---"
    DEPLOY_START=$(date +%s%N)
    icp deploy benchmark_sandbox -y $NETWORK_FLAG 2>&1
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

# Instruction-counted benchmarks (BenchmarkResult records).
BENCHMARKS=(
    # 1. spawn cost vs source size
    bench_spawn_1kb
    bench_spawn_10kb
    bench_spawn_50kb
    # 2. call bridge overhead
    bench_call_noop_inprocess
    bench_call_noop_sandbox
    # 3. boundary deep-copy scaling
    bench_roundtrip_1kb
    bench_roundtrip_10kb
    bench_roundtrip_100kb
    bench_roundtrip_1mb
    # 4. full fresh-per-use cycle
    bench_fresh_cycle_min
    bench_fresh_cycle_10kb
    # 5. metering overhead
    bench_sum_to_inprocess
    bench_sum_to_sandbox_unmetered
    bench_sum_to_sandbox_metered
    bench_fib_inprocess
    bench_fib_sandbox_unmetered
    bench_fib_sandbox_metered
    # 6. realistic extension workload
    bench_extension_inprocess
    bench_extension_sandbox_unmetered
    bench_extension_sandbox_metered
    # 8. capability rpc() round-trip
    bench_rpc_roundtrip
)

# Warm up: two calls to ensure interpreter is fully initialized
icp canister call --candid benchmark_sandbox.did benchmark_sandbox bench_call_noop_inprocess '()' $NETWORK_FLAG > /dev/null 2>&1 || true
icp canister call --candid benchmark_sandbox.did benchmark_sandbox bench_call_noop_inprocess '()' $NETWORK_FLAG > /dev/null 2>&1 || true

RESULTS_FILE="benchmark_results_sandbox_${NETWORK}.txt"
{
    echo "Benchmark: subinterpreter sandbox"
    echo "Network: $NETWORK"
    echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Wasm size: $WASM_SIZE bytes"
    echo "Build time: ${BUILD_MS}ms"
    echo "Deploy time: ${DEPLOY_MS}ms"
    echo "Runs per benchmark: $RUNS"
    echo ""
} > "$RESULTS_FILE"

# ─── Memory benchmarks first (Vec[str] reports, single run each) ───────────
# These read the wasm linear-memory high-water mark, which only ever grows;
# they must run BEFORE the instruction benchmarks (whose 1 MB payloads would
# push the high-water mark far above anything a few subinterpreters need,
# masking the real footprint).
echo "--- Memory footprint ---" | tee -a "$RESULTS_FILE"

echo "" | tee -a "$RESULTS_FILE"
echo "bench_memory_per_live:" | tee -a "$RESULTS_FILE"
icp canister call --candid benchmark_sandbox.did benchmark_sandbox bench_memory_per_live '()' $NETWORK_FLAG 2>&1 \
    | grep -oP '"[^"]+"' | tr -d '"' | sed 's/^/  /' | tee -a "$RESULTS_FILE"

# Two consecutive soaks: the first absorbs any one-time warm-up growth, the
# second's drift is the steady-state per-cycle leak (should be ~0).
for pass in 1 2; do
    echo "" | tee -a "$RESULTS_FILE"
    echo "bench_memory_soak pass $pass (${SOAK_CYCLES} cycles):" | tee -a "$RESULTS_FILE"
    icp canister call --candid benchmark_sandbox.did benchmark_sandbox bench_memory_soak "(${SOAK_CYCLES})" $NETWORK_FLAG 2>&1 \
        | grep -oP '"[^"]+"' | tr -d '"' | sed 's/^/  /' | tee -a "$RESULTS_FILE"
done
echo "" | tee -a "$RESULTS_FILE"

HEADER=$(printf "%-36s %16s %16s %12s %12s" "Benchmark" "Body Instr." "Total Instr." "Result" "Time (ms)")
echo "$HEADER" | tee -a "$RESULTS_FILE"
printf '%.0s─' {1..95} | tee -a "$RESULTS_FILE"
echo "" | tee -a "$RESULTS_FILE"

median() {
    local arr=("$@")
    local n=${#arr[@]}
    if [ "$n" -eq 0 ]; then echo "ERROR"; return; fi
    local sorted=($(printf '%s\n' "${arr[@]}" | sort -n))
    echo "${sorted[$(( n / 2 ))]}"
}

fmt_num() {
    if [ "$1" = "ERROR" ]; then echo "ERROR"; else printf "%'d" "$1"; fi
}

for bench in "${BENCHMARKS[@]}"; do
    BODY_VALUES=()
    TOTAL_VALUES=()
    TIME_VALUES=()
    RESULT_VAL=""

    for ((run=1; run<=RUNS; run++)); do
        # Measure wall-clock time around the call
        T_START=$(date +%s%N)
        OUTPUT=$(icp canister call --candid benchmark_sandbox.did benchmark_sandbox "$bench" '()' $NETWORK_FLAG 2>&1)
        T_END=$(date +%s%N)
        T_MS=$(( (T_END - T_START) / 1000000 ))
        TIME_VALUES+=("$T_MS")

        # Parse body_instructions and total_instructions from Candid record output
        BODY=$(echo "$OUTPUT" | grep -oP 'body_instructions\s*=\s*\K[0-9_]+' | tr -d '_')
        TOTAL=$(echo "$OUTPUT" | grep -oP 'total_instructions\s*=\s*\K[0-9_]+' | tr -d '_')
        RES=$(echo "$OUTPUT" | grep -oP '\bresult\s*=\s*\K[0-9_]+' | tr -d '_')
        [ -n "$BODY" ] && BODY_VALUES+=("$BODY")
        [ -n "$TOTAL" ] && TOTAL_VALUES+=("$TOTAL")
        [ -n "$RES" ] && RESULT_VAL="$RES"
    done

    BODY_MED=$(median "${BODY_VALUES[@]}")
    TOTAL_MED=$(median "${TOTAL_VALUES[@]}")
    TIME_MED=$(median "${TIME_VALUES[@]}")

    BODY_FMT=$(fmt_num "$BODY_MED")
    TOTAL_FMT=$(fmt_num "$TOTAL_MED")
    TIME_FMT=$(fmt_num "$TIME_MED")

    printf "%-36s %16s %16s %12s %12s\n" "$bench" "$BODY_FMT" "$TOTAL_FMT" "${RESULT_VAL:-ERROR}" "$TIME_FMT" | tee -a "$RESULTS_FILE"
done

echo "" | tee -a "$RESULTS_FILE"
echo "Results saved to $RESULTS_FILE"
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Sandbox benchmark complete on $NETWORK"
echo "╚══════════════════════════════════════════════════════════════╝"
