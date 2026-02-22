#!/bin/bash
#
# Build CPython 3.13 as a static library targeting wasm32-wasip1.
#
# Prerequisites:
#   - WASI SDK (https://github.com/WebAssembly/wasi-sdk) installed
#   - Set WASI_SDK_PATH to the WASI SDK installation directory
#
# Usage:
#   WASI_SDK_PATH=/opt/wasi-sdk ./build_cpython_wasm.sh <output_dir>
#
# The script will:
#   1. Clone CPython 3.13 if not already present
#   2. Configure for wasm32-wasip1 cross-compilation
#   3. Build libpython3.13.a (static library)
#   4. Copy headers and library to <output_dir>

set -euo pipefail

CPYTHON_VERSION="3.13.0"
CPYTHON_TAG="v${CPYTHON_VERSION}"
CPYTHON_DIR=""
OUTPUT_DIR=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

usage() {
    echo "Usage: WASI_SDK_PATH=/path/to/wasi-sdk $0 <output_dir>"
    echo ""
    echo "Environment variables:"
    echo "  WASI_SDK_PATH     Path to WASI SDK installation (required)"
    echo "  CPYTHON_CACHE_DIR Directory to cache CPython source (default: ~/.cache/basilisk/cpython)"
    echo ""
    echo "Arguments:"
    echo "  output_dir        Directory to place built artifacts (headers + libpython3.13.a)"
    exit 1
}

check_prerequisites() {
    if [ -z "${WASI_SDK_PATH:-}" ]; then
        log_error "WASI_SDK_PATH is not set"
        log_info "Install WASI SDK from https://github.com/WebAssembly/wasi-sdk/releases"
        log_info "Then set: export WASI_SDK_PATH=/path/to/wasi-sdk"
        exit 1
    fi

    if [ ! -d "${WASI_SDK_PATH}" ]; then
        log_error "WASI_SDK_PATH=${WASI_SDK_PATH} does not exist"
        exit 1
    fi

    if [ ! -f "${WASI_SDK_PATH}/bin/clang" ]; then
        log_error "WASI SDK clang not found at ${WASI_SDK_PATH}/bin/clang"
        exit 1
    fi

    # We need a native Python 3.13 to bootstrap the cross-compilation
    if ! command -v python3 &> /dev/null; then
        log_error "python3 is required for cross-compilation bootstrap"
        exit 1
    fi

    log_info "Prerequisites OK"
    log_info "  WASI SDK: ${WASI_SDK_PATH}"
    log_info "  Host Python: $(python3 --version)"
}

clone_cpython() {
    local cache_dir="${CPYTHON_CACHE_DIR:-${HOME}/.cache/basilisk/cpython}"
    CPYTHON_DIR="${cache_dir}/cpython-${CPYTHON_VERSION}"

    if [ -d "${CPYTHON_DIR}" ]; then
        log_info "Using cached CPython source at ${CPYTHON_DIR}"
        return
    fi

    log_info "Cloning CPython ${CPYTHON_TAG}..."
    mkdir -p "${cache_dir}"

    git clone --depth 1 --branch "${CPYTHON_TAG}" \
        https://github.com/python/cpython.git \
        "${CPYTHON_DIR}"

    log_info "CPython source cloned to ${CPYTHON_DIR}"
}

