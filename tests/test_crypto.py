"""
Integration and unit tests for %group and %crypto shell commands,
and basilisk.toolkit.crypto format helpers.

Unit tests (TestFormatHelpers, TestGroupCodeGeneration, TestCryptoCodeGeneration,
TestHandleGroupDispatch, TestHandleCryptoDispatch) run without a canister.

Integration tests (TestGroup*, TestCrypto*) run against a live canister
on IC mainnet via dfx.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.shell import (
    _handle_magic,
    _handle_group,
    _handle_crypto,
    _group_list_code,
    _group_create_code,
    _group_delete_code,
    _group_members_code,
    _group_add_code,
    _group_remove_code,
    _crypto_status_code,
    _crypto_scopes_code,
    _crypto_envelopes_code,
    _crypto_init_code,
    _crypto_share_principal_code,
    _crypto_share_group_code,
    _crypto_revoke_principal_code,
    _crypto_revoke_group_code,
    _crypto_encrypt_file_code,
    _crypto_decrypt_file_code,
    _crypto_encrypt_text_code,
    _crypto_decrypt_text_code,
    _GROUP_USAGE,
    _CRYPTO_USAGE,
    canister_exec,
)
try:
    from basilisk.toolkit.crypto import (
        encode_envelope,
        decode_envelope,
        encode_ciphertext,
        decode_ciphertext,
        is_encrypted,
        is_envelope,
    )
    _HAS_CRYPTO = True
except (ImportError, ModuleNotFoundError):
    _HAS_CRYPTO = False

from tests.conftest import exec_on_canister, magic_on_canister

_skip_no_crypto = pytest.mark.skipif(
    not _HAS_CRYPTO,
    reason="basilisk.toolkit.crypto not importable (basilisk.db not installed)",
)


# ---------------------------------------------------------------------------
# Entity resolution preamble — ensures crypto entities are available
# ---------------------------------------------------------------------------

_CRYPTO_RESOLVE = (
    "if 'KeyEnvelope' not in dir():\n"
    "    try:\n"
    "        from basilisk.toolkit.crypto import (\n"
    "            KeyEnvelope, CryptoGroup, CryptoGroupMember,\n"
    "            encode_envelope, decode_envelope,\n"
    "            encode_ciphertext, decode_ciphertext,\n"
    "            is_encrypted, is_envelope,\n"
    "        )\n"
    "    except ImportError:\n"
    "        pass\n"
)


# ===========================================================================
# Pure unit tests — no canister needed
# ===========================================================================

@_skip_no_crypto
class TestFormatHelpers:
    """Test encode/decode format helpers locally (no canister)."""

    # -- encode_envelope / decode_envelope --

    def test_encode_envelope(self):
        result = encode_envelope("deadbeef")
        assert result == "env:v=2:k=deadbeef"

    def test_decode_envelope(self):
        result = decode_envelope("env:v=2:k=deadbeef")
        assert result == "deadbeef"

    def test_encode_decode_envelope_roundtrip(self):
        original = "abcdef1234567890"
        assert decode_envelope(encode_envelope(original)) == original

    def test_decode_envelope_invalid(self):
        with pytest.raises(ValueError):
            decode_envelope("not_an_envelope")

    def test_decode_envelope_empty(self):
        with pytest.raises(ValueError):
            decode_envelope("")

    def test_decode_envelope_none(self):
        with pytest.raises(ValueError):
            decode_envelope(None)

    def test_decode_envelope_wrong_version(self):
        with pytest.raises(ValueError):
            decode_envelope("env:v=1:k=deadbeef")

    # -- encode_ciphertext / decode_ciphertext --

    def test_encode_ciphertext(self):
        result = encode_ciphertext("aabbccdd", "11223344")
        assert result == "enc:v=2:iv=aabbccdd:d=11223344"

    def test_decode_ciphertext(self):
        iv, data = decode_ciphertext("enc:v=2:iv=aabbccdd:d=11223344")
        assert iv == "aabbccdd"
        assert data == "11223344"

    def test_encode_decode_ciphertext_roundtrip(self):
        iv = "aabbccddeeff"
        data = "00112233445566778899"
        result_iv, result_data = decode_ciphertext(encode_ciphertext(iv, data))
        assert result_iv == iv
        assert result_data == data

    def test_decode_ciphertext_invalid(self):
        with pytest.raises(ValueError):
            decode_ciphertext("not_encrypted")

    def test_decode_ciphertext_missing_iv(self):
        with pytest.raises(ValueError):
            decode_ciphertext("enc:v=2:d=1234")

    def test_decode_ciphertext_missing_data(self):
        with pytest.raises(ValueError):
            decode_ciphertext("enc:v=2:iv=1234")

    def test_decode_ciphertext_empty(self):
        with pytest.raises(ValueError):
            decode_ciphertext("")

    def test_decode_ciphertext_none(self):
        with pytest.raises(ValueError):
            decode_ciphertext(None)

    # -- is_encrypted / is_envelope --

    def test_is_encrypted_true(self):
        assert is_encrypted("enc:v=2:iv=aa:d=bb") is True

    def test_is_encrypted_false(self):
        assert is_encrypted("plaintext") is False

    def test_is_encrypted_empty(self):
        assert is_encrypted("") is False

    def test_is_encrypted_none(self):
        assert is_encrypted(None) is False

    def test_is_envelope_true(self):
        assert is_envelope("env:v=2:k=deadbeef") is True

    def test_is_envelope_false(self):
        assert is_envelope("plaintext") is False

    def test_is_envelope_empty(self):
        assert is_envelope("") is False

    def test_is_envelope_none(self):
        assert is_envelope(None) is False


class TestGroupCodeGeneration:
    """Test that %group code generation functions produce valid Python."""

    def test_list_code_valid(self):
        code = _group_list_code()
        assert "CryptoGroup" in code
        compile(code, "<test>", "exec")

    def test_create_code_valid(self):
        code = _group_create_code("admins", "Administrators")
        assert "'admins'" in code
        assert "'Administrators'" in code
        compile(code, "<test>", "exec")

    def test_create_code_no_description(self):
        code = _group_create_code("testers")
        assert "'testers'" in code
        compile(code, "<test>", "exec")

    def test_delete_code_valid(self):
        code = _group_delete_code("admins")
        assert "'admins'" in code
        assert ".delete()" in code
        compile(code, "<test>", "exec")

    def test_members_code_valid(self):
        code = _group_members_code("admins")
        assert "'admins'" in code
        compile(code, "<test>", "exec")

    def test_add_code_valid(self):
        code = _group_add_code("admins", "abc-principal-123")
        assert "'admins'" in code
        assert "'abc-principal-123'" in code
        compile(code, "<test>", "exec")

    def test_remove_code_valid(self):
        code = _group_remove_code("admins", "abc-principal-123")
        assert "'admins'" in code
        assert "'abc-principal-123'" in code
        assert "KeyEnvelope" in code
        compile(code, "<test>", "exec")

    def test_escaping_single_quotes(self):
        code = _group_create_code("O'Brien", "it's a test")
        assert "O\\'Brien" in code
        assert "it\\'s" in code
        compile(code, "<test>", "exec")


class TestCryptoCodeGeneration:
    """Test that %crypto code generation functions produce valid Python."""

    def test_status_code_valid(self):
        code = _crypto_status_code()
        assert "KeyEnvelope" in code
        assert "ic.caller" in code
        compile(code, "<test>", "exec")

    def test_scopes_code_valid(self):
        code = _crypto_scopes_code()
        assert "KeyEnvelope" in code
        compile(code, "<test>", "exec")

    def test_envelopes_code_valid(self):
        code = _crypto_envelopes_code("user:alice")
        assert "'user:alice'" in code
        assert "CryptoGroupMember" in code
        compile(code, "<test>", "exec")

    def test_init_code_valid(self):
        code = _crypto_init_code("project:alpha")
        assert "'project:alpha'" in code
        assert "urandom" in code
        compile(code, "<test>", "exec")

    def test_share_principal_code_valid(self):
        code = _crypto_share_principal_code("project:alpha", "bob-principal")
        assert "'project:alpha'" in code
        assert "'bob-principal'" in code
        compile(code, "<test>", "exec")

    def test_share_group_code_valid(self):
        code = _crypto_share_group_code("project:alpha", "admins")
        assert "'project:alpha'" in code
        assert "'admins'" in code
        assert "CryptoGroupMember" in code
        compile(code, "<test>", "exec")

    def test_revoke_principal_code_valid(self):
        code = _crypto_revoke_principal_code("project:alpha", "bob-principal")
        assert "'project:alpha'" in code
        assert "'bob-principal'" in code
        assert ".delete()" in code
        compile(code, "<test>", "exec")

    def test_revoke_group_code_valid(self):
        code = _crypto_revoke_group_code("project:alpha", "admins")
        assert "'project:alpha'" in code
        assert "'admins'" in code
        compile(code, "<test>", "exec")

    def test_encrypt_file_code_valid(self):
        code = _crypto_encrypt_file_code("/data/secret.txt", "default")
        assert "'/data/secret.txt'" in code
        assert "encode_ciphertext" in code
        compile(code, "<test>", "exec")

    def test_decrypt_file_code_valid(self):
        code = _crypto_decrypt_file_code("/data/secret.txt")
        assert "'/data/secret.txt'" in code
        assert "decode_ciphertext" in code
        compile(code, "<test>", "exec")

    def test_encrypt_text_code_valid(self):
        code = _crypto_encrypt_text_code("hello world", "default")
        assert "'hello world'" in code
        compile(code, "<test>", "exec")

    def test_decrypt_text_code_valid(self):
        code = _crypto_decrypt_text_code("enc:v=2:iv=aa:d=bb")
        compile(code, "<test>", "exec")

    def test_escaping_single_quotes(self):
        code = _crypto_encrypt_text_code("it's a secret", "default")
        assert "it\\'s" in code
        compile(code, "<test>", "exec")

    def test_escaping_scope_single_quotes(self):
        code = _crypto_encrypt_file_code("/tmp/test.txt", "O'Brien")
        assert "O\\'Brien" in code
        compile(code, "<test>", "exec")


class TestHandleGroupDispatch:
    """Test _handle_group dispatcher routing (no canister needed)."""

    def test_help_returns_usage(self):
        result = _handle_group("help", "dummy", "dummy")
        assert "Usage:" in result
        assert "%group" in result

    def test_create_missing_name(self):
        result = _handle_group("create", "dummy", "dummy")
        assert "Usage:" in result

    def test_delete_missing_name(self):
        result = _handle_group("delete", "dummy", "dummy")
        assert "Usage:" in result

    def test_members_missing_name(self):
        result = _handle_group("members", "dummy", "dummy")
        assert "Usage:" in result

    def test_add_missing_args(self):
        result = _handle_group("add admins", "dummy", "dummy")
        assert "Usage:" in result

    def test_add_missing_both(self):
        result = _handle_group("add", "dummy", "dummy")
        assert "Usage:" in result

    def test_remove_missing_args(self):
        result = _handle_group("remove admins", "dummy", "dummy")
        assert "Usage:" in result

    def test_remove_missing_both(self):
        result = _handle_group("remove", "dummy", "dummy")
        assert "Usage:" in result

    def test_unknown_subcommand(self):
        result = _handle_group("foobar", "dummy", "dummy")
        assert "Unknown group command: foobar" in result
        assert "Usage:" in result

    def test_magic_dispatch_group(self):
        result = _handle_magic("%group help", "dummy", "dummy")
        assert result is not None
        assert "Usage:" in result

    def test_magic_dispatch_group_bare(self):
        result = _handle_magic("%group", "dummy", "dummy")
        assert result is not None


class TestHandleCryptoDispatch:
    """Test _handle_crypto dispatcher routing (no canister needed)."""

    def test_help_returns_usage(self):
        result = _handle_crypto("help", "dummy", "dummy")
        assert "Usage:" in result
        assert "%crypto" in result

    def test_bare_returns_usage(self):
        result = _handle_crypto("", "dummy", "dummy")
        assert "Usage:" in result

    def test_envelopes_missing_scope(self):
        result = _handle_crypto("envelopes", "dummy", "dummy")
        assert "Usage:" in result

    def test_encrypt_missing_file(self):
        result = _handle_crypto("encrypt", "dummy", "dummy")
        assert "Usage:" in result

    def test_decrypt_missing_file(self):
        result = _handle_crypto("decrypt", "dummy", "dummy")
        assert "Usage:" in result

    def test_encrypt_text_missing_text(self):
        result = _handle_crypto("encrypt-text", "dummy", "dummy")
        assert "Usage:" in result

    def test_decrypt_text_missing_text(self):
        result = _handle_crypto("decrypt-text", "dummy", "dummy")
        assert "Usage:" in result

    def test_share_missing_args(self):
        result = _handle_crypto("share", "dummy", "dummy")
        assert "Usage:" in result

    def test_share_missing_target(self):
        result = _handle_crypto("share myscope", "dummy", "dummy")
        assert "Usage:" in result

    def test_revoke_missing_args(self):
        result = _handle_crypto("revoke", "dummy", "dummy")
        assert "Usage:" in result

    def test_revoke_missing_target(self):
        result = _handle_crypto("revoke myscope", "dummy", "dummy")
        assert "Usage:" in result

    def test_unknown_subcommand(self):
        result = _handle_crypto("foobar", "dummy", "dummy")
        assert "Unknown crypto command: foobar" in result
        assert "Usage:" in result

    def test_magic_dispatch_crypto(self):
        result = _handle_magic("%crypto help", "dummy", "dummy")
        assert result is not None
        assert "Usage:" in result

    def test_magic_dispatch_crypto_bare(self):
        result = _handle_magic("%crypto", "dummy", "dummy")
        assert result is not None
        assert "Usage:" in result


class TestUsageMessages:
    """Verify usage strings contain all subcommands."""

    def test_group_usage_subcommands(self):
        for subcmd in ["create", "delete", "members", "add", "remove"]:
            assert subcmd in _GROUP_USAGE, f"Missing subcommand: {subcmd}"

    def test_crypto_usage_subcommands(self):
        for subcmd in ["status", "scopes", "encrypt", "decrypt",
                        "share", "revoke", "envelopes", "init"]:
            assert subcmd in _CRYPTO_USAGE, f"Missing subcommand: {subcmd}"


# ===========================================================================
# Integration tests — require a live canister
# ===========================================================================

@pytest.fixture(scope="module")
def _ensure_canister(canister_reachable):
    """Gate integration tests on canister availability."""
    return canister_reachable


@pytest.fixture(scope="module")
def _resolve_crypto(_ensure_canister):
    """Resolve crypto entities on the canister.

    Skips all integration tests if the canister hasn't been upgraded
    with the crypto module yet (ImportError from canister).
    """
    # First, probe whether the module is available at all.
    probe = exec_on_canister(
        "from basilisk.toolkit.crypto import KeyEnvelope\n"
        "print('crypto_available')\n"
    )
    if "ImportError" in probe or "cannot import" in probe or "crypto_available" not in probe:
        pytest.skip(
            "Canister does not have basilisk.toolkit.crypto yet — "
            "redeploy canister with updated code first"
        )
    # Now do the full resolve (with try/except for safety on the canister side).
    result = exec_on_canister(
        _CRYPTO_RESOLVE + "print('crypto_entities_ready')"
    )
    assert "crypto_entities_ready" in result, f"Failed to resolve crypto entities: {result}"
    return True


# ---------------------------------------------------------------------------
# Cleanup helper — remove all test entities by prefix
# ---------------------------------------------------------------------------

_TEST_PREFIX = "_test_crypto_"


def _cleanup_groups(prefix=_TEST_PREFIX):
    """Delete all CryptoGroups and CryptoGroupMembers matching prefix."""
    exec_on_canister(
        _CRYPTO_RESOLVE +
        f"_prefix = '{prefix}'\n"
        "for _m in list(CryptoGroupMember.instances()):\n"
        "    if str(_m.group).startswith(_prefix):\n"
        "        _m.delete()\n"
        "for _g in list(CryptoGroup.instances()):\n"
        "    if str(_g.name).startswith(_prefix):\n"
        "        _g.delete()\n"
        "print('cleanup_groups_done')\n"
    )


def _cleanup_envelopes(prefix=_TEST_PREFIX):
    """Delete all KeyEnvelopes with scope matching prefix."""
    exec_on_canister(
        _CRYPTO_RESOLVE +
        f"_prefix = '{prefix}'\n"
        "for _e in list(KeyEnvelope.instances()):\n"
        "    if str(_e.scope).startswith(_prefix):\n"
        "        _e.delete()\n"
        "print('cleanup_envelopes_done')\n"
    )


def _cleanup_all(prefix=_TEST_PREFIX):
    """Clean up all test groups and envelopes."""
    _cleanup_groups(prefix)
    _cleanup_envelopes(prefix)


# ===========================================================================
# %group integration tests
# ===========================================================================

class TestGroupList:
    """Test %group list on live canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_group_list_empty_or_populated(self):
        """Should return output (either 'No groups' or a listing)."""
        result = magic_on_canister("%group")
        assert result is not None
        assert "No groups" in result or "members" in result

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_group_list_explicit(self):
        result = magic_on_canister("%group list")
        assert result is not None


