#!/bin/bash
# Build and run the host-embedded subinterpreter test harness.
#
# Compiles the REAL src/cpython_config.c (symbol-renamed, see host_rename.h)
# against the native libpython3.13.a built from the same pinned+patched
# CPython tree as the wasm artifact, then runs main.c's subinterpreter tests.
#
# Usage: ./build_and_run.sh [cpython_source_dir]
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")" && pwd)"
BASILISK_DIR="$(cd "${HARNESS_DIR}/../.." && pwd)"
CPYTHON_DIR="${1:-${HOME}/.cache/basilisk/cpython/cpython-3.13.0}"
BUILD_DIR="${CPYTHON_DIR}/builddir/build"
CONFIG_SRC="${BASILISK_DIR}/basilisk/compiler/basilisk_cpython/src/cpython_config.c"
OUT_DIR="${HARNESS_DIR}/out"

if [ ! -f "${BUILD_DIR}/libpython3.13.a" ]; then
    echo "error: host libpython3.13.a not found at ${BUILD_DIR}" >&2
    echo "Build the host CPython first (configure && make in builddir/build)." >&2
    exit 2
fi

mkdir -p "${OUT_DIR}"

CFLAGS=(
    -I "${CPYTHON_DIR}/Include"
    -I "${BUILD_DIR}"          # pyconfig.h
    -O1 -g -Wall
)

# The stub sources under test, with host-safe symbol names.
cc -c "${CONFIG_SRC}" -o "${OUT_DIR}/cpython_config_host.o" \
    -include "${HARNESS_DIR}/host_rename.h" "${CFLAGS[@]}"

# The sandbox primitive under test (no symbol clashes with host libpython).
SANDBOX_SRC="${BASILISK_DIR}/basilisk/compiler/basilisk_cpython/src/basilisk_sandbox.c"
cc -c "${SANDBOX_SRC}" -o "${OUT_DIR}/basilisk_sandbox_host.o" "${CFLAGS[@]}"

# Trimmed archive: delete the real _threadmodule.o so the inittab's
# {"_thread", PyInit__thread} entry resolves to thread_shim.c, which
# dispatches to Basilisk's multi-phase stub. importlib bootstrap imports
# _thread during EVERY interpreter's early init, so this makes interpreter
# creation itself the test of the audit's flagged _thread risk.
cp "${BUILD_DIR}/libpython3.13.a" "${OUT_DIR}/libpython3.13-nothread.a"
ar d "${OUT_DIR}/libpython3.13-nothread.a" _threadmodule.o

cc -c "${HARNESS_DIR}/thread_shim.c" -o "${OUT_DIR}/thread_shim.o" "${CFLAGS[@]}"

cc -o "${OUT_DIR}/subinterp_harness" \
    "${HARNESS_DIR}/main.c" "${OUT_DIR}/cpython_config_host.o" \
    "${OUT_DIR}/basilisk_sandbox_host.o" \
    "${OUT_DIR}/thread_shim.o" \
    "${CFLAGS[@]}" \
    "${OUT_DIR}/libpython3.13-nothread.a" \
    -lm -lpthread -ldl -lutil

# Uninstalled host build: point the runtime at the source tree's stdlib.
export PYTHONHOME="${CPYTHON_DIR}"
export PYTHONPATH="${CPYTHON_DIR}/Lib"
exec "${OUT_DIR}/subinterp_harness"
