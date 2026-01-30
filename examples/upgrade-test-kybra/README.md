# Canister Upgrade Test (Kybra)

This example demonstrates **decentralized canister upgrades** using Kybra's management canister bindings for the IC's chunked code upload API.

## Overview

A **controller canister** upgrades a **target canister** without requiring `dfx` or external tools. This is essential for DAOs and autonomous systems that need to upgrade canisters programmatically.

### Key Features

- **Chunked WASM upload**: Large WASM modules are split into chunks and uploaded via `upload_chunk`
- **Module upgrades**: Demonstrates that imported modules are automatically updated (no `reload` needed)
- **Decentralized control**: The controller canister acts as a controller of the target

## Architecture

```
┌─────────────────┐     upload_chunk()      ┌────────────────────┐
│    Controller   │ ───────────────────────>│  Management        │
│    Canister     │     install_chunked_    │  Canister          │
│                 │     code()              │  (aaaaa-aa)        │
└─────────────────┘                         └────────────────────┘
                                                     │
                                                     │ upgrade
                                                     ▼
                                            ┌────────────────────┐
                                            │  Target Canister   │
                                            │  v1 → v2           │
                                            └────────────────────┘
```

## Files

| File | Description |
|------|-------------|
| `src/controller/main.py` | Controller canister with chunked upload logic |
| `src/target/main.py` | Target canister v1 (initial version) |
| `src/target/my_lib.py` | Shared module v1.0 |
| `src/target_v2/main.py` | Target canister v2 (upgraded version) |
| `src/target_v2/my_lib.py` | Shared module v2.0 |
| `call_upgrade.py` | Python script to orchestrate the upgrade |
| `test_upgrade.sh` | End-to-end test script |

## Running the Test

```bash
# Activate virtual environment
source venv/bin/activate

# Run the full test
./test_upgrade.sh
```

## Expected Results

### Before Upgrade
```
get_version()     → "v1"
get_lib_version() → "1.0"
greet("World")    → "Hello, World!"
```

### After Upgrade
```
get_version()     → "v2"
get_lib_version() → "2.0"  ← Module automatically updated!
greet("World")    → "Greetings, World! (upgraded)"
```

## Key Findings

1. **Modules update automatically**: When a canister is upgraded, all frozen Python modules are replaced with the new WASM. No `reload()` or special handling is required.

2. **Chunked upload works**: Large WASM files (>2MB) can be uploaded in chunks via the management canister API.

3. **Controller pattern**: A canister can upgrade other canisters if it has controller permissions.

## Requirements

- dfx 0.24+
- Kybra 0.7.1+
- Python 3.10+