class TestGroupCreateDelete:
    """Test %group create and %group delete on live canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_create_and_delete_group(self, canister, network):
        name = f"{_TEST_PREFIX}create_del"
        try:
            # Create
            result = magic_on_canister(f"%group create {name} Test group for deletion")
            assert "Created group" in result

            # Verify it appears in listing
            list_result = magic_on_canister("%group list")
            assert name in list_result

            # Delete
            del_result = magic_on_canister(f"%group delete {name}")
            assert "Deleted group" in del_result

            # Verify it's gone
            list_after = magic_on_canister("%group list")
            assert name not in list_after or "No groups" in list_after
        finally:
            _cleanup_groups()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_create_duplicate_group(self, canister, network):
        name = f"{_TEST_PREFIX}dup"
        try:
            magic_on_canister(f"%group create {name}")
            result = magic_on_canister(f"%group create {name}")
            assert "already exists" in result
        finally:
            _cleanup_groups()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_delete_nonexistent_group(self):
        result = magic_on_canister(f"%group delete {_TEST_PREFIX}nonexistent_xyz")
        assert "not found" in result


class TestGroupMembers:
    """Test %group add, remove, members on live canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_add_and_list_members(self, canister, network):
        name = f"{_TEST_PREFIX}members"
        princ1 = "aaaaa-aa"
        princ2 = "bbbbb-bb"
        try:
            magic_on_canister(f"%group create {name}")

            # Add two members
            r1 = magic_on_canister(f"%group add {name} {princ1}")
            assert "Added" in r1

            r2 = magic_on_canister(f"%group add {name} {princ2}")
            assert "Added" in r2

            # List members
            members = magic_on_canister(f"%group members {name}")
            assert princ1 in members
            assert princ2 in members
            assert "member" in members
        finally:
            _cleanup_groups()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_add_duplicate_member(self, canister, network):
        name = f"{_TEST_PREFIX}dup_member"
        princ = "ccccc-cc"
        try:
            magic_on_canister(f"%group create {name}")
            magic_on_canister(f"%group add {name} {princ}")
            result = magic_on_canister(f"%group add {name} {princ}")
            assert "already a member" in result
        finally:
            _cleanup_groups()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_add_to_nonexistent_group(self):
        result = magic_on_canister(f"%group add {_TEST_PREFIX}nogroup_xyz aaaaa-aa")
        assert "not found" in result

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_remove_member(self, canister, network):
        name = f"{_TEST_PREFIX}remove"
        princ = "ddddd-dd"
        try:
            magic_on_canister(f"%group create {name}")
            magic_on_canister(f"%group add {name} {princ}")

            result = magic_on_canister(f"%group remove {name} {princ}")
            assert "Removed" in result

            members = magic_on_canister(f"%group members {name}")
            assert princ not in members or "no members" in members.lower()
        finally:
            _cleanup_groups()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_remove_nonexistent_member(self, canister, network):
        name = f"{_TEST_PREFIX}rm_noone"
        try:
            magic_on_canister(f"%group create {name}")
            result = magic_on_canister(f"%group remove {name} zzzzz-zz")
            assert "not a member" in result
        finally:
            _cleanup_groups()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_members_empty_group(self, canister, network):
        name = f"{_TEST_PREFIX}empty_grp"
        try:
            magic_on_canister(f"%group create {name}")
            result = magic_on_canister(f"%group members {name}")
            assert "no members" in result.lower()
        finally:
            _cleanup_groups()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_members_nonexistent_group(self):
        result = magic_on_canister(f"%group members {_TEST_PREFIX}nogroup_xyz")
        assert "not found" in result

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_delete_group_removes_members(self, canister, network):
        """Deleting a group should also remove all its members."""
        name = f"{_TEST_PREFIX}del_members"
        try:
            magic_on_canister(f"%group create {name}")
            magic_on_canister(f"%group add {name} aaaaa-aa")
            magic_on_canister(f"%group add {name} bbbbb-bb")

            result = magic_on_canister(f"%group delete {name}")
            assert "Deleted" in result
            assert "2 members removed" in result

            # Verify members are gone too (can't list members of deleted group)
            result = magic_on_canister(f"%group members {name}")
            assert "not found" in result
        finally:
            _cleanup_groups()


