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
    total_donated = Integer(default=0)
    message_count = Integer(default=0)


class TipMessage(Entity):
    """A message left alongside a tip."""

    donor_name = String(max_length=100)
    message = String(max_length=500)
    amount = Integer(default=0)
    token = String(max_length=50)
    timestamp = Integer(default=0)
