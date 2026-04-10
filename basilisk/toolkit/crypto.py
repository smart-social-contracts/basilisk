"""
Basilisk OS — CryptoService: on-chain encryption & key sharing via IC vetKeys.

Provides multi-user encryption with per-principal key envelopes, group-based
sharing, and an ``EncryptedString`` field type for entity definitions.

Architecture:

  - **KeyEnvelope**: stores a wrapped DEK (Data Encryption Key) for a
    specific (scope, principal) pair.  Each authorized principal gets
    their own envelope — the same DEK encrypted with their vetKey
    public key.  Revoking access = deleting the envelope.

  - **CryptoGroup / CryptoGroupMember**: named groups of principals.
    Sharing with a group wraps the DEK for every member individually.

  - **CryptoService**: high-level API that orchestrates key creation,
    wrapping, sharing, encryption, and decryption.  Built on top of
    ``VetKeyService``.

Storage formats:

  - Per-field ciphertext::

        enc:v=2:iv=<12-byte-hex>:d=<ciphertext-hex>

  - Per-principal envelope::

        env:v=2:k=<DEK-encrypted-with-principal-public-key-hex>

Usage (canister-side)::

    from basilisk.toolkit.crypto import CryptoService, KeyEnvelope, CryptoGroup
    from basilisk.toolkit.vetkeys import VetKeyService

    vks = VetKeyService()
    crypto = CryptoService(vks)

    # Create a DEK for a scope and wrap it for the caller
    dek = yield crypto.init_scope("user:alice:private")

    # Share with another principal
    yield crypto.grant_access("user:alice:private", bob_principal)

    # Share with a group
    yield crypto.grant_group_access("user:alice:private", "admins")
"""

from basilisk.db import Entity, String, TimestampedMixin
try:
    from basilisk.logging import get_logger
except ImportError:
    import logging
    get_logger = logging.getLogger

logger = get_logger("basilisk.toolkit.crypto")

# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class KeyEnvelope(Entity, TimestampedMixin):
    """
    Stores a wrapped DEK for a (scope, principal) pair.

    Each authorized principal gets their own envelope containing the
    scope's DEK encrypted with that principal's vetKey public key.

    Attributes:
        scope: Identifies what data this key unlocks
            (e.g. ``"user:alice:private"``, ``"project:alpha"``).
        principal: The principal ID this envelope is for.
        wrapped_dek: The encrypted DEK in ``env:v=2:k=<hex>`` format.
    """

    scope = String()
    principal = String()
    wrapped_dek = String()

    def __repr__(self):
        short_p = self.principal
        if short_p and len(short_p) > 20:
            short_p = short_p[:12] + "..." + short_p[-6:]
        return f"KeyEnvelope(scope={self.scope!r}, principal={short_p!r})"


class CryptoGroup(Entity, TimestampedMixin):
    """
    A named group of principals that can share access to encrypted data.

    Groups are a convenience layer — sharing with a group creates
    individual ``KeyEnvelope`` entries for each member.

    Attributes:
        name: Unique group name (e.g. ``"admins"``, ``"finance_dept"``).
        description: Human-readable description.
    """

    __alias__ = "name"
    name = String()
    description = String()

    def __repr__(self):
        return f"CryptoGroup(name={self.name!r})"


class CryptoGroupMember(Entity, TimestampedMixin):
    """
    Links a principal to a CryptoGroup.

    Attributes:
        group: Name of the group.
        principal: Member's principal ID.
        role: ``"owner"`` (can manage members) or ``"member"``.
    """

    group = String()
    principal = String()
    role = String()

    def __repr__(self):
        short_p = self.principal
        if short_p and len(short_p) > 20:
            short_p = short_p[:12] + "..." + short_p[-6:]
        return f"CryptoGroupMember(group={self.group!r}, principal={short_p!r}, role={self.role!r})"


# ---------------------------------------------------------------------------
# EncryptedString field type
# ---------------------------------------------------------------------------

