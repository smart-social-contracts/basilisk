# Basilisk Test Suite

## Overview

The test suite is split into three workflows based on **where** they run:

| Workflow | File | Runs on | Trigger |
|---|---|---|---|
| **IC Tests** | `test-shell.yml` | Live IC mainnet canister | PR, push to main, manual |
| **Local Tests** | `test-integration.yml` | Local dfx replica | PR, push to main, manual |
| **Upgrade Test** | `test-upgrade.yml` | Local dfx replica | PR, push to main |

On push to main, `test-all.yml` orchestrates all three (plus the CPython WASM template build).

## IC Tests (`test-shell.yml`)

Tests Basilisk CDK runtime features against a live canister on IC mainnet (`2i66l-saaaa-aaaas-qe3sq-cai`).

Toolkit-specific IC tests (tasks, wallet, fx, crypto, vetkeys) live in [ic-basilisk-toolkit](https://github.com/smart-social-contracts/ic-basilisk-toolkit).

**Test files** (in `tests/`):

| Shard | Files | What it covers |
|---|---|---|
| shell | `test_shell.py` | Shell exec, Candid parsing, one-shot/file/pipe/watch modes |
| filesystem | `test_filesystem.py` | memfs operations, file persistence |
| guards | `test_guards.py` | Guard metadata extraction, controller-only access |

**Requirements:**
- `IC_IDENTITY_PEM` secret (CI identity for mainnet calls)
- The test canister must be deployed (handled by `test-all.yml`'s `setup-ic-canister` job)
- A concurrency group (`ic-tests-mainnet`) prevents parallel runs from stomping on the shared canister
- Each shard has a 20-minute timeout

**Running locally:**
```bash
pip install -e ".[shell,test]"
BASILISK_TEST_CANISTER=2i66l-saaaa-aaaas-qe3sq-cai \
BASILISK_TEST_NETWORK=ic \
PYTHONPATH=. python -m pytest tests/test_shell.py -v
```

## Local Tests (`test-integration.yml`)

Tests canister compilation and API correctness for 42 example canisters on a local dfx replica.

**Architecture:** build-once + deploy-only.
1. A single runner builds all example WASMs via `scripts/build_all_wasms.py`
2. Pre-built WASMs are uploaded as a GitHub artifact
3. Six test shards download the WASMs, deploy via `dfx canister install --wasm`, and run tests

**Test files** (in `tests/integration/`):

| Shard | Examples |
|---|---|
| simple-a | counter, query, update, date, primitive_types, annotated_tests, blob_array, bytes, complex_init, complex_types |
| simple-b | guard_functions, filesystem, generators, timers, inspect_message, ic_api, imports, key_value_store, keywords, null_example |
| simple-c | manual_reply, simple_erc20, simple_user_accounts, audio_recorder, principal, call_raw, init, optional_types, list_of_lists, tuple_types |
| advanced | stable_memory, stable_structures, stdlib, randomness, rejections, outgoing_http_requests, init_and_post_upgrade_recovery |
| multi-canister | cycles, heartbeat, management_canister, notify_raw, service |
| motoko | 12 Motoko interop examples (calc, counter, echo, etc.) |

**Example fixtures** are in `tests/fixtures/`. Each fixture has a `dfx.json` and Python source files.

**Running locally:**
```bash
pip install -e .
python -m basilisk install-dfx-extension
dfx start --clean --background

# Build all WASMs (slow, ~minutes):
python scripts/build_all_wasms.py

# Run one shard:
BASILISK_PREBUILT_WASMS=1 pytest tests/integration/test_counter.py -v
```

## Upgrade Test (`test-upgrade.yml`)

Tests decentralized canister upgrades using the IC chunked code upload API (`upload_chunk` + `install_chunked_code`), and verifies that `StableBTreeMap` data persists across upgrades.

**Fixture:** `tests/fixtures/upgrade_test/` — three canisters:
- `controller` — orchestrates the upgrade via management canister calls
- `target` — starts as v1, gets upgraded to v2
- `target_v2` — built separately to produce the v2 WASM

**Test flow** (`test_upgrade.sh`):
1. Deploy v1, insert StableBTreeMap data
2. Upload v2 WASM in chunks via the controller canister
3. Execute chunked upgrade
4. Verify version changed AND all data persisted

## Other Workflows

| Workflow | File | Purpose |
|---|---|---|
| **Build CPython WASM** | `build-cpython-wasm.yml` | Builds CPython 3.13 + canister template for wasm32-wasip1 |
| **Benchmark** | `benchmark.yml` | Manual: CPython vs RustPython performance comparison |
| **Publish** | `publish.yml` | Manual: bump version, publish to PyPI, IC mainnet smoke test |

## Directory Structure

```
tests/
  conftest.py              # Shared fixtures for IC tests
  test_*.py                # IC test files (3 shards)
  test_canister/           # Shell test canister source + dfx.json
  integration/
    conftest.py            # Shared fixtures for local tests
    test_*.py              # Local test files (42 examples)
  fixtures/
    upgrade_test/          # Upgrade test fixture
    <example_name>/        # One dir per example canister
```