# ===========================================================================
# %crypto integration tests
# ===========================================================================

class TestCryptoStatus:
    """Test %crypto status on live canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_status_shows_identity(self):
        result = magic_on_canister("%crypto status")
        assert "Identity:" in result
        assert "Accessible scopes:" in result


class TestCryptoScopes:
    """Test %crypto scopes on live canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_scopes_output(self):
        result = magic_on_canister("%crypto scopes")
        # Either "No encryption scopes" or a table
        assert "scope" in result.lower() or "No encryption scopes" in result


class TestCryptoInit:
    """Test %crypto init on live canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_init_creates_dek(self, canister, network):
        scope = f"{_TEST_PREFIX}init_scope"
        try:
            result = magic_on_canister(f"%crypto init --scope {scope}")
            assert "Created DEK" in result
            assert scope in result

            # Verify it appears in scopes
            scopes_result = magic_on_canister("%crypto scopes")
            assert scope in scopes_result
        finally:
            _cleanup_envelopes()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_init_duplicate_scope(self, canister, network):
        scope = f"{_TEST_PREFIX}init_dup"
        try:
            magic_on_canister(f"%crypto init --scope {scope}")
            result = magic_on_canister(f"%crypto init --scope {scope}")
            assert "already initialized" in result
        finally:
            _cleanup_envelopes()


class TestCryptoEnvelopes:
    """Test %crypto envelopes on live canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_envelopes_empty_scope(self):
        result = magic_on_canister(f"%crypto envelopes {_TEST_PREFIX}nosuch_xyz")
        assert "No envelopes" in result

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_envelopes_after_init(self, canister, network):
        scope = f"{_TEST_PREFIX}env_init"
        try:
            magic_on_canister(f"%crypto init --scope {scope}")
            result = magic_on_canister(f"%crypto envelopes {scope}")
            assert "Authorized principals: 1" in result
            assert "(self)" in result
        finally:
            _cleanup_envelopes()


