#!/usr/bin/env bash
# Print one SHA-256 over every committed file the canister template is built
# from: the CPython patch set, the Rust crates, the polyfill, the preamble
# compiled into the template, and the workflow that pins the build tools.
#
# CI records this hash next to the template on the rolling cpython-wasm release.
# A run whose sources hash to the same value reuses that template; any other
# run builds its own and tests it before it may be published.
set -euo pipefail

SOURCES=(
    basilisk/compiler/cpython
    basilisk/compiler/basilisk_cpython
    basilisk/compiler/cpython_canister_template
    basilisk/compiler/ic-wasi-polyfill-patched
    basilisk/frozen_stdlib_preamble.py
    .github/workflows/build-cpython-wasm.yml
)

cd "$(git rev-parse --show-toplevel)"

# git ls-tree skips a path it cannot find, which would drop a renamed input
# from the hash without a word.
for path in "${SOURCES[@]}"; do
    if [ -z "$(git ls-tree HEAD -- "$path")" ]; then
        echo "template_sources_hash.sh: $path is not in HEAD; update SOURCES" >&2
        exit 1
    fi
done

git ls-tree -r HEAD -- "${SOURCES[@]}" | sha256sum | cut -d' ' -f1
