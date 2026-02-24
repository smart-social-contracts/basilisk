<div align="center">
    <a href="https://github.com/smart-social-contracts/basilisk" target="_blank" rel="noopener noreferrer">
        <img height="150" src="https://raw.githubusercontent.com/smart-social-contracts/basilisk/main/logo/logo.png" alt="Basilisk logo">
    </a>
</div>

# Basilisk

[![Test](https://github.com/smart-social-contracts/basilisk/actions/workflows/test.yml/badge.svg)](https://github.com/smart-social-contracts/basilisk/actions/workflows/test.yml)

A Python CDK for the [Internet Computer](https://internetcomputer.org/), forked from [Kybra](https://github.com/demergent-labs/kybra).

## Features

- Full Python support for IC canister development
- **Two backends**: CPython 3.13 (recommended) and RustPython
- **Chunked code upload API** for canisters larger than 10MB
- IC system APIs: `ic.caller()`, `ic.time()`, `ic.print()`, `ic.canister_balance()`, etc.
- `StableBTreeMap` for persistent key-value storage across upgrades
- `Principal`, `Opt`, `Vec`, `Record`, `Variant` type support

## Installation

```bash
pip install ic-basilisk
```

## Quick Start

```python
from basilisk import query, update, nat64

count: nat64 = 0

@query
def read_count() -> nat64:
    return count

@update
def increment_count() -> nat64:
    global count
    count += 1
    return count
```

## Python Backends

Basilisk supports two Python backends. Set via the `BASILISK_PYTHON_BACKEND` environment variable:

```bash
# CPython 3.13 (default, recommended)
BASILISK_PYTHON_BACKEND=cpython dfx deploy

# RustPython (legacy)
BASILISK_PYTHON_BACKEND=rustpython dfx deploy
```

### CPython vs RustPython

|  | CPython 3.13 | RustPython |
|---|---|---|
| **Build time** | ~6s | ~60-120s |
| **canister_init** | ~51M instructions (1% of budget) | ~200-500M instructions |
| **Cycles per update call** | ~7M | ~35-70M (estimated) |
| **Wasm size** (simple canister) | ~8 MB | ~5 MB |
| **Python compatibility** | Full (reference implementation) | Partial |
| **Python version** | 3.13 | ~3.10 (partial) |

### Cycle Cost (CPython, measured)

| Operation | Instructions | Cycles |
|---|---|---|
| `StableBTreeMap.insert` (update) | ~17.5M | ~7M |
| `StableBTreeMap.get` (query) | free | free |
| `canister_init` | ~51M | ~20M (one-time) |

At IC pricing (~$1.30 per 1T cycles, pegged to 1 XDR):
- **1M update calls cost ~$9** with CPython vs ~$45-90 with RustPython (estimated)
- CPython is **~5-10x cheaper** per call due to its optimized C interpreter
- Queries are free on the IC regardless of backend

## Disclaimer

Basilisk may have unknown security vulnerabilities due to the following:

- Limited production deployments on the IC
- No extensive automated property tests
- No independent security reviews/audits

## Documentation

Documentation is available in the `docs/` directory. For the original Kybra documentation, see [The Kybra Book](https://demergent-labs.github.io/kybra/).

## Discussion

Feel free to open [issues](https://github.com/smart-social-contracts/basilisk/issues).

## License

See [LICENSE](LICENSE) and [NOTICE](NOTICE).
