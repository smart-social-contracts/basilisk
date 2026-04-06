# Integration Tests

Python pytest integration tests for Basilisk example canisters. These replace the previous per-example TypeScript test runner.

## Architecture

- **`conftest.py`** — Shared fixtures and helpers:
  - `replica` — Session-scoped PocketIC replica (started once, shared across all tests in a session)
  - `deploy_example(name)` — Builds and deploys an example canister, returns `{canister_name: canister_id}`
  - `call_canister(id, method, args)` — Calls a canister method via `dfx canister call`
  - `call_canister_expect_trap(id, method, args)` — Calls expecting a trap, returns error message
  - `parse_candid_text(response)` — Parses simple Candid text responses into Python types

- **`test_*.py`** — One file per example, each with a module-scoped `canister` fixture that deploys the example once and runs all tests against it.

## Running Locally

```bash
# All integration tests (requires dfx, basilisk, WASI SDK installed)
pytest tests/integration/ -v

# Single example
pytest tests/integration/test_counter.py -v

# By shard (as CI does)
pytest tests/integration/test_counter.py tests/integration/test_query.py -v
```

## CI Workflow

`test-integration.yml` runs these tests in 6 parallel shards:

| Shard | Contents |
|-------|----------|
| `simple-a` | counter, query, update, date, primitive_types, annotated_tests, blob_array, bytes, complex_init, complex_types |
| `simple-b` | guard_functions, filesystem, generators, timers, inspect_message, ic_api, imports, key_value_store, keywords, null_example |
| `simple-c` | manual_reply, simple_erc20, simple_user_accounts, audio_recorder, principal, call_raw, init, optional_types, list_of_lists, tuple_types |
| `advanced` | stable_memory, stable_structures, stdlib, randomness, rejections, outgoing_http_requests, init_and_post_upgrade_recovery |
| `multi-canister` | cycles, heartbeat, management_canister, notify_raw, service |
| `motoko` | calc, counter, echo, factorial, hello, hello-world, persistent-storage, phone-book, quicksort, simple-to-do, superheroes, whoami |

## Adding a New Test

1. Create `tests/integration/test_<example_name>.py`
2. Import helpers: `from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR`
3. Add a module-scoped `canister` fixture that calls `deploy_example("<example_name>")`
4. Write `test_*` functions using `call_canister()` and assertions
5. Add the test file to a shard in `.github/workflows/test-integration.yml`
