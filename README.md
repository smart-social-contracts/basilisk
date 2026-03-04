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
from basilisk import query, update, text, nat64, ic, StableBTreeMap, Opt

# StableBTreeMap persists across canister upgrades (uses IC stable memory)
db = StableBTreeMap[str, str](memory_id=0, max_key_size=100, max_value_size=100)

counter = 0

@update
def db_set(key: text, value: text) -> text:
    old = db.insert(key, value)
    return f"set {key}={value} (old={old})"

@query
def db_get(key: text) -> Opt[text]:
    return db.get(key)

@query
def greet(name: text) -> text:
    return f"Hello, {name}! The counter is at {counter}."

@update
def increment() -> nat64:
    global counter
    counter += 1
    return counter

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

dfx canister call my_project db_set '("name", "Alice")'
# ("set name=Alice (old=None)")

dfx canister call my_project db_get '("name")'
# (opt "Alice")
```

### Data persists across upgrades

```bash
# Upgrade the canister (redeploy with new code)
dfx deploy my_project --upgrade-unchanged

# StableBTreeMap data survives the upgrade
dfx canister call my_project db_get '("name")'
# (opt "Alice")  ← still there!

# Global variables reset on upgrade (normal Python memory)
dfx canister call my_project greet '("World")'
# ("Hello, World! The counter is at 0.")
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

Wasm instruction counts measured on a PocketIC replica via GitHub Actions CI. Lower is better — fewer instructions means lower cycle cost on the IC.

| Benchmark | CPython (instructions) | RustPython (instructions) | RustPython / CPython |
|---|---:|---:|---:|
| **noop** (call overhead) | 15,914 | 88,918 | **5.6x** |
| **increment** (state mutation) | 16,050 | 92,485 | **5.8x** |
| **fibonacci(25)** (iterative) | 37,269 | 294,649 | **7.9x** |
| **fibonacci_recursive(20)** | 29,617,903 | 337,795,318 | **11.4x** |
| **string_ops** (100 concatenations) | 275,375 | 2,135,202 | **7.8x** |
| **list_ops** (500 append + sort) | 602,711 | 5,819,267 | **9.7x** |
| **dict_ops** (500 inserts + lookups) | 3,407,101 | 23,087,720 | **6.8x** |
| **method_overhead** (total prelude) | 11,122 | 42,216 | **3.8x** |

CPython is **6–11x faster** than RustPython for compute-heavy workloads due to its optimized C interpreter. The gap is largest for **recursive function calls** (11.4x) and **list operations** (9.7x). Even the minimum overhead per call is lower: 11K vs 42K instructions.

Full CI logs: [CPython run](https://github.com/smart-social-contracts/basilisk/actions/runs/22616838245) · [RustPython run](https://github.com/smart-social-contracts/basilisk/actions/runs/22616844678)

> **Run it yourself:** trigger the [Benchmark workflow](https://github.com/smart-social-contracts/basilisk/actions/workflows/benchmark.yml) from the Actions tab — select `cpython`, `rustpython`, or `both` as the backend, and `local` or `ic` as the network.

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
