# Tip Jar — Basilisk Template

A full-stack canister template demonstrating all major [basilisk](https://github.com/smart-social-contracts/basilisk) features on the Internet Computer.

## Features

| Feature | Files |
|---|---|
| **Database ORM** — persistent entities via `ic-python-db` | `models.py` |
| **ICRC-1 Wallet** — token balance, transfer, indexer sync | `services.py`, `endpoints.py` |
| **FX Rates** — IC Exchange Rate Canister queries | `services.py`, `endpoints.py` |
| **On-chain Encryption** — vetKeys + CryptoService | `services.py`, `endpoints.py` |
| **HTTP Outcalls** — fetch web pages from a canister | `endpoints.py` |
| **Persistent Filesystem** — read/write files that survive upgrades | `endpoints.py` |
| **Timers** — one-shot and periodic scheduling | `endpoints.py` |
| **Guards** — controller-only access control | `main.py` |
| **Interactive Shell** — `basilisk shell` / `basilisk exec` | `main.py` |
| **Lifecycle Hooks** — `@init`, `@post_upgrade` | `main.py` |
| **Frontend** — vanilla HTML/JS/CSS with `@dfinity/agent` | `src/frontend/` |

## Project Structure

```
src/
  backend/
    main.py        — entry point: DB setup, shell, lifecycle hooks
    models.py      — entity definitions (Donor, TipMessage)
    services.py    — wallet, FX, encryption service setup
    endpoints.py   — all @query and @update canister methods
  frontend/
    assets/
      index.html   — single-page UI
      app.js       — IC agent calls to backend
      style.css    — dark-theme styling
dfx.json           — IC project config (backend + frontend canisters)
```

## Quick Start

```bash
# 1. Start a local IC replica
dfx start --background

# 2. Deploy both canisters
dfx deploy

# 3. Try it out
dfx canister call tip_jar_backend status
dfx canister call tip_jar_backend register_donor '("Alice")'
dfx canister call tip_jar_backend leave_message '("Alice", "Hello world!")'
dfx canister call tip_jar_backend get_leaderboard

# 4. Open the frontend
echo "http://$(dfx canister id tip_jar_frontend).localhost:4943"

# 5. Interactive shell
basilisk shell --canister tip_jar_backend

# 6. One-shot exec
basilisk exec --canister tip_jar_backend 'print([d.name for d in Donor.instances()])'
```

## Async Endpoints (inter-canister calls)

Endpoints that call other canisters use Python generators with `yield`:

```python
@update
def check_balance(token_name: text) -> Async[text]:
    balance = yield wallet.balance_of(token_name)
    return json.dumps({"token": token_name, "balance": balance})
```

The `yield` suspends the Python function while the IC processes the
inter-canister call, then resumes with the result.

## Deploy to Mainnet

```bash
dfx deploy --network ic
```

## Learn More

- [basilisk documentation](https://github.com/smart-social-contracts/basilisk)
- [Internet Computer docs](https://internetcomputer.org/docs)
- [ic-python-db](https://github.com/smart-social-contracts/ic-python-db)