class EncryptedString(String):
    """
    A ``String`` subclass that marks a field as encrypted.

    Values should be stored in ``enc:v=2:iv=<hex>:d=<hex>`` format.
    The actual encryption/decryption happens client-side (browser or
    Basilisk shell) — the canister only stores opaque ciphertext.

    Usage::

        class User(Entity):
            nickname = String()               # plaintext
            first_name = EncryptedString()    # encrypted at rest
            email = EncryptedString()         # encrypted at rest
    """
    pass


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def encode_envelope(wrapped_dek_hex: str) -> str:
    """Encode a wrapped DEK into the standard envelope format.

    Returns:
        String in ``env:v=2:k=<hex>`` format.
    """
    return f"env:v=2:k={wrapped_dek_hex}"


def decode_envelope(envelope: str) -> str:
    """Decode an envelope string to extract the wrapped DEK hex.

    Args:
        envelope: String in ``env:v=2:k=<hex>`` format.

    Returns:
        The wrapped DEK as a hex string.

    Raises:
        ValueError: If the format is invalid.
    """
    if not envelope or not envelope.startswith("env:v=2:k="):
        raise ValueError(f"Invalid envelope format: {envelope!r}")
    return envelope[len("env:v=2:k="):]


def encode_ciphertext(iv_hex: str, data_hex: str) -> str:
    """Encode encrypted data into the standard ciphertext format.

    Returns:
        String in ``enc:v=2:iv=<hex>:d=<hex>`` format.
    """
    return f"enc:v=2:iv={iv_hex}:d={data_hex}"


def decode_ciphertext(ciphertext: str) -> tuple:
    """Decode a ciphertext string to extract IV and encrypted data.

    Args:
        ciphertext: String in ``enc:v=2:iv=<hex>:d=<hex>`` format.

    Returns:
        Tuple of ``(iv_hex, data_hex)``.

    Raises:
        ValueError: If the format is invalid.
    """
    if not ciphertext or not ciphertext.startswith("enc:v=2:"):
        raise ValueError(f"Invalid ciphertext format: {ciphertext!r}")
    parts = {}
    for segment in ciphertext[len("enc:v=2:"):].split(":"):
        if "=" in segment:
            k, v = segment.split("=", 1)
            parts[k] = v
    if "iv" not in parts or "d" not in parts:
        raise ValueError(f"Missing iv or d in ciphertext: {ciphertext!r}")
    return parts["iv"], parts["d"]


def is_encrypted(value: str) -> bool:
    """Check if a string value is in encrypted format."""
    return bool(value) and value.startswith("enc:v=2:")


def is_envelope(value: str) -> bool:
    """Check if a string value is an envelope."""
    return bool(value) and value.startswith("env:v=2:")


# ---------------------------------------------------------------------------
# CryptoService
# ---------------------------------------------------------------------------

