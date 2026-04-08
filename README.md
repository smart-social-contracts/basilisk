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

- **Persistent ORM** — [ic-python-db](https://github.com/smart-social-contracts/ic-python-db) with typed fields, relationships, validation, and audit logging — stored in stable memory, survives canister upgrades
- **Filesystem** — standard `open()` and `os` calls, with optional persistence across upgrades
- **Interactive shell** — Python REPL running inside the canister, accessible via an SSH/SFTP proxy
- **Task management** — multi-step task execution that overcomes per-call cycle limits, with one-shot and recurring scheduling
- **File transfer** — upload/download files to and from the canister; fetch from the internet with `wget`-like command.
- **Encryption** — per-principal key envelopes, encrypted fields, and crypto groups
- **Wallet** — ckBTC/ckETH and ICRC-1 token balances, transfers, and transaction history
- **IC system APIs** — `ic.caller()`, `ic.time()`, `ic.canister_balance()`, inter-canister calls, timers, and Candid types (`Principal`, `Record`, `Variant`, etc.)

```
┌─────────────────────────────────────────────────────────┐
│              Basilisk Application Framework              │
├─────────────┬────────────┬────────────┬─────────────────┤
│ Task Mgr    │ Filesystem │ Database   │ Shell           │
│  Tasks      │ POSIX-like │ Entity ORM │ Python REPL     │
│  Scheduling │ os/open()  │ Stable Mem │ SSH / SFTP      │
│  Codex/Call │ Persistence│            │                 │
├─────────────┼────────────┼────────────┼─────────────────┤
│ Wallet      │ Encryption │ File Xfer  │ IC System APIs  │
│ ICRC-1      │ Key Envlps │ Upload/DL  │ Timers, Calls   │
│ ckBTC/ckETH │ Crypto Grps│ wget       │ Candid Types    │
├─────────────┴────────────┴────────────┴─────────────────┤
│             Basilisk CDK (Python → WASM)                │
├─────────────────────────────────────────────────────────┤
│              Internet Computer (ICP)                    │
└─────────────────────────────────────────────────────────┘

## Quick Start

### Prerequisites

- [icp](https://internetcomputer.org/docs/current/developer-docs/setup/install/) (IC SDK)
- Python 3.10+

### Install

```bash
pip install ic-basilisk
```

### Create, deploy, and connect

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

# 4. Open an interactive Python shell inside the canister
basilisk shell --canister my_project

# 5. Or connect via SSH and SFTP
basilisk sshd --canister my_project
ssh -p 2222 localhost              # Python shell over SSH
sftp -P 2222 localhost             # browse the canister filesystem
```

```
basilisk>>> print("Hello from the IC!")
Hello from the IC!
basilisk>>> import os; os.listdir("/")
['data', 'config.json']

# Create a task with inline code
basilisk>>> %task create my_report --code "print('Generating report...'); result = 42"

# Run it immediately
basilisk>>> %task run 1

# Schedule a recurring task (every 60 seconds)
basilisk>>> %task create heartbeat every 60s --code "print('alive at', ic.time())"

# View task details and list all tasks
basilisk>>> %task info 1
basilisk>>> %task list
```

## Database

Basilisk includes [ic-python-db](https://github.com/smart-social-contracts/ic-python-db), an Entity ORM with typed fields, relationships, validation, and audit logging — all persisted to stable memory across canister upgrades:

```python
from basilisk import query, update, text
from basilisk.db import Entity, String, Integer, TimestampedMixin

class User(Entity, TimestampedMixin):
    __alias__ = "name"
    name = String(min_length=2, max_length=50)
    age = Integer(min_value=0)

@update
def add_user(name: text, age: text) -> text:
    user = User(name=name, age=int(age))
    return f"Created user {user.name} with id {user._id}"

@query
def get_user(name: text) -> text:
    user = User[name]  # Lookup by alias
    return f"{user.name}, age {user.age}"

@query
def list_users() -> text:
    return str([(u.name, u.age) for u in User.instances()])
```

```bash
dfx canister call my_project add_user '("Alice", "30")'
# ("Created user Alice with id 1")
dfx canister call my_project get_user '("Alice")'
# ("Alice, age 30")

# Data survives upgrades:
dfx deploy my_project --upgrade-unchanged
dfx canister call my_project get_user '("Alice")'
# ("Alice, age 30")  ← still there!
```

See the [ic-python-db documentation](https://github.com/smart-social-contracts/ic-python-db) for relationships (`OneToMany`, `ManyToOne`, etc.), access control, entity hooks, and more.

### Basilisk (CPython) vs RustPython

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

<!-- ## CLI Reference

```
basilisk new [--backend cpython|rustpython] <name>   Create a new project
basilisk build                                       Build the canister
basilisk exec [--canister <c>] [--network <n>] <code> Execute code on a deployed canister
basilisk shell [--canister <c>] [--network <n>]      Interactive shell
basilisk sshd [--canister <c>] [--network <n>] [--port <p>]  SSH/SFTP server
basilisk --version                                   Print version -->

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

For detailed architecture notes, see [CPYTHON_MIGRATION_NOTES.md](CPYTHON_MIGRATION_NOTES.md).

## Discussion

Feel free to open [issues](https://github.com/smart-social-contracts/basilisk/issues).

## License

See [LICENSE](LICENSE).