apply_ic_patches() {
    local patches_dir
    patches_dir="$(cd "$(dirname "$0")" && pwd)/patches"

    if [ ! -d "${patches_dir}" ]; then
        log_warn "No patches directory found at ${patches_dir}, skipping IC-specific patches"
        return
    fi

    log_info "Applying IC-specific patches..."
    for patch_file in "${patches_dir}"/*.patch; do
        if [ -f "${patch_file}" ]; then
            log_info "  Applying $(basename "${patch_file}")"
            (cd "${CPYTHON_DIR}" && git apply "${patch_file}" 2>/dev/null || true)
        fi
    done
}

build_host_python() {
    # CPython cross-compilation requires a host build first
    local host_build_dir="${CPYTHON_DIR}/build-host"

    if [ -f "${host_build_dir}/python" ] || [ -f "${host_build_dir}/python3" ]; then
        log_info "Using existing host Python build"
        return
    fi

    log_info "Building host Python (needed for cross-compilation)..."
    mkdir -p "${host_build_dir}"

    (
        cd "${host_build_dir}"
        ../configure \
            --prefix="${host_build_dir}/install" \
            --disable-test-modules \
            2>&1 | tail -5
        make -j"$(nproc)" 2>&1 | tail -5
    )

    log_info "Host Python build complete"
}

configure_wasm_build() {
    local build_dir="${CPYTHON_DIR}/build-wasi"
    mkdir -p "${build_dir}"

    local host_build_dir="${CPYTHON_DIR}/build-host"

    # WASI SDK tools
    local CC="${WASI_SDK_PATH}/bin/clang"
    local AR="${WASI_SDK_PATH}/bin/llvm-ar"
    local RANLIB="${WASI_SDK_PATH}/bin/llvm-ranlib"

    # Target sysroot
    local SYSROOT="${WASI_SDK_PATH}/share/wasi-sysroot"

    # CPython 3.13 has a configure flag for WASI
    local CONFIG_SITE="${CPYTHON_DIR}/Tools/wasm/wasi/config.site-wasm32-wasi"

    log_info "Configuring CPython for wasm32-wasip1..."

    local CFLAGS="-D_WASI_EMULATED_SIGNAL -D_WASI_EMULATED_PROCESS_CLOCKS -D_WASI_EMULATED_MMAN -D_WASI_EMULATED_GETPID"
    CFLAGS="${CFLAGS} -DPYTHONHASHSEED=0"  # Deterministic hash seed for IC
    CFLAGS="${CFLAGS} -fPIC -O2"

    local LDFLAGS="-lwasi-emulated-signal -lwasi-emulated-process-clocks -lwasi-emulated-mman -lwasi-emulated-getpid"

    (
        cd "${build_dir}"

        if [ -f "${CONFIG_SITE}" ]; then
            CONFIG_SITE="${CONFIG_SITE}" \
            CC="${CC}" \
            AR="${AR}" \
            RANLIB="${RANLIB}" \
            CFLAGS="${CFLAGS}" \
            LDFLAGS="${LDFLAGS}" \
            ../configure \
                --host=wasm32-wasip1 \
                --build="$(../config.guess)" \
                --with-build-python="${host_build_dir}/python" \
                --prefix="${build_dir}/install" \
                --disable-shared \
                --disable-test-modules \
                --without-ensurepip \
                --without-pymalloc \
                --disable-ipv6 \
                2>&1 | tail -10
        else
            # Fallback for CPython versions without wasi config.site
            CC="${CC}" \
            AR="${AR}" \
            RANLIB="${RANLIB}" \
            CFLAGS="${CFLAGS}" \
            LDFLAGS="${LDFLAGS}" \
            ../configure \
                --host=wasm32-wasi \
                --build="$(../config.guess)" \
                --with-build-python="${host_build_dir}/python" \
                --prefix="${build_dir}/install" \
                --disable-shared \
                --disable-test-modules \
                --without-ensurepip \
                --without-pymalloc \
                --disable-ipv6 \
                ac_cv_file__dev_ptmx=no \
                ac_cv_file__dev_ptc=no \
                2>&1 | tail -10
        fi
    )

    log_info "Configuration complete"
}

build_wasm() {
    local build_dir="${CPYTHON_DIR}/build-wasi"

    log_info "Building CPython for wasm32-wasip1 (this may take several minutes)..."

    (
        cd "${build_dir}"
        make -j"$(nproc)" 2>&1 | tail -20
    )

    log_info "Build complete"
}

install_artifacts() {
    local build_dir="${CPYTHON_DIR}/build-wasi"

    log_info "Installing artifacts to ${OUTPUT_DIR}..."

    mkdir -p "${OUTPUT_DIR}/lib"
    mkdir -p "${OUTPUT_DIR}/include"

    # Copy the static library
    if [ -f "${build_dir}/libpython3.13.a" ]; then
        cp "${build_dir}/libpython3.13.a" "${OUTPUT_DIR}/lib/"
    elif [ -f "${build_dir}/libpython3.13d.a" ]; then
        cp "${build_dir}/libpython3.13d.a" "${OUTPUT_DIR}/lib/libpython3.13.a"
    else
        log_error "Could not find libpython3.13.a in build directory"
        ls -la "${build_dir}"/libpython* 2>/dev/null || true
        exit 1
    fi

    # Copy headers
    cp -r "${CPYTHON_DIR}/Include/"* "${OUTPUT_DIR}/include/"

    # Copy the generated pyconfig.h
    if [ -f "${build_dir}/pyconfig.h" ]; then
        cp "${build_dir}/pyconfig.h" "${OUTPUT_DIR}/include/"
    fi

    # Copy the frozen stdlib modules
    if [ -d "${build_dir}/install/lib/python3.13" ]; then
        mkdir -p "${OUTPUT_DIR}/lib/python3.13"
        cp -r "${build_dir}/install/lib/python3.13/"* "${OUTPUT_DIR}/lib/python3.13/"
    elif [ -d "${CPYTHON_DIR}/Lib" ]; then
        mkdir -p "${OUTPUT_DIR}/lib/python3.13"
        cp -r "${CPYTHON_DIR}/Lib/"* "${OUTPUT_DIR}/lib/python3.13/"
    fi

    log_info "Artifacts installed:"
    log_info "  Library: ${OUTPUT_DIR}/lib/libpython3.13.a"
    log_info "  Headers: ${OUTPUT_DIR}/include/"
    log_info "  Stdlib:  ${OUTPUT_DIR}/lib/python3.13/"

    # Print sizes
    local lib_size
    lib_size=$(du -sh "${OUTPUT_DIR}/lib/libpython3.13.a" 2>/dev/null | cut -f1)
    log_info "  Library size: ${lib_size}"
}

main() {
    if [ $# -lt 1 ]; then
        usage
    fi

    OUTPUT_DIR="$(cd "$(dirname "$1")" 2>/dev/null && pwd)/$(basename "$1")" || OUTPUT_DIR="$1"
    mkdir -p "${OUTPUT_DIR}"

    log_info "=== Building CPython ${CPYTHON_VERSION} for wasm32-wasip1 ==="
    log_info "Output directory: ${OUTPUT_DIR}"
    echo ""

    check_prerequisites
    clone_cpython
    apply_ic_patches
    build_host_python
    configure_wasm_build
    build_wasm
    install_artifacts

    echo ""
    log_info "=== CPython wasm32-wasip1 build complete ==="
}

main "$@"