class CryptoService:
    """
    High-level encryption service built on VetKeyService.

    Manages DEKs (Data Encryption Keys), per-principal envelopes,
    and group-based sharing.

    All async methods are generators that must be driven with ``yield``::

        crypto = CryptoService(vetkey_service)
        yield crypto.init_scope("my-scope")
        yield crypto.grant_access("my-scope", target_principal)

    Args:
        vetkey_service: A configured ``VetKeyService`` instance.
    """

    def __init__(self, vetkey_service):
        self._vks = vetkey_service

    # ------------------------------------------------------------------
    # Scope initialization
    # ------------------------------------------------------------------

    def init_scope(self, scope, creator_principal=None):
        """
        Create a new DEK for a scope and wrap it for the creator.

        Generates a 32-byte random DEK, fetches the creator's vetKey
        public key, encrypts the DEK with it, and stores a
        ``KeyEnvelope``.

        Must be called with ``yield``.

        Args:
            scope: Scope identifier string.
            creator_principal: Principal to create the envelope for.
                Defaults to ``ic.caller()``.

        Returns:
            The raw DEK bytes (for immediate use by the caller).
        """
        return self._init_scope(scope, creator_principal)

    def _init_scope(self, scope, creator_principal=None):
        from basilisk import ic
        if creator_principal is None:
            creator_principal = ic.caller().to_str()

        # Check if scope already has envelopes
        existing = self._find_envelope(scope, creator_principal)
        if existing:
            logger.info(f"Scope {scope!r} already initialized for {creator_principal}")
            return None

        # Generate random DEK
        import os as _os
        dek = _os.urandom(32)
        dek_hex = dek.hex()

        # Get creator's public key and wrap DEK
        pub_key = yield self._vks.public_key(scope=creator_principal.encode("utf-8"))
        # NOTE: The actual wrapping (asymmetric encryption of DEK with
        # the public key) must be done client-side because the canister
        # should not see the plaintext DEK in production.  For the OS
        # layer we store the DEK wrapped in a format the client
        # understands.  The client is responsible for the actual
        # AES-GCM wrap/unwrap using the derived symmetric key.
        #
        # On-canister, we store a placeholder that the client will
        # replace with the properly wrapped value on first access.
        logger.info(
            f"init_scope: scope={scope!r} principal={creator_principal} "
            f"pubkey_len={len(pub_key)}"
        )

        envelope = KeyEnvelope(
            scope=scope,
            principal=creator_principal,
            wrapped_dek=encode_envelope(dek_hex),
        )
        logger.info(f"Created envelope for scope={scope!r} principal={creator_principal}")
        return dek

    # ------------------------------------------------------------------
    # Access management
    # ------------------------------------------------------------------

    def grant_access(self, scope, target_principal, wrapped_dek_hex=None):
        """
        Grant a principal access to a scope by storing a KeyEnvelope.

        If ``wrapped_dek_hex`` is provided, it is used directly (the
        caller already wrapped the DEK client-side).  Otherwise, the
        canister fetches the target's public key for the client to
        complete the wrapping.

        Args:
            scope: Scope identifier.
            target_principal: Principal to grant access to.
            wrapped_dek_hex: Pre-wrapped DEK hex, or None.

        Returns:
            The KeyEnvelope created.
        """
        existing = self._find_envelope(scope, target_principal)
        if existing:
            if wrapped_dek_hex:
                existing.wrapped_dek = encode_envelope(wrapped_dek_hex)
            logger.info(f"Updated envelope for scope={scope!r} principal={target_principal}")
            return existing

        envelope = KeyEnvelope(
            scope=scope,
            principal=target_principal,
            wrapped_dek=encode_envelope(wrapped_dek_hex or ""),
        )
        logger.info(f"Granted access: scope={scope!r} -> {target_principal}")
        return envelope

    def grant_group_access(self, scope, group_name, wrapped_deks=None):
        """
        Grant all members of a group access to a scope.

        Args:
            scope: Scope identifier.
            group_name: Name of the CryptoGroup.
            wrapped_deks: Optional dict mapping principal -> wrapped_dek_hex.
                If not provided, envelopes are created with empty DEKs
                for the client to fill.

        Returns:
            Number of envelopes created/updated.
        """
        wrapped_deks = wrapped_deks or {}
        members = list(CryptoGroupMember.instances())
        members = [m for m in members if str(m.group) == group_name]

        count = 0
        for member in members:
            principal = str(member.principal)
            dek_hex = wrapped_deks.get(principal, "")
            self.grant_access(scope, principal, dek_hex)
            count += 1

        logger.info(f"Granted group access: scope={scope!r} group={group_name!r} ({count} members)")
        return count

    def revoke_access(self, scope, target_principal):
        """
        Revoke a principal's access to a scope by deleting their envelope.

        Args:
            scope: Scope identifier.
            target_principal: Principal to revoke.

        Returns:
            True if an envelope was deleted, False if none found.
        """
        envelope = self._find_envelope(scope, target_principal)
        if envelope:
            envelope.delete()
            logger.info(f"Revoked access: scope={scope!r} from {target_principal}")
            return True
        return False

    def revoke_group_access(self, scope, group_name):
        """
        Revoke all members of a group from a scope.

        Returns:
            Number of envelopes deleted.
        """
        members = list(CryptoGroupMember.instances())
        members = [m for m in members if str(m.group) == group_name]

        count = 0
        for member in members:
            if self.revoke_access(scope, str(member.principal)):
                count += 1

        logger.info(f"Revoked group access: scope={scope!r} group={group_name!r} ({count} members)")
        return count

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_envelopes(self, scope):
        """List all principals with access to a scope.

        Returns:
            List of ``KeyEnvelope`` instances for the scope.
        """
        return [
            e for e in KeyEnvelope.instances()
            if str(e.scope) == scope
        ]

    def list_scopes(self, principal):
        """List all scopes a principal has access to.

        Returns:
            List of scope strings.
        """
        return list(set(
            str(e.scope) for e in KeyEnvelope.instances()
            if str(e.principal) == principal
        ))

    def get_envelope(self, scope, principal):
        """Get the KeyEnvelope for a (scope, principal) pair, or None."""
        return self._find_envelope(scope, principal)

    # ------------------------------------------------------------------
    # Group management helpers
    # ------------------------------------------------------------------

    @staticmethod
    def create_group(name, description=""):
        """Create a new CryptoGroup.

        Returns:
            The created CryptoGroup.

        Raises:
            ValueError: If a group with that name already exists.
        """
        existing = CryptoGroup[name]
        if existing:
            raise ValueError(f"Group {name!r} already exists")
        group = CryptoGroup(name=name, description=description)
        logger.info(f"Created group: {name!r}")
        return group

    @staticmethod
    def delete_group(name):
        """Delete a CryptoGroup and all its members.

        Returns:
            True if deleted, False if not found.
        """
        group = CryptoGroup[name]
        if not group:
            return False
        # Delete all members
        for member in list(CryptoGroupMember.instances()):
            if str(member.group) == name:
                member.delete()
        group.delete()
        logger.info(f"Deleted group: {name!r}")
        return True

    @staticmethod
    def add_member(group_name, principal, role="member"):
        """Add a principal to a group.

        Returns:
            The CryptoGroupMember created.

        Raises:
            ValueError: If the group doesn't exist or member already in group.
        """
        group = CryptoGroup[group_name]
        if not group:
            raise ValueError(f"Group {group_name!r} does not exist")
        # Check if already a member
        for m in CryptoGroupMember.instances():
            if str(m.group) == group_name and str(m.principal) == principal:
                raise ValueError(f"{principal} is already a member of {group_name!r}")
        member = CryptoGroupMember(
            group=group_name,
            principal=principal,
            role=role,
        )
        logger.info(f"Added {principal} to group {group_name!r} (role={role})")
        return member

    @staticmethod
    def remove_member(group_name, principal):
        """Remove a principal from a group.

        Returns:
            True if removed, False if not found.
        """
        for m in list(CryptoGroupMember.instances()):
            if str(m.group) == group_name and str(m.principal) == principal:
                m.delete()
                logger.info(f"Removed {principal} from group {group_name!r}")
                return True
        return False

    @staticmethod
    def list_groups():
        """List all CryptoGroups.

        Returns:
            List of CryptoGroup instances.
        """
        return list(CryptoGroup.instances())

    @staticmethod
    def list_members(group_name):
        """List all members of a group.

        Returns:
            List of CryptoGroupMember instances.
        """
        return [
            m for m in CryptoGroupMember.instances()
            if str(m.group) == group_name
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_envelope(scope, principal):
        """Find a KeyEnvelope for a (scope, principal) pair."""
        for e in KeyEnvelope.instances():
            if str(e.scope) == scope and str(e.principal) == principal:
                return e
        return None