class TestCryptoShareRevoke:
    """Test %crypto share and revoke with principals on live canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_share_with_principal(self, canister, network):
        scope = f"{_TEST_PREFIX}share_p"
        target = "share-test-principal-xyz"
        try:
            magic_on_canister(f"%crypto init --scope {scope}")
            result = magic_on_canister(f"%crypto share {scope} --with {target}")
            assert "Shared" in result

            # Verify envelope exists
            env_result = magic_on_canister(f"%crypto envelopes {scope}")
            assert target in env_result
            assert "Authorized principals: 2" in env_result
        finally:
            _cleanup_envelopes()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_share_duplicate_principal(self, canister, network):
        scope = f"{_TEST_PREFIX}share_dup"
        target = "dup-test-principal-xyz"
        try:
            magic_on_canister(f"%crypto init --scope {scope}")
            magic_on_canister(f"%crypto share {scope} --with {target}")
            result = magic_on_canister(f"%crypto share {scope} --with {target}")
            assert "already has access" in result
        finally:
            _cleanup_envelopes()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_revoke_principal(self, canister, network):
        scope = f"{_TEST_PREFIX}revoke_p"
        target = "revoke-test-principal-xyz"
        try:
            magic_on_canister(f"%crypto init --scope {scope}")
            magic_on_canister(f"%crypto share {scope} --with {target}")

            result = magic_on_canister(f"%crypto revoke {scope} --from {target}")
            assert "Revoked" in result

            env_result = magic_on_canister(f"%crypto envelopes {scope}")
            assert target not in env_result
            assert "Authorized principals: 1" in env_result
        finally:
            _cleanup_envelopes()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_revoke_nonexistent_principal(self, canister, network):
        scope = f"{_TEST_PREFIX}revoke_no"
        try:
            magic_on_canister(f"%crypto init --scope {scope}")
            result = magic_on_canister(f"%crypto revoke {scope} --from nobody-xyz")
            assert "no envelope" in result
        finally:
            _cleanup_envelopes()


class TestCryptoShareGroup:
    """Test %crypto share/revoke with groups on live canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_share_with_group(self, canister, network):
        scope = f"{_TEST_PREFIX}share_grp"
        group = f"{_TEST_PREFIX}grp_share"
        p1 = "grp-member-aaa"
        p2 = "grp-member-bbb"
        try:
            # Set up group
            magic_on_canister(f"%group create {group}")
            magic_on_canister(f"%group add {group} {p1}")
            magic_on_canister(f"%group add {group} {p2}")

            # Init scope and share with group
            magic_on_canister(f"%crypto init --scope {scope}")
            result = magic_on_canister(f"%crypto share {scope} --with-group {group}")
            assert "2 new" in result

            # Both members should have envelopes
            env_result = magic_on_canister(f"%crypto envelopes {scope}")
            assert p1 in env_result
            assert p2 in env_result
        finally:
            _cleanup_all()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_share_with_nonexistent_group(self, canister, network):
        scope = f"{_TEST_PREFIX}share_nogrp"
        try:
            magic_on_canister(f"%crypto init --scope {scope}")
            result = magic_on_canister(f"%crypto share {scope} --with-group {_TEST_PREFIX}nogroup_xyz")
            assert "not found" in result
        finally:
            _cleanup_all()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_revoke_group(self, canister, network):
        scope = f"{_TEST_PREFIX}revoke_grp"
        group = f"{_TEST_PREFIX}grp_revoke"
        p1 = "rvk-member-aaa"
        p2 = "rvk-member-bbb"
        try:
            magic_on_canister(f"%group create {group}")
            magic_on_canister(f"%group add {group} {p1}")
            magic_on_canister(f"%group add {group} {p2}")

            magic_on_canister(f"%crypto init --scope {scope}")
            magic_on_canister(f"%crypto share {scope} --with-group {group}")

            result = magic_on_canister(f"%crypto revoke {scope} --from-group {group}")
            assert "Revoked 2 envelope(s)" in result

            # Only self should remain
            env_result = magic_on_canister(f"%crypto envelopes {scope}")
            assert p1 not in env_result
            assert p2 not in env_result
            assert "Authorized principals: 1" in env_result
        finally:
            _cleanup_all()


