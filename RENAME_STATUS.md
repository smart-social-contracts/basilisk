# Basilisk Rename Status

## Summary

This fork renames the kybra Python SDK to basilisk. The initial rename has been completed at the Python source level, but the Rust runtime still registers the module as 'kybra', causing runtime errors.

## What Has Been Done

### Completed Changes
- ✅ Renamed main package directory: `kybra/` → `basilisk/`
- ✅ Renamed compiler directories: `kybra_*` → `basilisk_*`
- ✅ Updated all Python imports: `from kybra` → `from basilisk`
- ✅ Updated Cargo.toml workspace paths
- ✅ Updated Rust source files (.rs)
- ✅ Updated JSON, shell scripts, markdown documentation
- ✅ Renamed `the_kybra_book/` → `the_basilisk_book/`
- ✅ Added **chunked code upload API** to management canister:
  - `upload_chunk`, `clear_chunk_store`, `stored_chunks`, `install_chunked_code`
  - Types: `ChunkHash`, `UploadChunkArgs`, `UploadChunkResult`, `InstallChunkedCodeArgs`, etc.
- ✅ Fixed download URL to use original kybra releases (external dependency)

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

## Current Impediment

When running a canister built with basilisk, we get:
```
ModuleNotFoundError: No module named 'basilisk'
```

### Root Cause

The Rust runtime code in `basilisk_generate` registers the Python module as `kybra`:

```rust
// In the Rust runtime (conceptual)
vm.register_module("kybra", kybra_module);
```

When canister code runs `from basilisk import query`, the Python interpreter looks for a module named "basilisk" but only "kybra" is registered.

### Layers Requiring Changes

| Layer | Status | Notes |
|-------|--------|-------|
| Python source | ✅ Done | Imports use `basilisk` |
| Bundled Python modules | ⚠️ Partial | Directory renamed but internal refs may remain |
| Rust runtime code | ❌ Not done | Module registration still uses "kybra" |
| External dependencies | ✅ Kept as kybra | GitHub releases, git repos |

## Potential Solutions

### Option 1: Complete Rust Rename (Recommended)
Update the Rust code in `basilisk_generate` to:
1. Register the module as "basilisk" instead of "kybra"
2. Update any hardcoded "kybra" strings in the Rust source
3. Rebuild the compiler toolchain

Files to modify:
- `basilisk/compiler/basilisk_generate/src/*.rs`
- Any Rust files that reference "kybra" as a module name

### Option 2: Dual Module Registration
Register both "kybra" and "basilisk" as aliases to the same module, allowing both import styles to work.

### Option 3: Keep Internal Name as kybra
Keep the internal module name as "kybra" but have the package installable as "basilisk". Users would still write `from kybra import` but install with `pip install basilisk`.

## Next Steps

1. Identify all Rust files that register the "kybra" module name
2. Update module registration to use "basilisk"
3. Test canister compilation and runtime
4. Update any remaining hardcoded references

## Related

This work enables decentralized canister upgrades for the realms project, bypassing the 10MB `install_code` payload limit.
