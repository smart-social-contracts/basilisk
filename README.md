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

## Quick Start

### Prerequisites

- [icp-cli](https://docs.internetcomputer.org/docs/getting-started/install-cli) (`curl --proto '=https' --tlsv1.2 -LsSf https://github.com/dfinity/icp-cli/releases/latest/download/icp-cli-installer.sh | sh`)
- Python 3.10+


### "Hello World" with icp-cli

To create a simple "Hello World" project with icp-cli, run:

```bash
# 1. Scaffold a new project from the Basilisk template
icp new my_project --git https://github.com/smart-social-contracts/basilisk --subfolder icp-cli/templates/hello-world

# 2. Install dependencies and deploy to the local replica
cd my_project
# Optional: python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
icp network start -d
icp deploy

# 3. Call your canister
icp canister call my_project greet '("World")'
# ("Hello, World!")
```

Alternatively, you can install Basilisk directly: `pip install ic-basilisk`

## Features

- **Based on CPython 3.13**, compiled to WASM — deploy in seconds with a pre-built template, no Rust toolchain needed
- **Near-complete standard library** — `os`, `json`, `re`, `math`, `datetime`, `hashlib`, `collections`, networking stubs, and more. A few modules requiring native OS threads or sockets (e.g. `threading`, `subprocess`, `socket`) are not available

**Built-in Application Framework:**

- **Persistent storage** — Rust-backed stable data structures (`StableBTreeMap`, `StableBTreeSet`, `StableVec`, `StableLog`, `StableCell`, `StableMinHeap`) powered by `ic-stable-structures` with tagged binary encoding — data persists across canister upgrades with no serialization step. Supports explicit type hints (`nat8`, `int32`, etc.) for compact, correctly-ordered keys and values
- **Filesystem** — standard `open()` and `os` calls, automatically persisted to stable memory across upgrades
- **IC system APIs** — `ic.caller()`, `ic.time()`, `ic.canister_balance()`, inter-canister calls, timers, and Candid types (`Principal`, `Record`, `Variant`, etc.)
- **Sandboxed execution** — run untrusted Python (extensions, rule modules) in an isolated CPython subinterpreter with a capability-gated host bridge, a deterministic instruction budget, and validated plain-data results. See [Sandboxing Untrusted Code](#sandboxing-untrusted-code)

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

## Built-in AI/Agent Endpoints

Basilisk can auto-inject standardized `__shell__` and `__browse__` endpoints into your canister at build time. Enable them with a single line:

```python
__basilisk_features__ = ["shell", "browse"]
```

**`__shell__`** — full Python execution (controller-only `@update`):
```bash
icp canister call my_canister __shell__ '("print(1 + 1)")'
# ("2\n")
```

**`__browse__`** — read-only data introspection (public `@query`, instant, free):
```bash
# Discover data schema
icp canister call my_canister __browse__ '("{\"action\": \"schema\"}")'

# Read keys from a stable map (paginated, default limit=100)
icp canister call my_canister __browse__ '("{\"action\": \"keys\", \"map\": \"users\"}")'

# Get a specific value
icp canister call my_canister __browse__ '("{\"action\": \"get\", \"map\": \"users\", \"key\": \"alice\"}")'
```

Both endpoints can be overridden with custom implementations (e.g. custom guards, filtered data access). If you define `__shell__` or `__browse__` yourself, the compiler uses yours instead of the default.

## Sandboxing Untrusted Code

Run untrusted or semi-trusted Python (user-supplied extensions, rule modules) inside an **isolated CPython subinterpreter**. The sandbox has its own heap and GIL, an empty `sys.path`, and cannot import the privileged host surface — code inside it can only compute and talk back through a capability-gated `rpc()` bridge you control. Data crossing the boundary is **plain data only** (`None`/`bool`/`int`/`float`/`str`/`list`/`dict`), deep-copied in both directions; no live object references cross.

Key properties:

- **Content-hash allow-list** — a subinterpreter only runs source whose SHA-256 you explicitly approved host-side.
- **Deterministic instruction budget** — sandboxed code is metered in the interpreter's dispatch loop (bytecode instructions, never wall-clock); exceeding the budget raises `BudgetExceeded`. The main interpreter is never metered.
- **Isolation by construction** — `_basilisk_ic` and the spawn primitive itself are refused fail-closed inside the sandbox; the dangerous native surface (real filesystem, sockets, subprocesses) is simply absent, not denylisted.

### Simple example

```python
import _basilisk_sandbox as sandbox
from basilisk import update

# Untrusted extension code (imagine a user uploaded this).
EXTENSION = """
def score(numbers=None):
    numbers = numbers or []
    return {"total": sum(numbers), "count": len(numbers)}
"""

@update
def run_extension() -> str:
    # 1. Approve the exact source by its content hash (host-side allow-list).
    content_hash = sandbox.sha256(EXTENSION)
    sandbox.approve_hash(content_hash)

    # 2. Spawn an isolated subinterpreter running that source.
    handle = sandbox.spawn_subinterpreter(EXTENSION, content_hash)

    # 3. Call a function in it — args and result cross as plain data only.
    result = sandbox.call_in_subinterpreter(handle, "score", {"numbers": [1, 2, 3]})

    # 4. Tear it down (fresh-per-use by design; no pooling).
    sandbox.close_subinterpreter(handle)
    return str(result)  # {'total': 6, 'count': 3}
```

For privileged operations, spawn with a **capability** and an `rpc` handler (`basilisk.sandbox.build_capability` / `spawn_sandboxed`), and validate anything the sandbox proposes to write with the two-pass validator + atomic commit (`basilisk.sandbox.commit_result`). See [docs/SUBINTERPRETER_AUDIT.md](docs/SUBINTERPRETER_AUDIT.md) for the full security model, capability intersection, result validation, and the `bool`/`int`/`float` type-checking notes.

**Overhead:** a call into an already-spawned sandbox costs ~10K instructions, boundary copies ~0.6K instructions per byte, metering 5–11%, and a full fresh-per-use spawn/call/close cycle ~55–100M instructions. Full numbers and amortization guidance in [docs/SANDBOX_BENCHMARKS.md](docs/SANDBOX_BENCHMARKS.md) ([`benchmarks/sandbox/`](benchmarks/sandbox/)).

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
| **fibonacci_recursive(20)** | 373,953 | 2,050,048 | 29,617,193 | **79.2x** |
| **sum_to(10000)** (arithmetic loop) | 272,761 | 513,314 | 12,767,523 | **46.8x** |
| **ackermann(3,6)** (deep recursion) | 3,285,678 | 15,225,081 | 284,158,839 | **86.5x** |
| **method_overhead** (total prelude) | 12,334 | 2,863 | 10,172 | **0.8x** |

Full CI logs: [All backends](https://github.com/smart-social-contracts/basilisk/actions/runs/26014003754)

### Python-Specific Benchmark (CPython vs RustPython)

These benchmarks use language-specific data structures (Python `dict`, `list`, `str`) so they only compare CPython against RustPython — not against Rust/Motoko, which have fundamentally different standard libraries.

| Benchmark | CPython | RustPython | RustPython / CPython |
|---|---:|---:|---:|
| **string_ops** (100 concatenations) | 275,375 | 2,135,202 | **7.8x** |
| **list_ops** (500 append + sort) | 602,711 | 5,819,267 | **9.7x** |
| **dict_ops** (500 inserts + lookups) | 3,407,101 | 23,087,720 | **6.8x** |

CPython is **6–10x faster** than RustPython across the board, with the gap largest for recursive function calls and list operations.

> **Run it yourself:** trigger the [Benchmark workflow](https://github.com/smart-social-contracts/basilisk/actions/workflows/benchmark.yml) from the Actions tab — select `cpython`, `rust`, `motoko`, `sandbox`, or `all` as the backend, and `local` or `ic` as the network.

The benchmark sources are in [`benchmarks/counter/`](benchmarks/counter/) (CPython), [`benchmarks/counter_rust/`](benchmarks/counter_rust/) (Rust), and [`benchmarks/counter_motoko/`](benchmarks/counter_motoko/) (Motoko). The subinterpreter-sandbox overhead suite is in [`benchmarks/sandbox/`](benchmarks/sandbox/), with results in [docs/SANDBOX_BENCHMARKS.md](docs/SANDBOX_BENCHMARKS.md).


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

## Security

See [SECURITY.md](SECURITY.md).

## Documentation

For detailed architecture notes, see [CPYTHON_MIGRATION_NOTES.md](docs/CPYTHON_MIGRATION_NOTES.md).

## Discussion

Feel free to open [issues](https://github.com/smart-social-contracts/basilisk/issues).

## Disclaimer

**This software is not production-ready.** Do not deploy to mainnet or use with real assets or canister state you cannot afford to lose.

Basilisk is in early development (alpha). It may contain bugs, breaking changes, and unknown security vulnerabilities. It has not undergone an independent security audit. **Use at your own risk.**

- Not recommended for production deployments on the Internet Computer
- No extensive automated property tests
- No guarantee of correctness, availability, or security
- APIs and behavior may change without notice

## License

MIT — see [LICENSE](LICENSE).