class TestCryptoEncryptDecryptFile:
    """Test %crypto encrypt/decrypt files on live canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_encrypt_decrypt_file_roundtrip(self, canister, network):
        path = "/_test_crypto_file.txt"
        content = "Hello, encrypted world!"
        try:
            # Write a file to canister
            exec_on_canister(
                f"with open('{path}', 'w') as f:\n"
                f"    f.write('{content}')\n"
                "print('wrote file')\n"
            )

            # Encrypt it
            enc_result = magic_on_canister(f"%crypto encrypt {path} --scope default")
            assert "Encrypted" in enc_result
            assert str(len(content)) in enc_result

            # Verify it's encrypted
            cat_result = exec_on_canister(
                f"with open('{path}', 'r') as f:\n"
                f"    print(f.read())\n"
            )
            assert cat_result.startswith("enc:v=2:")

            # Decrypt it
            dec_result = magic_on_canister(f"%crypto decrypt {path}")
            assert "Decrypted" in dec_result

            # Verify contents restored
            cat_after = exec_on_canister(
                f"with open('{path}', 'r') as f:\n"
                f"    print(f.read())\n"
            )
            assert cat_after == content
        finally:
            exec_on_canister(
                f"import os; os.remove('{path}') if os.path.exists('{path}') else None"
            )

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_encrypt_already_encrypted_file(self, canister, network):
        path = "/_test_crypto_already_enc.txt"
        try:
            exec_on_canister(
                f"with open('{path}', 'w') as f:\n"
                f"    f.write('enc:v=2:iv=aabb:d=ccdd')\n"
                "print('wrote')\n"
            )
            result = magic_on_canister(f"%crypto encrypt {path}")
            assert "Already encrypted" in result
        finally:
            exec_on_canister(
                f"import os; os.remove('{path}') if os.path.exists('{path}') else None"
            )

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_encrypt_nonexistent_file(self):
        result = magic_on_canister("%crypto encrypt /_test_crypto_nofile_xyz.txt")
        assert "No such file" in result

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_decrypt_nonexistent_file(self):
        result = magic_on_canister("%crypto decrypt /_test_crypto_nofile_xyz.txt")
        assert "No such file" in result

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_decrypt_plaintext_file(self, canister, network):
        path = "/_test_crypto_plain.txt"
        try:
            exec_on_canister(
                f"with open('{path}', 'w') as f:\n"
                f"    f.write('just plain text')\n"
                "print('wrote')\n"
            )
            result = magic_on_canister(f"%crypto decrypt {path}")
            assert "Not encrypted" in result
        finally:
            exec_on_canister(
                f"import os; os.remove('{path}') if os.path.exists('{path}') else None"
            )


class TestCryptoEncryptDecryptText:
    """Test %crypto encrypt-text/decrypt-text on live canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_encrypt_text_produces_ciphertext(self):
        result = magic_on_canister("%crypto encrypt-text hello")
        assert result.startswith("enc:v=2:")

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_encrypt_decrypt_text_roundtrip(self, canister, network):
        plaintext = "SecretMessage123"
        enc_result = magic_on_canister(f"%crypto encrypt-text {plaintext}")
        assert enc_result.startswith("enc:v=2:")

        dec_result = magic_on_canister(f"%crypto decrypt-text {enc_result}")
        assert dec_result == plaintext

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_decrypt_invalid_text(self):
        result = magic_on_canister("%crypto decrypt-text plaintext_not_encrypted")
        assert "Not in encrypted format" in result


