<div align="center">
    <a href="https://github.com/smart-social-contracts/basilisk" target="_blank" rel="noopener noreferrer">
        <img height="150" src="https://raw.githubusercontent.com/smart-social-contracts/basilisk/main/img/logo.png" alt="Basilisk logo">
    </a>
</div>

# Basilisk

[![PyPI](https://img.shields.io/pypi/v/ic-basilisk)](https://pypi.org/project/ic-basilisk/)
[![Local Tests](https://github.com/smart-social-contracts/basilisk/actions/workflows/test-integration.yml/badge.svg)](https://github.com/smart-social-contracts/basilisk/actions/workflows/test-integration.yml)
[![IC Tests](https://github.com/smart-social-contracts/basilisk/actions/workflows/test-shell.yml/badge.svg)](https://github.com/smart-social-contracts/basilisk/actions/workflows/test-shell.yml)

An ICP Python Canister Development Kit and Application Framework. Write decentralized applications in Python efficiently on the [Internet Computer](https://internetcomputer.org/).

**Live demo:** [https://ic-basilisk.tech/](https://ic-basilisk.tech/).

## Features

- **Based on CPython 3.13**, compiled to WASM — deploy in seconds with a pre-built template, no Rust toolchain needed
- **Near-complete standard library** — `os`, `json`, `re`, `math`, `datetime`, `hashlib`, `collections`, networking stubs, and more. A few modules requiring native OS threads or sockets (e.g. `threading`, `subprocess`, `socket`) are not available

**Built-in Application Framework:**

- **Persistent storage** — Rust-backed stable data structures (`StableBTreeMap`, `StableBTreeSet`, `StableVec`, `StableLog`, `StableCell`, `StableMinHeap`) powered by `ic-stable-structures` with tagged binary encoding — data persists across canister upgrades with no serialization step. Supports explicit type hints (`nat8`, `int32`, etc.) for compact, correctly-ordered keys and values
- **Filesystem** — standard `open()` and `os` calls, automatically persisted to stable memory across upgrades
- **IC system APIs** — `ic.caller()`, `ic.time()`, `ic.canister_balance()`, inter-canister calls, timers, and Candid types (`Principal`, `Record`, `Variant`, etc.)

```
┌─────────────────────────────────────────────────────────┐
│                    Basilisk CDK                         │
├─────────────┬────────────┬──────────────────────────────┤
│ Filesystem  │ Storage    │ IC System APIs               │
│ POSIX-like  │ BTreeMap,  │ Timers, Inter-canister calls │
│ os/open()   │ Vec, Log,  │ Candid types, Lifecycle      │
│ auto-persist│ Cell, Heap │                              │
├─────────────┴────────────┴──────────────────────────────┤
│        MemoryManager (ic-stable-structures)             │
├─────────────────────────────────────────────────────────┤
│           CPython 3.13 (compiled to WASM)               │
├─────────────────────────────────────────────────────────┤
│              Internet Computer (ICP)                    │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- [icp](https://internetcomputer.org/docs/current/developer-docs/setup/install/) (IC SDK)
- Python 3.10+

### Install

```bash
pip install ic-basilisk
```

### Create and deploy

```bash
# 1. Scaffold a new project
basilisk new my_project
cd my_project

# 2. Start the local replica and deploy
dfx start --background
dfx deploy

# 3. Call your canister
dfx canister call my_project greet '("World")'
# ("Hello, World! The counter is at 0.")
```

> **Interactive shell, file transfer, task management, wallet, and more** are provided by
> [ic-basilisk-toolkit](https://github.com/smart-social-contracts/ic-basilisk-toolkit)
> (`pip install ic-basilisk-toolkit`).

### CPython vs RustPython

A benchmark comparison was done between [Kybra](https://github.com/demergent-labs/kybra) (RustPython) and Basilisk (CPython) to evaluate their performance characteristics.


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


## Projects Using Basilisk

- [**Realms**](https://github.com/smart-social-contracts/realms) — Governance Operating System for building and deploying governance systems on the Internet Computer

*Using Basilisk? Open a PR to add your project here.*

## Why "Basilisk"?

<div align="center">
    <img width="400" src="img/basilisk-fountain-basel.png" alt="Basilisk fountain in Basel, Switzerland">
    <br><em>A basilisk fountain in Basel, Switzerland — where this project was written.</em>
</div>

<br>

This project was written in **Basel, Switzerland** — a city guarded by basilisks since the Middle Ages. In European mythology, the basilisk is the king of serpents — part rooster, part snake — making it a fitting patron for a Python framework.

According to local legend, a basilisk once dwelt beneath Basel's streets, turning to stone anyone who dared look upon it. The citizens, unable to defeat it by force, outwitted the creature with a mirror: confronted with its own reflection, the basilisk was petrified by its own gaze. Impressed by the creature's power, the people of Basel didn't destroy it — they adopted it. To this day, basilisk statues stand watch over the city's fountains, their water said to carry a faint enchantment of protection.

In the shadow of the Tower of the Bank for International Settlements — where the world's central banks convene to shape global finance — a basilisk fountain stands watch. It is here, at the crossroads of ancient myth and modern power, that we chose to unleash the dormant power of Python onto the Internet Computer.

The fountains still flow in Basel. And now, so does Python on the IC. Great power requires great responsibility. Handle with care.

## Disclaimer

Basilisk may have unknown security vulnerabilities due to the following:

- Limited or no production deployments on the IC
- No extensive automated property tests
- No independent security reviews/audits

## Documentation

For detailed architecture notes, see [CPYTHON_MIGRATION_NOTES.md](docs/CPYTHON_MIGRATION_NOTES.md).

## Discussion

Feel free to open [issues](https://github.com/smart-social-contracts/basilisk/issues).

## License

See [LICENSE](LICENSE).
