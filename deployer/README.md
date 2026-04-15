# Basilisk WASM Deployer

On-chain WASM repository + deployer canister for basilisk. Stores versioned
`cpython_canister_template.wasm` files and deploys new basilisk canisters from
them.

**Issue**: https://github.com/smart-social-contracts/basilisk/issues/40

## Quick Start

```bash
cd deployer

# Start local network
dfx start --background

# Deploy the deployer canister
dfx deploy

# Upload a WASM version
python3 scripts/upload_wasm.py 0.11.22 \
    ~/.config/basilisk/0.11.22/cpython_canister_template.wasm \
    --network local --description "Basilisk v0.11.22"

# List available versions
dfx canister call deployer list_versions

# Deploy a new canister from the stored WASM
dfx canister call deployer deploy '("{\"version\": \"0.11.22\"}")'
```

## API

### Admin endpoints (controller-only)

| Method | Args (JSON) | Description |
|--------|-------------|-------------|
| `upload_wasm_chunk` | `{version, chunk_index, data}` | Upload base64-encoded WASM chunk |
| `finalize_version` | `{version, description, expected_hash?}` | Assemble chunks and verify hash |
| `remove_version` | `{version}` | Remove a version from the store |

### Public endpoints

| Method | Args | Description |
|--------|------|-------------|
| `list_versions` | — | List finalized versions |
| `get_version_info` | version string | Get metadata for a version |
| `deploy` | `{version, controllers?, cycles?}` | Create + install a new canister |

## Architecture

```
┌─────────────────┐     upload_chunk()      ┌──────────────────┐
│   Admin / CI    │ ──────────────────────> │                  │
│                 │     finalize_version()   │    Deployer      │
│                 │ ──────────────────────> │    Canister       │
└─────────────────┘                         │                  │
                                            │  WASM store:     │
┌─────────────────┐     deploy()            │  v0.11.22.wasm   │
│   User          │ ──────────────────────> │  v0.11.23.wasm   │
│                 │ <────────────────────── │  ...              │
│                 │     {canister_id}        │                  │
└─────────────────┘                         └────────┬─────────┘
                                                     │
                                          create_canister()
                                          upload_chunk()
                                          install_chunked_code()
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │  New Canister     │
                                            │  (basilisk app)   │
                                            └──────────────────┘
```
