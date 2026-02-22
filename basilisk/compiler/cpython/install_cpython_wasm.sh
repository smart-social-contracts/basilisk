#!/bin/bash
#
# Download or build CPython 3.13 for wasm32-wasip1 and install it
# to the Basilisk global config directory.
#
# This is called by the Basilisk build pipeline as an alternative to
# compile_or_download_rust_python_stdlib.
#
# Usage:
#   ./install_cpython_wasm.sh <basilisk_version_dir>

set -euo pipefail

CPYTHON_VERSION="3.13.0"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

basilisk_version_dir="$1"
cpython_wasm_dir="${basilisk_version_dir}/cpython_wasm"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[CPython]${NC} $1"; }
log_error() { echo -e "${RED}[CPython]${NC} $1"; }

if [ -d "${cpython_wasm_dir}" ] && [ -f "${cpython_wasm_dir}/lib/libpython3.13.a" ]; then
    log_info "CPython wasm32-wasip1 already installed at ${cpython_wasm_dir}"
    exit 0
fi

# Try to download pre-built artifacts first
DOWNLOAD_URL="https://github.com/smart-social-contracts/basilisk/releases/download/cpython-wasm-${CPYTHON_VERSION}/cpython-wasm32-wasip1.tar.gz"

log_info "Attempting to download pre-built CPython wasm32-wasip1..."
mkdir -p "${cpython_wasm_dir}"

if curl -Lf --connect-timeout 10 --max-time 120 \
    "${DOWNLOAD_URL}" \
    -o "${basilisk_version_dir}/cpython-wasm32-wasip1.tar.gz" 2>/dev/null; then

    log_info "Extracting pre-built CPython..."
    tar -xzf "${basilisk_version_dir}/cpython-wasm32-wasip1.tar.gz" -C "${cpython_wasm_dir}"
    rm -f "${basilisk_version_dir}/cpython-wasm32-wasip1.tar.gz"
    log_info "CPython wasm32-wasip1 installed from pre-built artifacts"
else
    log_info "Pre-built artifacts not available, building from source..."

    if [ -z "${WASI_SDK_PATH:-}" ]; then
        # Try common installation paths
        for candidate in /opt/wasi-sdk "${HOME}/.local/share/wasi-sdk" /usr/local/wasi-sdk; do
            if [ -d "${candidate}" ]; then
                export WASI_SDK_PATH="${candidate}"
                break
            fi
        done
    fi

    if [ -z "${WASI_SDK_PATH:-}" ]; then
        log_error "WASI SDK not found. Set WASI_SDK_PATH or install from:"
        log_error "  https://github.com/WebAssembly/wasi-sdk/releases"
        exit 1
    fi

    WASI_SDK_PATH="${WASI_SDK_PATH}" "${SCRIPT_DIR}/build_cpython_wasm.sh" "${cpython_wasm_dir}"
    log_info "CPython wasm32-wasip1 built and installed"
fi
