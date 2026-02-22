# CPython Backend for Basilisk

This directory contains the infrastructure for building and using CPython 3.13 as Basilisk's Python interpreter, replacing RustPython.

## Motivation

RustPython is **7-20x slower** than CPython (see `the_basilisk_book/src/caveats.md`). On the IC, this directly translates to:
- Higher cycle costs per message
- Hitting instruction limits sooner
- Reduced capability for compute-intensive operations

CPython also provides:
- Full Python 3.13 compatibility
- C extension support (enabling PyPI packages like numpy, etc.)
- Better-tested, more mature interpreter

## Architecture

```
basilisk/compiler/
├── cpython/
│   ├── build_cpython_wasm.sh      # Cross-compile CPython to wasm32-wasip1
│   ├── install_cpython_wasm.sh    # Download or build CPython for Basilisk
│   ├── patches/                   # IC-specific patches (determinism, etc.)
│   └── README.md                  # This file
├── basilisk_cpython/              # Rust FFI bridge crate
│   ├── Cargo.toml
│   ├── build.rs                   # Locates libpython3.13.a
│   └── src/
│       ├── lib.rs                 # Crate root, re-exports
│       ├── ffi.rs                 # Raw CPython C API bindings
│       ├── object.rs              # Safe PyObjectRef wrapper (RAII refcounting)
│       ├── interpreter.rs         # Interpreter & Scope types
│       ├── dict.rs                # Python dict operations
│       ├── tuple.rs               # Python tuple operations
│       └── convert.rs             # Type conversion traits
├── basilisk_generate/src/
│   ├── cpython_header/            # Code gen: CPython header/imports
│   ├── cpython_canister_method/   # Code gen: CPython init/query/update
│   └── cpython_body/              # Code gen: CPython function dispatch
```

## Usage

Set the environment variable before building a canister:

```bash
export BASILISK_PYTHON_BACKEND=cpython
python -m basilisk <canister_name>
```

Without the env var, the default `rustpython` backend is used (backward compatible).

## Prerequisites

To build CPython from source for wasm32-wasip1:

1. **WASI SDK**: Download from https://github.com/WebAssembly/wasi-sdk/releases
2. Set `WASI_SDK_PATH` to the installation directory
3. A host Python 3.x for cross-compilation bootstrap

Pre-built artifacts will be downloaded automatically when available.

## Status

🚧 **Work in progress** — See [GitHub Issue #8](https://github.com/smart-social-contracts/basilisk/issues/8)

### Completed
- [x] CPython wasm32-wasip1 build scripts
- [x] Rust FFI bridge crate (`basilisk_cpython`)
- [x] Type conversion traits (TryIntoPyObject / TryFromPyObject)
- [x] CPython-specific code generation modules
- [x] Build pipeline integration (BASILISK_PYTHON_BACKEND env var)
- [x] Cargo.toml generation for CPython backend

### TODO
- [ ] End-to-end proof of concept with a simple canister
- [ ] IC object (`_basilisk_ic`) implementation via CPython C API
- [ ] Async/coroutine handling for cross-canister calls
- [ ] StopIteration value extraction for coroutine returns
- [ ] CPython stdlib bundling for wasm
- [ ] Determinism patches validation
- [ ] Pre-built CPython wasm artifacts in CI
- [ ] Run existing test suite with CPython backend
- [ ] Performance benchmarking (RustPython vs CPython)
- [ ] Update `basilisk_vm_value_derive` for CPython compatibility
