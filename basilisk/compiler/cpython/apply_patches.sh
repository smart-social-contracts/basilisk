#!/bin/bash
#
# Apply Basilisk's IC-specific patches to a CPython source tree.
#
# Usage:
#   ./apply_patches.sh <cpython_source_dir> [patches_dir] [--verify-exact]
#
# Behavior (per patch, in lexicographic order):
#   - If the patch applies cleanly            -> apply it.
#   - If the patch is already applied         -> skip (idempotent re-runs).
#   - Anything else (malformed, conflicting)  -> FATAL, non-zero exit.
#
# With --verify-exact, additionally verify ZERO source-tree drift: after
# applying, all patches are reverse-applied and the tree must then be
# byte-identical to the pristine upstream tag (no modified tracked files).
# This catches uncommitted, load-bearing local modifications in cached
# source trees — the exact failure mode found during the Step-0 audit,
# where frozen-encodings changes existed only in a build cache and nowhere
# in the repo. The patches are re-applied before the script exits.
#
# Failing loudly is a hard requirement: these patches are load-bearing
# (frozen encodings are required for subinterpreter creation; the upcoming
# instruction-metering patch is a security control for sandboxed code).
# A silently-unapplied patch would produce a libpython3.13.a that appears
# to work while missing a security-critical behavior.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[patches]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[patches]${NC} $1"; }
log_error() { echo -e "${RED}[patches]${NC} $1" >&2; }

if [ $# -lt 1 ]; then
    log_error "Usage: $0 <cpython_source_dir> [patches_dir]"
    exit 2
fi

CPYTHON_DIR="$1"
PATCHES_DIR="${2:-$(cd "$(dirname "$0")" && pwd)/patches}"
VERIFY_EXACT=0
for arg in "$@"; do
    if [ "$arg" = "--verify-exact" ]; then
        VERIFY_EXACT=1
    fi
done
# Allow --verify-exact as the second arg (patches_dir defaulted)
if [ "${PATCHES_DIR}" = "--verify-exact" ]; then
    PATCHES_DIR="$(cd "$(dirname "$0")" && pwd)/patches"
fi

if [ ! -d "${CPYTHON_DIR}" ]; then
    log_error "CPython source dir not found: ${CPYTHON_DIR}"
    exit 2
fi

if [ ! -d "${PATCHES_DIR}" ]; then
    log_error "Patches dir not found: ${PATCHES_DIR}"
    exit 2
fi

# Absolutize both dirs: git apply runs with cwd inside CPYTHON_DIR, so a
# relative patches path would silently resolve against the wrong directory.
CPYTHON_DIR="$(cd "${CPYTHON_DIR}" && pwd)"
PATCHES_DIR="$(cd "${PATCHES_DIR}" && pwd)"

shopt -s nullglob
patch_files=("${PATCHES_DIR}"/*.patch)
shopt -u nullglob

if [ ${#patch_files[@]} -eq 0 ]; then
    log_warn "No .patch files in ${PATCHES_DIR} — nothing to apply"
    exit 0
fi

failed=0
for patch_file in "${patch_files[@]}"; do
    name="$(basename "${patch_file}")"
    if (cd "${CPYTHON_DIR}" && git apply --check "${patch_file}" 2>/dev/null); then
        (cd "${CPYTHON_DIR}" && git apply "${patch_file}")
        log_info "applied ${name}"
    elif (cd "${CPYTHON_DIR}" && git apply --reverse --check "${patch_file}" 2>/dev/null); then
        log_info "already applied, skipping ${name}"
    else
        log_error "FAILED to apply ${name} (not applicable and not already applied)."
        # Re-run without suppression so the actual git error is visible.
        (cd "${CPYTHON_DIR}" && git apply --check "${patch_file}") || true
        failed=1
    fi
done

if [ "${failed}" -ne 0 ]; then
    log_error "One or more IC patches failed to apply — refusing to continue."
    log_error "A build from an unpatched tree would be silently missing"
    log_error "IC-critical behavior (frozen encodings, metering, determinism)."
    exit 1
fi

if [ "${VERIFY_EXACT}" -eq 1 ]; then
    log_info "Verifying zero source-tree drift (patched tree == pristine + patches)..."

    # Reverse-apply every patch (reverse lexicographic order, so patches that
    # touch the same files unwind correctly).
    for (( i=${#patch_files[@]}-1; i>=0; i-- )); do
        patch_file="${patch_files[$i]}"
        if ! (cd "${CPYTHON_DIR}" && git apply --reverse "${patch_file}"); then
            log_error "DRIFT CHECK BROKEN: could not reverse-apply $(basename "${patch_file}")."
            log_error "Tree is now in an inconsistent state — discard it and re-clone."
            exit 1
        fi
    done

    drift="$(cd "${CPYTHON_DIR}" && git status --porcelain --untracked-files=no)"

    # Re-apply all patches regardless of the verdict, so the tree is usable.
    for patch_file in "${patch_files[@]}"; do
        (cd "${CPYTHON_DIR}" && git apply "${patch_file}")
    done

    if [ -n "${drift}" ]; then
        log_error "SOURCE TREE DRIFT DETECTED: after removing all repo patches, the"
        log_error "tree still differs from the pristine upstream tag:"
        echo "${drift}" >&2
        log_error ""
        log_error "This means the source tree contains modifications that exist in NO"
        log_error "patch file in the repository. Capture them as a patch under"
        log_error "$(basename "${PATCHES_DIR}")/ or discard them. Refusing to build from"
        log_error "an unreproducible tree."
        exit 1
    fi

    log_info "Zero drift: tree is exactly pristine + repo patches"
fi

log_info "All IC patches OK"
