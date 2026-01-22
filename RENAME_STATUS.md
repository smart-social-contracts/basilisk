# Basilisk Rename Status

## Summary

This fork renames the kybra Python SDK to basilisk. **The rename is now complete** - the runtime module registration issue has been fixed by creating a proper runtime-ready `basilisk` package in `custom_modules`.

## What Has Been Done

### Completed Changes
- ✅ Renamed main package directory: `kybra/` → `basilisk/`
- ✅ Renamed compiler directories: `kybra_*` → `basilisk_*`
- ✅ Updated all Python imports: `from kybra` → `from basilisk`
- ✅ Updated Cargo.toml workspace paths
- ✅ Updated Rust source files (.rs) - all use `basilisk` and `_basilisk_ic`
- ✅ Updated JSON, shell scripts, markdown documentation
- ✅ Renamed `the_kybra_book/` → `the_basilisk_book/`
- ✅ Added **chunked code upload API** to management canister:
  - `upload_chunk`, `clear_chunk_store`, `stored_chunks`, `install_chunked_code`
  - Types: `ChunkHash`, `UploadChunkArgs`, `UploadChunkResult`, `InstallChunkedCodeArgs`, etc.
- ✅ Fixed download URL to use original kybra releases (external dependency)
- ✅ **Fixed runtime module registration** - created `custom_modules/basilisk/__init__.py` with all runtime types and decorators
- ✅ Updated bundler to use custom runtime `basilisk` module instead of site-packages version
- ✅ Renamed all environment variables: `KYBRA_*` → `BASILISK_*`

### New Feature: Chunked Code Upload API

Added support for the IC's chunked code upload API, enabling upgrades of canisters larger than 10MB:

```python
from basilisk.canisters.management import (
    management_canister,
    ChunkHash,
    UploadChunkArgs,
    InstallChunkedCodeArgs,
)

# Upload chunks
result = yield management_canister.upload_chunk({
    "canister_id": target,
    "chunk": chunk_data,
})

# Install from chunks
yield management_canister.install_chunked_code({
    "mode": {"upgrade": None},
    "target_canister": target,
    "chunk_hashes_list": hashes,
    "wasm_module_hash": wasm_hash,
    "arg": bytes(),
})
```

## Runtime Module Fix

The original issue was that when canister code ran `from basilisk import query`, the Python interpreter couldn't find the `basilisk` module because:
1. The installed `basilisk` package had complex internal imports (`.compiler.custom_modules.principal`)
2. These relative imports didn't work correctly when bundled for the canister runtime

### Solution Implemented

Created a standalone runtime-ready `basilisk` module at `compiler/custom_modules/basilisk/__init__.py` that:
1. Contains all types, decorators, and classes needed at runtime
2. Includes the `Principal` class directly (no relative imports)
3. Uses `_basilisk_ic` for IC API calls (injected by Rust runtime)

The bundler was updated to:
1. Copy `custom_modules/basilisk/` to `python_source/basilisk/`
2. Skip the site-packages `basilisk` package (which has complex imports)

### Layers Status

| Layer | Status | Notes |
|-------|--------|-------|
| Python source | ✅ Done | Imports use `basilisk` |
| Bundled Python modules | ✅ Done | Runtime module in `custom_modules/basilisk/` |
| Rust runtime code | ✅ Done | Uses `basilisk` and `_basilisk_ic` |
| External dependencies | ✅ Kept as kybra | GitHub releases, git repos (intentional) |

## Environment Variables

The following environment variables have been renamed:
- `KYBRA_VERBOSE` → `BASILISK_VERBOSE`
- `KYBRA_REBUILD` → `BASILISK_REBUILD`
- `KYBRA_COMPILE_RUST_PYTHON_STDLIB` → `BASILISK_COMPILE_RUST_PYTHON_STDLIB`

## Related

This work enables decentralized canister upgrades for the realms project, bypassing the 10MB `install_code` payload limit.
