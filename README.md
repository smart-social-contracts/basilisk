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
- **In-memory filesystem**: `os.mkdir`, `os.path.exists`, `os.rename`, `os.makedirs`, `open()` for file I/O
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

# A simple counter stored in a global variable.
# State persists across calls but resets on canister upgrade.
counter = 0

@query
def greet(name: text) -> text:
    """Return a greeting message."""
    return f"Hello, {name}! The counter is at {counter}."

@query
def get_counter() -> nat64:
    """Read the current counter value."""
    return counter

@update
def increment() -> nat64:
    """Increment the counter and return the new value."""
    global counter
    counter += 1
    return counter

@query
def get_time() -> nat64:
    """Return the current IC timestamp in nanoseconds."""
    return ic.time()

@query
def whoami() -> text:
    """Return the caller's principal ID."""
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

## Filesystem

Basilisk provides an in-memory filesystem via the WASI polyfill. You can use standard Python `os` operations and `open()` for file I/O — no special imports needed.

### Directory operations

```python
import os

@update
def create_workspace() -> text:
    os.makedirs("/data/reports", exist_ok=True)
    os.mkdir("/data/logs")
    return f"exists={os.path.exists('/data/reports')} is_dir={os.path.isdir('/data/logs')}"

@update
def cleanup(path: text) -> text:
    os.rename("/data/logs", "/data/archive")
    os.rmdir("/data/archive")
    return f"renamed and removed, gone={not os.path.exists('/data/archive')}"
```

Supported: `os.mkdir`, `os.makedirs`, `os.rmdir`, `os.rename`, `os.path.exists`, `os.path.isdir`, `os.path.isfile`, `os.stat`.

### File I/O

```python
@update
def save_config(data: text) -> text:
    with open("/data/config.json", "w") as f:
        f.write(data)
    return "saved"

@query
def load_config() -> text:
    with open("/data/config.json", "r") as f:
        return f.read()
```

> **Note:** The filesystem is in-memory (heap). Data persists across calls but resets on canister upgrade. For persistent storage, use `StableBTreeMap`.

## StableBTreeMap

`StableBTreeMap` provides key-value storage that survives canister upgrades using IC stable memory.

```python
from basilisk import query, update, text, nat64, Opt, StableBTreeMap

db = StableBTreeMap[str, str](memory_id=0, max_key_size=100, max_value_size=100)

@update
def db_set(key: text, value: text) -> text:
    old = db.insert(key, value)
    return f"set {key}={value} (old={old})"

@query
def db_get(key: text) -> Opt[text]:
    return db.get(key)

@query
def db_len() -> nat64:
    return db.len()
```

```bash
dfx canister call my_project db_set '("name", "Alice")'
# ("set name=Alice (old=None)")

dfx canister call my_project db_get '("name")'
# (opt "Alice")

# Data survives upgrades:
dfx deploy my_project --upgrade-unchanged
dfx canister call my_project db_get '("name")'
# (opt "Alice")  ← still there!
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

## Disclaimer

Basilisk may have unknown security vulnerabilities due to the following:

- Limited or no production deployments on the IC
- No extensive automated property tests
- No independent security reviews/audits

## Documentation

For detailed architecture notes, see [CPYTHON_MIGRATION_NOTES.md](CPYTHON_MIGRATION_NOTES.md).

## Discussion

Feel free to open [issues](https://github.com/smart-social-contracts/basilisk/issues).

## License

See [LICENSE](LICENSE).