class TestCryptoGroupRemoveRevokesEnvelopes:
    """Test that removing a member from a group also revokes their envelopes."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_remove_member_revokes_envelopes(self, canister, network):
        scope = f"{_TEST_PREFIX}grp_rm_env"
        group = f"{_TEST_PREFIX}grp_rm_env"
        principal = "remove-revoke-test-principal"
        try:
            # Create group, add member, init scope, share with group
            magic_on_canister(f"%group create {group}")
            magic_on_canister(f"%group add {group} {principal}")
            magic_on_canister(f"%crypto init --scope {scope}")
            magic_on_canister(f"%crypto share {scope} --with-group {group}")

            # Verify envelope exists
            env_result = magic_on_canister(f"%crypto envelopes {scope}")
            assert principal in env_result

            # Remove member from group (should revoke envelopes)
            rm_result = magic_on_canister(f"%group remove {group} {principal}")
            assert "Removed" in rm_result
            assert "Revoked" in rm_result
            assert "envelope" in rm_result.lower()

            # Verify envelope is gone
            env_after = magic_on_canister(f"%crypto envelopes {scope}")
            assert principal not in env_after
        finally:
            _cleanup_all()


# ===========================================================================
# Full end-to-end lifecycle
# ===========================================================================

class TestCryptoE2ELifecycle:
    """
    Full end-to-end test: create group, add members, init scope,
    share with group, encrypt file, verify envelopes, revoke,
    clean up. Tests the complete workflow on a live canister.
    """

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_full_lifecycle(self, canister, network):
        group = f"{_TEST_PREFIX}e2e_lifecycle"
        scope = f"{_TEST_PREFIX}e2e_scope"
        p1 = "e2e-alice-principal"
        p2 = "e2e-bob-principal"
        filepath = "/_test_crypto_e2e_data.txt"
        content = "Top secret financial data"

        try:
            # 1. Create a group
            r = magic_on_canister(f"%group create {group} E2E test group")
            assert "Created group" in r

            # 2. Add members
            r = magic_on_canister(f"%group add {group} {p1}")
            assert "Added" in r
            r = magic_on_canister(f"%group add {group} {p2}")
            assert "Added" in r

            # 3. Verify members
            members = magic_on_canister(f"%group members {group}")
            assert p1 in members
            assert p2 in members

            # 4. Init encryption scope
            r = magic_on_canister(f"%crypto init --scope {scope}")
            assert "Created DEK" in r

            # 5. Share scope with group
            r = magic_on_canister(f"%crypto share {scope} --with-group {group}")
            assert "2 new" in r

            # 6. Verify envelopes (self + 2 group members = 3)
            envs = magic_on_canister(f"%crypto envelopes {scope}")
            assert "Authorized principals: 3" in envs
            assert p1 in envs
            assert p2 in envs
            assert "(self)" in envs

            # 7. Write and encrypt a file
            exec_on_canister(
                f"with open('{filepath}', 'w') as f:\n"
                f"    f.write('{content}')\n"
                "print('wrote')\n"
            )
            r = magic_on_canister(f"%crypto encrypt {filepath} --scope {scope}")
            assert "Encrypted" in r

            # 8. Verify file is encrypted
            cat = exec_on_canister(
                f"with open('{filepath}', 'r') as f:\n"
                f"    print(f.read())\n"
            )
            assert cat.startswith("enc:v=2:")

            # 9. Decrypt file
            r = magic_on_canister(f"%crypto decrypt {filepath}")
            assert "Decrypted" in r

            # 10. Verify original content
            cat = exec_on_canister(
                f"with open('{filepath}', 'r') as f:\n"
                f"    print(f.read())\n"
            )
            assert cat == content

            # 11. Check crypto status shows the scope
            status = magic_on_canister("%crypto status")
            assert scope in status

            # 12. Revoke Bob's access
            r = magic_on_canister(f"%crypto revoke {scope} --from {p2}")
            assert "Revoked" in r

            # 13. Verify Bob's envelope is gone
            envs = magic_on_canister(f"%crypto envelopes {scope}")
            assert p2 not in envs
            assert p1 in envs
            assert "Authorized principals: 2" in envs

            # 14. Remove Alice from group (revokes envelopes)
            r = magic_on_canister(f"%group remove {group} {p1}")
            assert "Removed" in r

            # 15. Verify only self remains
            envs = magic_on_canister(f"%crypto envelopes {scope}")
            assert p1 not in envs
            assert "Authorized principals: 1" in envs

            # 16. Delete group
            r = magic_on_canister(f"%group delete {group}")
            assert "Deleted" in r

        finally:
            exec_on_canister(
                f"import os; os.remove('{filepath}') if os.path.exists('{filepath}') else None"
            )
            _cleanup_all()


class TestCryptoFormatHelpersOnCanister:
    """Test that format helpers work correctly when executed on the canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_encode_decode_envelope_on_canister(self):
        result = exec_on_canister(
            _CRYPTO_RESOLVE +
            "_env = encode_envelope('deadbeef1234')\n"
            "_decoded = decode_envelope(_env)\n"
            "print(f'{_env}|{_decoded}')\n"
        )
        parts = result.split("|")
        assert parts[0] == "env:v=2:k=deadbeef1234"
        assert parts[1] == "deadbeef1234"

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_encode_decode_ciphertext_on_canister(self):
        result = exec_on_canister(
            _CRYPTO_RESOLVE +
            "_ct = encode_ciphertext('aabbccdd', '11223344')\n"
            "_iv, _data = decode_ciphertext(_ct)\n"
            "print(f'{_ct}|{_iv}|{_data}')\n"
        )
        parts = result.split("|")
        assert parts[0] == "enc:v=2:iv=aabbccdd:d=11223344"
        assert parts[1] == "aabbccdd"
        assert parts[2] == "11223344"

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_is_encrypted_on_canister(self):
        result = exec_on_canister(
            _CRYPTO_RESOLVE +
            "print(is_encrypted('enc:v=2:iv=aa:d=bb'))\n"
            "print(is_encrypted('plaintext'))\n"
            "print(is_encrypted(''))\n"
        )
        lines = result.strip().split("\n")
        assert lines[0] == "True"
        assert lines[1] == "False"
        assert lines[2] == "False"

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_is_envelope_on_canister(self):
        result = exec_on_canister(
            _CRYPTO_RESOLVE +
            "print(is_envelope('env:v=2:k=dead'))\n"
            "print(is_envelope('plaintext'))\n"
        )
        lines = result.strip().split("\n")
        assert lines[0] == "True"
        assert lines[1] == "False"


