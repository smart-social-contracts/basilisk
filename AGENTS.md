# Basilisk Agent Interface

Basilisk canisters expose two standardized endpoints for AI agents.

## `__browse__` — Read-only data access (query, free, instant)

```bash
dfx canister call <canister> __browse__ '("{\"action\": \"<action>\", ...}")'
```

| Action | Params | Returns |
|--------|--------|---------|
| `schema` | — | `{"stable_maps": {...}, "stable_sets": {...}, "stable_vecs": {...}}` |
| `len` | `map`/`set`/`vec` | `{"result": <int>}` |
| `keys` | `map`/`set`, `limit?`, `offset?` | `{"result": [...], "total": <int>}` |
| `get` | `map` + `key`, or `vec` + `key` (index) | `{"result": <value>}` |
| `items` | `map`/`set`/`vec`, `limit?`, `offset?` | `{"result": [...], "total": <int>}` |

Default limit: 100. Max: 10000. All responses are JSON.

## `__shell__` — Python execution (update, controller-only)

```bash
dfx canister call <canister> __shell__ '("print(1 + 1)")'
```

Full CPython exec. Per-principal namespace persistence. `ic` and `basilisk` pre-injected.

## Discovery flow

1. `__get_candid_interface_tmp_hack` → `.did` with all method signatures
2. `__browse__` `schema` → stable structure names, types, memory IDs
3. `__browse__` `keys`/`get`/`items` → actual data

## Enabling

```python
__basilisk_features__ = ["shell", "browse"]
```

Both auto-injected at build time. Define your own `__shell__`/`__browse__` to override defaults.
