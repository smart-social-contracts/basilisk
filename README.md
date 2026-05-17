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

> **Interactive shell, ORM, Schema Upgrade Checking, file transfer, task management, wallet, and more** are provided by
> [ic-basilisk-toolkit](https://github.com/smart-social-contracts/ic-basilisk-toolkit)
> (`pip install ic-basilisk-toolkit`).

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

- [dfx](https://internetcomputer.org/docs/building-apps/getting-started/install) (IC SDK)
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

## Built-in AI/Agent Endpoints

Basilisk can auto-inject standardized `__shell__` and `__browse__` endpoints into your canister at build time. Enable them with a single line:

```python
__basilisk_features__ = ["shell", "browse"]
```

**`__shell__`** — full Python execution (controller-only `@update`):
```bash
dfx canister call my_canister __shell__ '("print(1 + 1)")'
# ("2\n")
```

**`__browse__`** — read-only data introspection (public `@query`, instant, free):
```bash
# Discover data schema
dfx canister call my_canister __browse__ '("{\"action\": \"schema\"}")'

# Read keys from a stable map (paginated, default limit=100)
dfx canister call my_canister __browse__ '("{\"action\": \"keys\", \"map\": \"users\"}")'

# Get a specific value
dfx canister call my_canister __browse__ '("{\"action\": \"get\", \"map\": \"users\", \"key\": \"alice\"}")'
```

Both endpoints can be overridden with custom implementations (e.g. custom guards, filtered data access). If you define `__shell__` or `__browse__` yourself, the compiler uses yours instead of the default.

### CPython vs RustPython

|  | CPython 3.13 | RustPython |
|---|---|---|
| **Build time** | ~seconds (template) | ~60-120s (Cargo build) |
| **Wasm size** | ~5.3 MB | ~26 MB |
| **Python compatibility** | Full (reference implementation) | Partial (~3.10) |

### Cross-Language Benchmark

Pure-compute benchmarks comparing Rust, Motoko, and CPython on identical algorithms. Measured via `ic0.performance_counter` on a PocketIC replica. On the IC, **1 instruction ≈ 1 cycle** of compute cost. Lower is better. These numbers exclude the fixed per-call fee (~590K cycles for updates, ~260K for queries) and memory/storage costs.

| Benchmark | Rust | Motoko | CPython | vs Rust (CPython) |
|---|---:|---:|---:|---:|
| **noop** (call overhead) | 13,686 | 3,299 | 15,592 | **1.1x** |
| **increment** (state mutation) | 12,827 | 3,411 | 15,159 | **1.2x** |
| **fibonacci(25)** (iterative) | 12,750 | 5,713 | 36,553 | **2.9x** |
| **fibonacci_recursive(20)** | 373,953 | 2,203,257 | 29,617,193 | **79.2x** |
| **sum_to(10000)** (arithmetic loop) | 272,761 | 513,314 | 12,767,523 | **46.8x** |
| **ackermann(3,6)** (deep recursion) | 3,285,678 | 19,717,638 | 284,158,839 | **86.5x** |
| **method_overhead** (total prelude) | 12,334 | 2,863 | 10,172 | **0.8x** |

For lightweight operations (noop, increment), CPython is within **1–2x** of native Rust — the interpreter overhead is negligible. For short iterative work (fibonacci), the gap is modest at **2.9x**. However, for longer loops (sum_to: **47x**) and deep recursion (ackermann: **87x**, fibonacci_recursive: **79x**), Python's per-instruction and per-frame overhead compounds significantly. Motoko has the smallest call prelude (~3K instructions) but its instruction cost grows faster than Rust for heavy computation.

Full CI logs: [All backends](https://github.com/smart-social-contracts/basilisk/actions/runs/26002047455)

### Python-Specific Benchmark (CPython vs RustPython)

These benchmarks use language-specific data structures (Python `dict`, `list`, `str`) so they only compare CPython against RustPython — not against Rust/Motoko, which have fundamentally different standard libraries.

| Benchmark | CPython | RustPython | RustPython / CPython |
|---|---:|---:|---:|
| **string_ops** (100 concatenations) | 275,375 | 2,135,202 | **7.8x** |
| **list_ops** (500 append + sort) | 602,711 | 5,819,267 | **9.7x** |
| **dict_ops** (500 inserts + lookups) | 3,407,101 | 23,087,720 | **6.8x** |

CPython is **6–11x faster** than RustPython across the board, with the gap largest for recursive function calls and list operations.

> **Run it yourself:** trigger the [Benchmark workflow](https://github.com/smart-social-contracts/basilisk/actions/workflows/benchmark.yml) from the Actions tab — select `cpython`, `rust`, `motoko`, or `all` as the backend, and `local` or `ic` as the network.

The benchmark sources are in [`benchmarks/counter/`](benchmarks/counter/) (CPython), [`benchmarks/counter_rust/`](benchmarks/counter_rust/) (Rust), and [`benchmarks/counter_motoko/`](benchmarks/counter_motoko/) (Motoko).


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

## Security

See [SECURITY.md](SECURITY.md).

## Documentation

For detailed architecture notes, see [CPYTHON_MIGRATION_NOTES.md](docs/CPYTHON_MIGRATION_NOTES.md).

## Discussion

Feel free to open [issues](https://github.com/smart-social-contracts/basilisk/issues).

## License

See [LICENSE](LICENSE).
