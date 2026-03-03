<div align="center">
    <a href="https://github.com/smart-social-contracts/basilisk" target="_blank" rel="noopener noreferrer">
        <img height="150" src="https://raw.githubusercontent.com/smart-social-contracts/basilisk/main/logo/logo.png" alt="Basilisk logo">
    </a>
</div>

# Basilisk

[![PyPI](https://img.shields.io/pypi/v/ic-basilisk)](https://pypi.org/project/ic-basilisk/)
[![Test](https://github.com/smart-social-contracts/basilisk/actions/workflows/test.yml/badge.svg)](https://github.com/smart-social-contracts/basilisk/actions/workflows/test.yml)

Write **Python canisters** for the [Internet Computer](https://internetcomputer.org/). Forked from [Kybra](https://github.com/demergent-labs/kybra).

## Features

- Write IC canisters in pure Python using `@query` and `@update` decorators
- **Two backends**: CPython 3.13 (default, fast builds) and RustPython
- **Fast template builds**: CPython canisters build in seconds, not minutes
- IC system APIs: `ic.caller()`, `ic.time()`, `ic.print()`, `ic.canister_balance()`, etc.
- **Chunked code upload** for canisters larger than 10MB
- `StableBTreeMap` for persistent key-value storage across upgrades
- `Principal`, `Opt`, `Vec`, `Record`, `Variant` type support

## Getting Started

### Prerequisites

- [dfx](https://internetcomputer.org/docs/current/developer-docs/setup/install/) (IC SDK)
- Python 3.10+
- [WASI SDK](https://github.com/aspect-build/aspect-workflows-releases/blob/main/wasi-sdk/README.md) (for CPython backend)

### Install

```bash
pip install ic-basilisk
```

### Create a new project

```bash
basilisk new my_project
cd my_project
```

This creates a ready-to-deploy project:

```
my_project/
  src/main.py    -- your canister code
  dfx.json       -- IC project config
```

### The generated canister code

```python
from basilisk import query, update, text, nat64, ic

counter = 0

@query
def greet(name: text) -> text:
    return f"Hello, {name}! The counter is at {counter}."

@query
def get_counter() -> nat64:
    return counter

@update
def increment() -> nat64:
    global counter
    counter += 1
    return counter

@query
def get_time() -> nat64:
    return ic.time()

@query
def whoami() -> text:
    return str(ic.caller())
```

### Deploy and call

```bash
dfx start --background
dfx deploy

dfx canister call my_project greet '("World")'
# ("Hello, World! The counter is at 0.")

dfx canister call my_project increment
# (1 : nat64)

dfx canister call my_project whoami
# ("2vxsx-fae")
```

## Python Backends

Basilisk supports two Python backends:

```bash
# CPython 3.13 (default) -- fast template builds
basilisk new my_project

# RustPython -- legacy, full Rust build
basilisk new --backend rustpython my_project
```

### CPython vs RustPython

|  | CPython 3.13 | RustPython |
|---|---|---|
| **Build time** | ~seconds (template) | ~60-120s (Cargo build) |
| **Wasm size** | ~5.3 MB | ~26 MB |
| **Python compatibility** | Full (reference implementation) | Partial (~3.10) |

### Benchmark Results

Instruction counts measured on a local IC replica (PocketIC). Lower is better — fewer instructions means lower cycle cost on the IC.

| Benchmark | CPython (instructions) | RustPython (instructions) | RustPython / CPython |
|---|---:|---:|---:|
| **noop** (call overhead) | 27,313 | 88,918 | 3.3x |
| **increment** (state mutation) | 27,349 | 91,911 | 3.4x |
| **fibonacci(25)** (iterative) | 49,823 | 297,086 | 6.0x |
| **fibonacci_recursive(20)** | 29,334,665 | 338,200,210 | **11.5x** |
| **string_ops** (100 concatenations) | 284,951 | 2,139,351 | **7.5x** |
| **list_ops** (500 append + sort) | 604,656 | 5,819,063 | **9.6x** |
| **dict_ops** (500 inserts + lookups) | 3,349,809 | 23,086,280 | **6.9x** |
| **method_overhead** (total prelude) | 24,088 | 42,102 | 1.7x |

CPython is **7–12x faster** than RustPython for compute-heavy workloads due to its optimized C interpreter. The gap is largest for **recursive function calls** (11.5x) and **list operations** (9.6x). Even the minimum overhead per call is lower: 24K vs 42K instructions.

> **Run it yourself:** trigger the [Benchmark workflow](https://github.com/smart-social-contracts/basilisk/actions/workflows/benchmark.yml) from the Actions tab — select `cpython`, `rustpython`, or `both` as the backend, and `local` or `ic` as the network. View full logs by clicking any workflow run.

The benchmark source is in [`benchmarks/counter/`](benchmarks/counter/).

## CLI Reference

```bash
basilisk new [--backend cpython|rustpython] <project_name>   # scaffold a project
basilisk build                                                # build in current dir
basilisk --version                                            # print version
```

## Available Types

```python
from basilisk import (
    query, update,                    # method decorators
    text, blob, null, void,           # basic types
    nat, nat8, nat16, nat32, nat64,   # unsigned integers
    int8, int16, int32, int64,        # signed integers
    float32, float64,                 # floats
    Opt, Vec, Record, Variant,        # compound types
    Principal,                        # IC principal
    ic,                               # IC system API
)
```

## IC System API

```python
from basilisk import ic

ic.caller()              # caller's Principal
ic.time()                # current timestamp (nanoseconds)
ic.id()                  # canister's own Principal
ic.print(msg)            # debug print (visible in replica logs)
ic.trap(msg)             # abort with error message
ic.canister_balance()    # current cycle balance
ic.canister_balance128() # cycle balance as 128-bit int
```

## Disclaimer

Basilisk may have unknown security vulnerabilities due to the following:

- Limited production deployments on the IC
- No extensive automated property tests
- No independent security reviews/audits

## Documentation

For detailed architecture notes, see [CPYTHON_MIGRATION_NOTES.md](CPYTHON_MIGRATION_NOTES.md). For the original Kybra documentation, see [The Kybra Book](https://demergent-labs.github.io/kybra/).

## Discussion

Feel free to open [issues](https://github.com/smart-social-contracts/basilisk/issues).

## License

See [LICENSE](LICENSE) and [NOTICE](NOTICE).
