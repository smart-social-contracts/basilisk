"""Tip Jar — Data models (ic-python-db entities).

Entities are persisted in a StableBTreeMap and survive canister upgrades.
Each entity class maps to a "table" with auto-incrementing integer IDs.
The ``__alias__`` field enables lookup by a human-readable key, e.g.
``Donor["alice"]`` instead of ``Donor.load(3)``.
"""

from ic_python_db import Entity, String, Integer


class Donor(Entity):
    """A registered donor who can leave tips and messages."""

    __alias__ = "name"

    name = String(max_length=100)
    principal = String(max_length=64)
    total_donated = Integer(default=0)        # ckBTC in satoshis (kept for backward compat)
    total_donated_cketh = Integer(default=0)   # ckETH in wei
    total_donated_icp = Integer(default=0)     # ICP in e8s
    total_donated_ckusdc = Integer(default=0)   # ckUSDC in 1e-6 units
    message_count = Integer(default=0)


class PendingTip(Entity):
    """A tip registration waiting for on-chain ckBTC verification.

    Created in step 1 (user submits name + message + planned amount).
    Consumed in step 2 (verify_tip matches an on-chain transfer).
    """

    donor_name = String(max_length=100)
    message = String(max_length=500)
    message_type = String(max_length=10)   # "public" or "secret"
    amount = Integer(default=0)            # claimed amount in satoshis
    token = String(max_length=50)
    principal = String(max_length=64)
    timestamp = Integer(default=0)


class TipMessage(Entity):
    """A message left alongside a verified tip."""

    donor_name = String(max_length=100)
    message = String(max_length=500)
    amount = Integer(default=0)
    token = String(max_length=50)
    timestamp = Integer(default=0)
    claimed_tx_id = String(max_length=64)  # indexer tx ID that was matched


class SecretNote(Entity):
    """An encrypted note that only the canister owner can read.

    Demonstrates vetKeys on-chain encryption.  The note text is stored
    encrypted; only the controller can decrypt via ``read_secret_notes``.
    """

    sender_name = String(max_length=100)
    sender_principal = String(max_length=64)
    encrypted_text = String(max_length=2000)
    timestamp = Integer(default=0)