class TestCryptoEntityCRUDOnCanister:
    """Test direct entity creation and querying on the canister."""

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_create_and_query_group(self, canister, network):
        name = f"{_TEST_PREFIX}entity_grp"
        try:
            result = exec_on_canister(
                _CRYPTO_RESOLVE +
                f"_g = CryptoGroup(name='{name}', description='Entity test')\n"
                f"_loaded = CryptoGroup['{name}']\n"
                "print(f'{_loaded.name}|{_loaded.description}')\n"
            )
            parts = result.split("|")
            assert parts[0] == name
            assert parts[1] == "Entity test"
        finally:
            _cleanup_groups()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_create_and_query_member(self, canister, network):
        group = f"{_TEST_PREFIX}entity_mem"
        princ = "entity-test-principal"
        try:
            exec_on_canister(
                _CRYPTO_RESOLVE +
                f"CryptoGroup(name='{group}', description='test')\n"
                f"CryptoGroupMember(group='{group}', principal='{princ}', role='member')\n"
                "print('created')\n"
            )
            result = exec_on_canister(
                _CRYPTO_RESOLVE +
                f"_members = [m for m in CryptoGroupMember.instances() if str(m.group) == '{group}']\n"
                "print(f'{len(_members)}|{_members[0].principal}|{_members[0].role}')\n"
            )
            parts = result.split("|")
            assert parts[0] == "1"
            assert parts[1] == princ
            assert parts[2] == "member"
        finally:
            _cleanup_groups()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_create_and_query_envelope(self, canister, network):
        scope = f"{_TEST_PREFIX}entity_env"
        princ = "envelope-test-principal"
        try:
            result = exec_on_canister(
                _CRYPTO_RESOLVE +
                f"_e = KeyEnvelope(scope='{scope}', principal='{princ}', wrapped_dek=encode_envelope('cafebabe'))\n"
                f"_found = [e for e in KeyEnvelope.instances() if str(e.scope) == '{scope}']\n"
                "print(f'{len(_found)}|{_found[0].principal}|{_found[0].wrapped_dek}')\n"
            )
            parts = result.split("|")
            assert parts[0] == "1"
            assert parts[1] == princ
            assert parts[2] == "env:v=2:k=cafebabe"
        finally:
            _cleanup_envelopes()

    @pytest.mark.usefixtures("_resolve_crypto")
    def test_delete_envelope(self, canister, network):
        scope = f"{_TEST_PREFIX}entity_del"
        princ = "delete-test-principal"
        try:
            exec_on_canister(
                _CRYPTO_RESOLVE +
                f"KeyEnvelope(scope='{scope}', principal='{princ}', wrapped_dek=encode_envelope('1234'))\n"
                "print('created')\n"
            )
            result = exec_on_canister(
                _CRYPTO_RESOLVE +
                f"_found = [e for e in KeyEnvelope.instances() if str(e.scope) == '{scope}']\n"
                "for _e in _found:\n"
                "    _e.delete()\n"
                f"_after = [e for e in KeyEnvelope.instances() if str(e.scope) == '{scope}']\n"
                "print(f'{len(_after)}')\n"
            )
            assert result == "0"
        finally:
            _cleanup_envelopes()
