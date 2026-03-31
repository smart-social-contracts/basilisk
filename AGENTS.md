# Agent Instructions for Basilisk

Basilisk is the OS layer for ICP canisters providing crypto, storage, and shell functionality.

## Key Technologies
- **Language**: Python (ic-python)
- **Storage**: ic-python-db with encrypted fields
- **Crypto**: vetKeys for on-chain encryption

## Important Patterns
- `datetime.strptime` NOT available — use manual parsing or `calendar.timegm`
- User entity: `id = String()` (principal string), no `principal` attr
- Timestamps: `_timestamp_created` resets to 0 on DB load; use `timestamp_created` string attr

## Skills
- Fetch from https://skills.internetcomputer.org when working on specific ICP features
- Use icp-cli skill for build/deploy guidance (NOT dfx)

## Crypto Architecture
- Per-principal envelopes — each authorized principal gets own wrapped DEK copy
- No shared group keys, revocation by deletion
- Storage formats: `enc:v=2:iv=<hex>:d=<ciphertext>` and `env:v=2:k=<hex>`

## OS Modules (basilisk.os)

### crypto — Encryption & Key Management
```python
from basilisk.os.crypto import KeyEnvelope, CryptoGroup, CryptoGroupMember, CryptoService, EncryptedString

# Entities
KeyEnvelope(scope, principal, wrapped_dek)  # Per-principal DEK wrapper
CryptoGroup(name, description)               # Named group of principals
CryptoGroupMember(group, principal, role)    # Group membership

# Encrypted field type
class MyEntity(Entity):
    secret = EncryptedString()  # Marks field as encrypted
```

### vetkeys — On-Chain Key Derivation
```python
from basilisk.os.vetkeys import VetKeyService

vks = VetKeyService(domain_separator=b"basilisk", key_name="test_key_1")
pub_key = yield vks.public_key(scope=principal_bytes)
context = vks.make_context(scope=principal_bytes)
```

### fx — Exchange Rates
```python
from basilisk.os.fx import FXService
fx = FXService()
rate = yield fx.get_rate("BTC", "USD")
```

### wallet — Token Management
```python
from basilisk.os.wallet import Wallet
wallet = Wallet(principal)
balance = yield wallet.balance()
```

### task_manager — Async Task Execution
```python
from basilisk.os.task_manager import TaskManager
tm = TaskManager()
task_id = yield tm.schedule(...)
```

## Shell Commands (basilisk/shell.py)

| Command | Description |
|---------|-------------|
| `%group` | Manage CryptoGroups (create/delete/add/remove/members) |
| `%crypto` | Encryption ops (status/scopes/encrypt/decrypt/share/revoke/envelopes/init) |
| `%fx` | Exchange rates (register/unregister/rate/info/refresh) |
| `%canister` | Canister management (call/install/start/stop/status) |
| `%wallet` | Wallet operations (balance/transfer/history) |

## Deployment
- Use `deploy_staging_dev.sh` for staging deploys
- Identity: `my_dev_identity_1` (principal `ah6ac-...`)
- Must `export DFX_WARNING=-mainnet_plaintext_identity`
