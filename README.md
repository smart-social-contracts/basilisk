<div align="center">
    <a href="https://github.com/smart-social-contracts/basilisk" target="_blank" rel="noopener noreferrer">
        <img height="150" src="https://raw.githubusercontent.com/smart-social-contracts/basilisk/main/logo/logo.png" alt="Basilisk logo">
    </a>
</div>

# Basilisk

[![PyPI](https://img.shields.io/pypi/v/ic-basilisk)](https://pypi.org/project/ic-basilisk/)
[![Test](https://github.com/smart-social-contracts/basilisk/actions/workflows/test.yml/badge.svg)](https://github.com/smart-social-contracts/basilisk/actions/workflows/test.yml)

Write **Python canisters** for the [Internet Computer](https://internetcomputer.org/). Deploy in seconds, connect via SSH/SFTP. Forked from [Kybra](https://github.com/demergent-labs/kybra).

## Features

- Write IC canisters in pure Python using `@query` and `@update` decorators
- **Builds in seconds** — pre-compiled CPython 3.13 WASM template, no Rust toolchain needed
- **SSH & SFTP access** — connect to any deployed canister with standard `ssh` and `sftp` clients
- **Interactive shell** — Python REPL running inside the canister
- **Basilisk OS** — task scheduling, code management (Codex), and process execution on-chain
- **In-memory filesystem** — standard `os` and `open()` calls, accessible via SFTP
- **Persistent storage** — `StableBTreeMap` survives canister upgrades
- IC system APIs: `ic.caller()`, `ic.time()`, `ic.print()`, `ic.canister_balance()`, etc.
- `Principal`, `Opt`, `Vec`, `Record`, `Variant` type support

## Quick Start

### Prerequisites

- [dfx](https://internetcomputer.org/docs/current/developer-docs/setup/install/) (IC SDK)
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

# 2. Start the local replica and deploy (builds in ~2 seconds)
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

## SSH & SFTP Access

Every Basilisk canister is accessible over SSH and SFTP. Start the proxy and connect with any standard client.

### Start the SSH server

```bash
# Local replica
basilisk sshd --canister my_project

# IC mainnet
basilisk sshd --canister my_project --network ic

# Custom port
basilisk sshd --canister my_project --port 3333
```

### Connect via SSH

```bash
ssh -p 2222 -o StrictHostKeyChecking=no localhost
```

This drops you into **Basilisk Shell** — a Python REPL running inside the canister:

```
basilisk>>> print("Hello from the IC!")
Hello from the IC!
basilisk>>> import os; os.listdir("/")
['data', 'config.json']
basilisk>>> 1 + 1
2
```

Run a single command over SSH:

```bash
ssh -p 2222 localhost 'print(ic.time())'
```

### Connect via SFTP

```bash
sftp -P 2222 -o StrictHostKeyChecking=no localhost
```

Browse, upload, and download files on the canister's in-memory filesystem:

```
sftp> ls /
data        config.json
sftp> put local_script.py /scripts/myscript.py
sftp> get /data/results.json ./results.json
sftp> mkdir /logs
```

### Shell commands

| Command | Description |
|---|---|
| `%ls [path]` | List canister filesystem |
| `%cat <file>` | Show file contents |
| `%mkdir <path>` | Create directory |
| `%wget <url> <dest>` | Download URL into canister filesystem |
| `%run <file>` | Execute a local file on the canister |
| `%task create/run/list` | Create and manage scheduled tasks |
| `%db dump/clear/count` | Inspect the canister database |
| `%info` | Show canister info (principal, cycles, status) |
| `!<cmd>` | Run a local OS command |

## Basilisk OS

Basilisk OS provides operating-system-like services for IC canisters: **task management**, **code storage**, **scheduled execution**, and **persistent storage** — all running on-chain.

```
┌─────────────────────────────────────────────┐
│                 Basilisk OS                  │
├──────────────┬──────────────┬───────────────┤
│ Task Manager │  Filesystem  │   Database    │
│  Task        │  POSIX-like  │  ic-python-db │
│  TaskStep    │  in-memory   │  Entity ORM   │
│  TaskSchedule│  os / open() │  StableBTree  │
│  Codex/Call  │              │               │
├──────────────┴──────────────┴───────────────┤
│           Basilisk CDK (Python → WASM)      │
├─────────────────────────────────────────────┤
│         Internet Computer (IC)              │
└─────────────────────────────────────────────┘
```

### Entities

- **Codex** — Stores executable Python code on the canister filesystem. Code is read/written transparently via the `code` property.
- **Call** — Links a Codex to a TaskStep for execution (sync or async).
- **Task** — A unit of work with one or more steps.
- **TaskStep** — A single step in a multi-step task workflow.
- **TaskSchedule** — Defines when and how often a Task runs (one-shot or recurring).
- **TaskExecution** — Records the result of each execution attempt.

### Task management

```bash
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

### Using Basilisk OS entities in canister code

```python
from basilisk.os import Task, TaskStep, Codex, Call, TaskSchedule

@update
def create_pipeline() -> text:
    codex = Codex(name="etl_script")
    codex.code = "data = [x * 2 for x in range(10)]; print(f'Processed {len(data)} items')"

    task = Task(name="ETL Pipeline")
    step = TaskStep(task=task)
    call = Call(codex=codex, task_step=step)
    schedule = TaskSchedule(name="hourly", task=task, repeat_every=3600)

    return f"Created task: {task.name}"
```

## Remote Code Execution

Execute Python on a deployed canister without redeploying:

```bash
# One-liner
basilisk exec --canister my_project 'print(1 + 1)'

# Run a local script on the canister
basilisk exec --canister my_project -f analysis.py

# Pipe code
echo "import os; print(os.listdir('/'))" | basilisk exec --canister my_project

# Target IC mainnet
basilisk exec --canister my_project --network ic 'print(ic.canister_balance())'
```

## Filesystem

Standard Python `os` operations and `open()` work inside the canister. The filesystem is also accessible via SFTP (see above).

```python
import os

@update
def setup() -> text:
    os.makedirs("/data/reports", exist_ok=True)
    with open("/data/config.json", "w") as f:
        f.write('{"version": 1}')
    return f"exists={os.path.exists('/data/config.json')}"

@query
def load_config() -> text:
    with open("/data/config.json", "r") as f:
        return f.read()
```

> **Note:** The filesystem is in-memory (heap). Data persists across calls but resets on canister upgrade. For persistent storage, use `StableBTreeMap`.

## StableBTreeMap

Key-value storage that survives canister upgrades using IC stable memory:

```python
from basilisk import query, update, text, Opt, StableBTreeMap

db = StableBTreeMap[str, str](memory_id=0, max_key_size=100, max_value_size=100)

@update
def db_set(key: text, value: text) -> text:
    db.insert(key, value)
    return f"set {key}={value}"

@query
def db_get(key: text) -> Opt[text]:
    return db.get(key)
```

```bash
dfx canister call my_project db_set '("name", "Alice")'
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

## CLI Reference

```
basilisk new [--backend cpython|rustpython] <name>   Create a new project
basilisk build                                       Build the canister
basilisk exec [--canister <c>] [--network <n>] <code> Execute code on a deployed canister
basilisk shell [--canister <c>] [--network <n>]      Interactive shell
basilisk sshd [--canister <c>] [--network <n>] [--port <p>]  SSH/SFTP server
basilisk --version                                   Print version
```

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
