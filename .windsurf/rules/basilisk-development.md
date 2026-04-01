---
trigger: always_on
description: Basilisk OS development rules covering entities, crypto, shell commands, and vetKeys
---

# Basilisk OS Development Rules

## Entity Patterns
- User entity: `id = String()` stores principal string, NO `principal` attribute
- Use `TimestampedMixin` for created/updated timestamps
- Note: `_timestamp_created` resets to 0 on DB load; use `timestamp_created` string attr

## DateTime
- `datetime.strptime` NOT available in IC canisters
- Use manual string parsing or `calendar.timegm` instead

## Crypto (basilisk.os.crypto)
- **Per-principal envelopes**: each authorized principal gets own wrapped DEK copy
- **No shared group keys**: revocation = delete KeyEnvelope entry
- **Storage formats**:
  - Ciphertext: `enc:v=2:iv=<12-byte-hex>:d=<ciphertext-hex>`
  - Envelope: `env:v=2:k=<DEK-encrypted-with-principal-public-key-hex>`
- **Entities**: `KeyEnvelope`, `CryptoGroup`, `CryptoGroupMember`
- Use `EncryptedString` field type for encrypted entity attributes

## Shell Commands
- `%group` — create/delete/add/remove/members for CryptoGroups
- `%crypto` — status/scopes/encrypt/decrypt/share/revoke/envelopes/init
- `%fx` — exchange rate operations

## VetKeys (basilisk.os.vetkeys)
- Use `VetKeyService` for on-chain key derivation
- Default key: `test_key_1` (development), `key_1` (production)
- Domain separator defaults to `b"basilisk"`

## Key Imports
```python
from basilisk.os.crypto import KeyEnvelope, CryptoGroup, CryptoGroupMember, CryptoService, EncryptedString
from basilisk.os.vetkeys import VetKeyService
from basilisk.os.fx import FXService
from basilisk.os.wallet import Wallet
```
