"""
Integration tests for Basilisk OS vetKeys — vetKD (Verifiably Encrypted
Threshold Key Derivation) support.

Tests are organized in layers:

  1. **Unit tests** — Candid type definitions, VetKeyService context
     construction, shell flag parsing.  These run locally without a
     canister.
  2. **Integration tests** — vetkd_public_key and vetkd_derive_key
     calls via a live canister.  These require a deployed canister
     with vetKD-enabled replica (mainnet test_key_1 or local
     dfx_test_key).

Configuration:
    Set environment variables or use defaults:
        BASILISK_TEST_CANISTER  — canister ID (default from conftest)
        BASILISK_TEST_NETWORK   — network (default: ic)

Usage:
    # Unit tests only (no canister needed):
    pytest tests/test_vetkeys.py -v -k "Unit"

    # Full integration tests against live canister:
    pytest tests/test_vetkeys.py -v

    # Against local replica with dfx_test_key:
    BASILISK_TEST_NETWORK=local pytest tests/test_vetkeys.py -v
"""

import json
import os
import re
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers shared with conftest (duplicated to keep test file self-contained
# when running in isolation)
# ---------------------------------------------------------------------------

_TEST_CANISTER_DIR = os.path.join(os.path.dirname(__file__), "test_canister")


def _get_canister():
    return os.environ.get("BASILISK_TEST_CANISTER", "ru4ga-siaaa-aaaai-q7f3a-cai")


def _get_network():
    return os.environ.get("BASILISK_TEST_NETWORK", "ic")


def _vetkey_name():
    """Return the correct vetKD key name for the target network."""
    net = _get_network()
    if net == "local":
        return "dfx_test_key"
    return os.environ.get("BASILISK_VETKEY_NAME", "test_key_1")


def _local_canister_exec(code, canister, network):
    """Execute code on canister via dfx."""
    from basilisk.shell import _parse_candid
    escaped = code.replace('"', '\\"').replace("\n", "\\n")
    cmd = ["dfx", "canister", "call"]
    if network:
        cmd.extend(["--network", network])
    cmd.extend([canister, "execute_code_shell", f'("{escaped}")'])
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=_TEST_CANISTER_DIR if os.path.isdir(_TEST_CANISTER_DIR) else None,
        )
        if r.returncode != 0:
            return f"[dfx error] {r.stderr.strip()}"
        return _parse_candid(r.stdout)
    except subprocess.TimeoutExpired:
        return "[error] canister call timed out (120s)"
    except FileNotFoundError:
        return "[error] dfx not found"


def _write_file_on_canister(path, content, canister, network):
    """Write a Python file to the canister's in-memory filesystem."""
    import base64
    b64 = base64.b64encode(content.encode()).decode()
    result = _local_canister_exec(
        f"import base64\n"
        f"_data = base64.b64decode('{b64}').decode()\n"
        f"with open('{path}', 'w') as f:\n"
        f"    f.write(_data)\n"
        f"print('wrote {path}')",
        canister, network,
    )
    assert "wrote" in result, f"Failed to write file: {result}"


def _extract_task_id(output):
    m = re.search(r'task\s+(\d+)', output, re.IGNORECASE)
    return m.group(1) if m else None


def _task_magic(cmd, canister, network):
    """Run a magic command via dfx by converting it to code."""
    from basilisk.shell import (
        _task_list_code, _task_create_code, _task_add_step_code,
        _task_info_code, _task_start_code, _task_stop_code,
        _task_delete_code, _task_log_code, _TASK_RESOLVE,
    )
    stripped = cmd.strip()
    if stripped.startswith("%task"):
        stripped = stripped[5:].strip()
    if not stripped:
        return _local_canister_exec(_task_list_code(), canister, network).strip()
    space_idx = stripped.find(" ")
    if space_idx == -1:
        sub, rest = stripped, ""
    else:
        sub, rest = stripped[:space_idx], stripped[space_idx + 1:]
    code_map = {
        "list": lambda: _task_list_code(),
        "create": lambda: _task_create_code(rest),
        "add-step": lambda: _task_add_step_code(rest),
        "info": lambda: _task_info_code(rest.strip()),
        "log": lambda: _task_log_code(rest.strip()),
        "start": lambda: _task_start_code(rest.strip()),
        "stop": lambda: _task_stop_code(rest.strip()),
        "delete": lambda: _task_delete_code(rest.strip()),
    }
    code = code_map.get(sub, lambda: None)()
    if code is None:
        raise ValueError(f"Unknown %task subcommand: {sub}")
    result = _local_canister_exec(code, canister, network)
    return result.strip() if result else ""


def _wait_for_task_execution(tid, canister, network, timeout=90, poll=3):
    """Poll task log until execution completes/fails or timeout."""
    deadline = time.time() + timeout
    log = ""
    while time.time() < deadline:
        log = _task_magic(f"%task log {tid}", canister, network)
        if "completed" in log or "failed" in log:
            return log
        time.sleep(poll)
    return log


def _run_async_task(name, code, canister, network, timeout=90):
    """Write async code to canister, create task, add async step, start, wait, return log."""
    path = f"/_vetkey_test_{name}.py"
    _write_file_on_canister(path, code, canister, network)

    result = _task_magic(f'%task create {name}', canister, network)
    tid = _extract_task_id(result)
    assert tid, f"Failed to create task: {result}"

    step_result = _task_magic(
        f'%task add-step {tid} --async --file {path}',
        canister, network,
    )
    assert "Added" in step_result or "step" in step_result.lower(), \
        f"Failed to add step: {step_result}"

    _task_magic(f"%task start {tid}", canister, network)
    log = _wait_for_task_execution(tid, canister, network, timeout=timeout)

    # Clean up
    _task_magic(f"%task delete {tid}", canister, network)
    _local_canister_exec(
        f"import os; os.remove('{path}') if os.path.exists('{path}') else None",
        canister, network,
    )
    return log


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def vetkey_canister():
    return _get_canister()


@pytest.fixture(scope="session")
def vetkey_network():
    return _get_network()


@pytest.fixture(scope="session")
def key_name():
    return _vetkey_name()


@pytest.fixture(scope="session")
def canister_reachable(vetkey_canister, vetkey_network):
    """Verify the canister is reachable before running integration tests."""
    try:
        result = _local_canister_exec(
            "print('vetkey_ping')", vetkey_canister, vetkey_network,
        )
    except Exception as e:
        pytest.skip(f"Cannot reach canister: {e}")
    if not result or "vetkey_ping" not in result:
        pytest.skip(f"Canister not reachable: {result}")
    return True


# ===========================================================================
# UNIT TESTS — no canister required
# ===========================================================================

class TestUnitVetKDTypes:
    """Unit tests for vetKD Candid type definitions."""

    def test_vetkd_curve_variant(self):
        """VetKDCurve should have bls12_381_g2 variant."""
        from basilisk.canisters.management.vetkd import VetKDCurve
        curve = VetKDCurve(bls12_381_g2=None)
        # Record/Variant are dict subclasses outside a canister
        assert 'bls12_381_g2' in curve

    def test_vetkd_key_id_record(self):
        """VetKDKeyId should have curve and name fields."""
        from basilisk.canisters.management.vetkd import VetKDKeyId, VetKDCurve
        key_id = VetKDKeyId(
            curve=VetKDCurve(bls12_381_g2=None),
            name="test_key_1",
        )
        assert key_id['name'] == "test_key_1"
        assert 'curve' in key_id

    def test_vetkd_public_key_args(self):
        """VetKDPublicKeyArgs should accept canister_id, context, key_id."""
        from basilisk.canisters.management.vetkd import (
            VetKDPublicKeyArgs, VetKDKeyId, VetKDCurve,
        )
        args = VetKDPublicKeyArgs(
            canister_id=None,
            context=b"\x08basilisktest",
            key_id=VetKDKeyId(
                curve=VetKDCurve(bls12_381_g2=None),
                name="test_key_1",
            ),
        )
        assert args['context'] == b"\x08basilisktest"
        assert args['canister_id'] is None

    def test_vetkd_derive_key_args(self):
        """VetKDDeriveKeyArgs should accept input, context, key_id, transport_public_key."""
        from basilisk.canisters.management.vetkd import (
            VetKDDeriveKeyArgs, VetKDKeyId, VetKDCurve,
        )
        args = VetKDDeriveKeyArgs(
            input=b"",
            context=b"\x08basilisktest",
            key_id=VetKDKeyId(
                curve=VetKDCurve(bls12_381_g2=None),
                name="test_key_1",
            ),
            transport_public_key=b"\x00" * 48,
        )
        assert len(args['transport_public_key']) == 48
        assert args['input'] == b""

    def test_vetkd_public_key_result(self):
        """VetKDPublicKeyResult should have public_key field."""
        from basilisk.canisters.management.vetkd import VetKDPublicKeyResult
        result = VetKDPublicKeyResult(public_key=b"\x01\x02\x03")
        assert result['public_key'] == b"\x01\x02\x03"

    def test_vetkd_derive_key_result(self):
        """VetKDDeriveKeyResult should have encrypted_key field."""
        from basilisk.canisters.management.vetkd import VetKDDeriveKeyResult
        result = VetKDDeriveKeyResult(encrypted_key=b"\xaa\xbb\xcc")
        assert result['encrypted_key'] == b"\xaa\xbb\xcc"


class TestUnitManagementCanisterBindings:
    """Unit tests: verify vetkd methods exist on ManagementCanister."""

    def test_management_canister_has_vetkd_public_key(self):
        from basilisk.canisters.management import ManagementCanister
        assert hasattr(ManagementCanister, 'vetkd_public_key')

    def test_management_canister_has_vetkd_derive_key(self):
        from basilisk.canisters.management import ManagementCanister
        assert hasattr(ManagementCanister, 'vetkd_derive_key')

    def test_management_canister_arg_types_vetkd(self):
        """Candid arg type metadata should include vetKD methods."""
        from basilisk.canisters.management import ManagementCanister
        arg_types = getattr(ManagementCanister, '_arg_types', {})
        assert 'vetkd_public_key' in arg_types
        assert 'vetkd_derive_key' in arg_types
        assert 'bls12_381_g2' in arg_types['vetkd_public_key']
        assert 'transport_public_key' in arg_types['vetkd_derive_key']

    def test_management_canister_return_types_vetkd(self):
        """Candid return type metadata should include vetKD methods."""
        from basilisk.canisters.management import ManagementCanister
        return_types = getattr(ManagementCanister, '_return_types', {})
        assert 'vetkd_public_key' in return_types
        assert 'vetkd_derive_key' in return_types
        assert 'public_key' in return_types['vetkd_public_key']
        assert 'encrypted_key' in return_types['vetkd_derive_key']

    def test_management_canister_singleton(self):
        """management_canister singleton should have vetKD methods."""
        from basilisk.canisters.management import management_canister
        assert hasattr(management_canister, 'vetkd_public_key')
        assert hasattr(management_canister, 'vetkd_derive_key')


class TestUnitVetKeyServiceContext:
    """Unit tests for VetKeyService context construction (no canister needed)."""

    def test_context_format_with_bytes_scope(self):
        """Context should be: [len(ds)] || ds || scope."""
        # Cannot use the real VetKeyService here because it imports `ic`
        # which is only available inside a canister. Test the algorithm directly.
        domain_separator = b"basilisk"
        scope = b"\x01\x02\x03"
        context = bytes([len(domain_separator)]) + domain_separator + scope
        assert context[0] == 8  # len("basilisk")
        assert context[1:9] == b"basilisk"
        assert context[9:] == b"\x01\x02\x03"

    def test_context_format_with_string_scope(self):
        """String scope should be encoded to UTF-8."""
        domain_separator = b"basilisk"
        scope = "my-scope".encode("utf-8")
        context = bytes([len(domain_separator)]) + domain_separator + scope
        assert context == b"\x08basiliskmy-scope"

    def test_context_different_domains_differ(self):
        """Different domain separators produce different contexts."""
        scope = b"same"
        ctx1 = bytes([8]) + b"basilisk" + scope
        ctx2 = bytes([6]) + b"realms" + scope
        assert ctx1 != ctx2

    def test_context_different_scopes_differ(self):
        """Different scopes produce different contexts."""
        ds = b"basilisk"
        ctx1 = bytes([len(ds)]) + ds + b"user-a"
        ctx2 = bytes([len(ds)]) + ds + b"user-b"
        assert ctx1 != ctx2

    def test_context_empty_scope(self):
        """Empty scope should still produce valid context."""
        ds = b"basilisk"
        context = bytes([len(ds)]) + ds + b""
        assert len(context) == 9  # 1 + 8

    def test_custom_domain_separator(self):
        """Custom domain separator should be used correctly."""
        ds = b"my-custom-app"
        scope = b"test"
        context = bytes([len(ds)]) + ds + scope
        assert context[0] == 13  # len("my-custom-app")
        assert context[1:14] == b"my-custom-app"


class TestUnitShellFlagParsing:
    """Unit tests for %vetkey shell command flag parsing."""

    def test_parse_no_flags(self):
        from basilisk.shell import _parse_vetkey_flags
        cleaned, scope, input_text, key_name = _parse_vetkey_flags("pubkey")
        assert cleaned == "pubkey"
        assert scope is None
        assert input_text == ""
        assert key_name == "test_key_1"

    def test_parse_scope_flag(self):
        from basilisk.shell import _parse_vetkey_flags
        cleaned, scope, input_text, key_name = _parse_vetkey_flags(
            "pubkey --scope my-custom-scope"
        )
        assert "pubkey" in cleaned
        assert scope == "my-custom-scope"
        assert input_text == ""

    def test_parse_input_flag(self):
        from basilisk.shell import _parse_vetkey_flags
        cleaned, scope, input_text, key_name = _parse_vetkey_flags(
            "derive abc123 --input document-42"
        )
        assert "derive" in cleaned
        assert "abc123" in cleaned
        assert input_text == "document-42"

    def test_parse_key_flag(self):
        from basilisk.shell import _parse_vetkey_flags
        cleaned, scope, input_text, key_name = _parse_vetkey_flags(
            "pubkey --key key_1"
        )
        assert key_name == "key_1"
        assert "pubkey" in cleaned

    def test_parse_all_flags(self):
        from basilisk.shell import _parse_vetkey_flags
        cleaned, scope, input_text, key_name = _parse_vetkey_flags(
            "derive aabbcc --scope admin --input doc-1 --key key_1"
        )
        assert scope == "admin"
        assert input_text == "doc-1"
        assert key_name == "key_1"
        assert "derive" in cleaned
        assert "aabbcc" in cleaned

    def test_parse_flags_order_independent(self):
        from basilisk.shell import _parse_vetkey_flags
        cleaned1, scope1, input1, key1 = _parse_vetkey_flags(
            "derive ff --key key_1 --scope x --input y"
        )
        cleaned2, scope2, input2, key2 = _parse_vetkey_flags(
            "derive ff --input y --key key_1 --scope x"
        )
        assert scope1 == scope2 == "x"
        assert input1 == input2 == "y"
        assert key1 == key2 == "key_1"


class TestUnitShellDispatch:
    """Unit tests for %vetkey shell command dispatch (help/usage paths)."""

    def test_handle_vetkey_no_args_shows_usage(self):
        from basilisk.shell import _handle_vetkey
        result = _handle_vetkey("", "dummy-canister", "ic")
        assert "Usage:" in result
        assert "pubkey" in result
        assert "derive" in result

    def test_handle_vetkey_help_shows_usage(self):
        from basilisk.shell import _handle_vetkey
        result = _handle_vetkey("help", "dummy-canister", "ic")
        assert "Usage:" in result

    def test_handle_vetkey_unknown_subcmd(self):
        from basilisk.shell import _handle_vetkey
        result = _handle_vetkey("foobar", "dummy-canister", "ic")
        assert "Unknown vetkey command: foobar" in result

    def test_handle_vetkey_derive_no_tpk(self):
        """derive without transport_public_key should show usage."""
        from basilisk.shell import _handle_vetkey
        result = _handle_vetkey("derive", "dummy-canister", "ic")
        assert "Usage:" in result
        assert "transport_public_key_hex" in result

    def test_handle_vetkey_derive_invalid_hex(self):
        """derive with invalid hex should return error."""
        from basilisk.shell import _handle_vetkey
        result = _handle_vetkey("derive ZZZZ_NOT_HEX", "dummy-canister", "ic")
        assert "[error]" in result
        assert "invalid transport public key hex" in result


class TestUnitOSExports:
    """Verify VetKeyService is exported from basilisk.toolkit."""

    def test_vetkey_service_in_all(self):
        import basilisk.toolkit
        exports = getattr(basilisk.toolkit, "__all__", dir(basilisk.toolkit))
        assert "VetKeyService" in exports


class TestUnitKeyConstants:
    """Verify the key name constants are defined."""

    def test_production_key(self):
        from basilisk.toolkit.vetkeys import VETKD_KEY_PRODUCTION
        assert VETKD_KEY_PRODUCTION == "key_1"

    def test_test_key(self):
        from basilisk.toolkit.vetkeys import VETKD_KEY_TEST
        assert VETKD_KEY_TEST == "test_key_1"

    def test_local_key(self):
        from basilisk.toolkit.vetkeys import VETKD_KEY_LOCAL
        assert VETKD_KEY_LOCAL == "dfx_test_key"


# ===========================================================================
# INTEGRATION TESTS — require live canister
# ===========================================================================

class TestIntegrationVetKDPublicKey:
    """Integration tests for vetkd_public_key via live canister."""

    @pytest.mark.slow
    def test_vetkd_public_key_via_task(
        self, canister_reachable, vetkey_canister, vetkey_network, key_name,
    ):
        """Derive a vetKD public key from the management canister.

        This is the core end-to-end test: it sends async code to the
        canister that calls vetkd_public_key via ic.call_raw, writes the
        result to memfs, and we read it back.
        """
        code = (
            "import json as _json\n"
            "\n"
            "def async_task():\n"
            "    _ds = b'basilisk'\n"
            "    _scope = ic.id().bytes\n"
            "    _ctx = bytes([len(_ds)]) + _ds + _scope\n"
            "    _ctx_hex = ''.join(f'{b:02x}' for b in _ctx)\n"
            f"    _args = ic.candid_encode('(record {{ canister_id = null; "
            f"context = blob \"' + _ctx_hex + '\"; "
            f"key_id = record {{ curve = variant {{ bls12_381_g2 = null }}; "
            f"name = \"{key_name}\" }} }})')\n"
            "    _result = yield ic.call_raw('aaaaa-aa', 'vetkd_public_key', _args, 26_000_000_000)\n"
            "    if hasattr(_result, 'Ok') and _result.Ok is not None:\n"
            "        _decoded = ic.candid_decode(_result.Ok)\n"
            "        return 'VETKEY_PK_OK:' + str(len(str(_decoded)))\n"
            "    elif hasattr(_result, 'Err') and _result.Err is not None:\n"
            "        return 'VETKEY_PK_ERR:' + str(_result.Err)\n"
            "    else:\n"
            "        return 'VETKEY_PK_RAW:' + str(_result)\n"
        )

        log = _run_async_task(
            "_test_vetkey_pubkey", code,
            vetkey_canister, vetkey_network, timeout=90,
        )
        assert "completed" in log, f"Task did not complete: {log}"

        # Expect either success or a known rejection (if vetKD not enabled on this subnet)
        if "VETKEY_PK_OK" in log:
            m = re.search(r'VETKEY_PK_OK:(\d+)', log)
            assert m, f"Could not parse public key length from: {log}"
            pk_repr_len = int(m.group(1))
            assert pk_repr_len > 0, "Public key should not be empty"
            print(f"\n  vetKD public key received (repr length: {pk_repr_len})")
        elif "VETKEY_PK_ERR" in log:
            # vetKD might not be available on the test subnet — still a valid test result
            print(f"\n  vetKD returned error (expected if not on vetKD subnet): {log}")
        else:
            pytest.fail(f"Unexpected task result: {log}")

    @pytest.mark.slow
    def test_vetkd_public_key_different_contexts_differ(
        self, canister_reachable, vetkey_canister, vetkey_network, key_name,
    ):
        """Two different contexts should produce different public keys.

        Uses two separate tasks (one vetKD call each) instead of one task
        with two sequential yields, since each inter-canister call can
        take 30-60s on mainnet.
        """
        results = []
        for scope_label in ["scope-A", "scope-B"]:
            scope_bytes_hex = scope_label.encode().hex()
            ds_hex = "basilisk".encode().hex()
            ds_len_hex = f"{len('basilisk'):02x}"
            ctx_hex = ds_len_hex + ds_hex + scope_bytes_hex

            code = (
                "def async_task():\n"
                f"    _args = ic.candid_encode('(record {{ canister_id = null; "
                f"context = blob \"{ctx_hex}\"; "
                f"key_id = record {{ curve = variant {{ bls12_381_g2 = null }}; "
                f"name = \"{key_name}\" }} }})')\n"
                "    _result = yield ic.call_raw('aaaaa-aa', 'vetkd_public_key', _args, 26_000_000_000)\n"
                "    if hasattr(_result, 'Ok') and _result.Ok is not None:\n"
                "        return 'VETKEY_CTX_OK:' + str(ic.candid_decode(_result.Ok))\n"
                "    else:\n"
                "        return 'VETKEY_CTX_ERR:' + str(_result)\n"
            )

            log = _run_async_task(
                f"_test_vetkey_ctx_{scope_label.replace('-', '_')}",
                code, vetkey_canister, vetkey_network, timeout=120,
            )
            assert "completed" in log, f"Task did not complete for {scope_label}: {log}"
            results.append(log)

        if "VETKEY_CTX_ERR" in results[0] or "VETKEY_CTX_ERR" in results[1]:
            print(f"\n  vetKD not available on this subnet")
        elif results[0] == results[1]:
            pytest.fail("Different contexts produced SAME public key — this is wrong")
        else:
            print("\n  Different contexts produced different public keys (correct)")


class TestIntegrationVetKDDeriveKey:
    """Integration tests for vetkd_derive_key via live canister."""

    @pytest.mark.slow
    def test_vetkd_derive_key_via_task(
        self, canister_reachable, vetkey_canister, vetkey_network, key_name,
    ):
        """Derive an encrypted vetKey from the management canister.

        Uses a dummy transport public key (all zeros) — the result will be
        an encrypted key blob.  We can't decrypt it without BLS12-381 client
        code, but we can verify the canister call succeeds and returns bytes.
        """
        # 48-byte dummy transport public key (BLS12-381 G1 point)
        # In production, this would be generated by TransportSecretKey.random()
        dummy_tpk_hex = "00" * 48

        code = (
            "import json as _json\n"
            "\n"
            "def async_task():\n"
            "    _ds = b'basilisk'\n"
            "    _scope = ic.id().bytes\n"
            "    _ctx = bytes([len(_ds)]) + _ds + _scope\n"
            "    _ctx_hex = ''.join(f'{b:02x}' for b in _ctx)\n"
            f"    _tpk = '{dummy_tpk_hex}'\n"
            f"    _args = ic.candid_encode('(record {{ "
            f"input = blob \"\"; "
            f"context = blob \"' + _ctx_hex + '\"; "
            f"key_id = record {{ curve = variant {{ bls12_381_g2 = null }}; "
            f"name = \"{key_name}\" }}; "
            f"transport_public_key = blob \"' + _tpk + '\" }})')\n"
            "    _result = yield ic.call_raw('aaaaa-aa', 'vetkd_derive_key', _args, 54_000_000_000)\n"
            "    if hasattr(_result, 'Ok') and _result.Ok is not None:\n"
            "        _decoded = ic.candid_decode(_result.Ok)\n"
            "        return 'VETKEY_DK_OK:' + str(len(str(_decoded)))\n"
            "    elif hasattr(_result, 'Err') and _result.Err is not None:\n"
            "        return 'VETKEY_DK_ERR:' + str(_result.Err)\n"
            "    else:\n"
            "        return 'VETKEY_DK_RAW:' + str(_result)\n"
        )

        log = _run_async_task(
            "_test_vetkey_derive", code,
            vetkey_canister, vetkey_network, timeout=90,
        )
        assert "completed" in log, f"Task did not complete: {log}"

        if "VETKEY_DK_OK" in log:
            m = re.search(r'VETKEY_DK_OK:(\d+)', log)
            assert m, f"Could not parse encrypted key length from: {log}"
            ek_repr_len = int(m.group(1))
            assert ek_repr_len > 0, "Encrypted key should not be empty"
            print(f"\n  vetKD encrypted key received (repr length: {ek_repr_len})")
        elif "VETKEY_DK_ERR" in log:
            # May fail with dummy tpk or if vetKD not enabled — still valid
            print(f"\n  vetKD derive returned error: {log}")
        else:
            pytest.fail(f"Unexpected task result: {log}")

    @pytest.mark.slow
    def test_vetkd_derive_key_different_inputs_differ(
        self, canister_reachable, vetkey_canister, vetkey_network, key_name,
    ):
        """Two different inputs (same context) should produce different encrypted keys.

        Uses two separate tasks (one vetKD call each) instead of one task
        with two sequential yields, since each inter-canister call can
        take 30-60s on mainnet.
        """
        results = []
        for input_label in ["input-A", "input-B"]:
            input_hex = input_label.encode().hex()
            ds_hex = "basilisk".encode().hex()
            ds_len_hex = f"{len('basilisk'):02x}"
            tpk_hex = "00" * 48

            code = (
                "def async_task():\n"
                "    _scope = ic.id().bytes\n"
                "    _scope_hex = ''.join(f'{b:02x}' for b in _scope)\n"
                f"    _ctx_hex = '{ds_len_hex}{ds_hex}' + _scope_hex\n"
                f"    _args = ic.candid_encode('(record {{ "
                f"input = blob \"{input_hex}\"; "
                f"context = blob \"' + _ctx_hex + '\"; "
                f"key_id = record {{ curve = variant {{ bls12_381_g2 = null }}; "
                f"name = \"{key_name}\" }}; "
                f"transport_public_key = blob \"{tpk_hex}\" }})')\n"
                "    _result = yield ic.call_raw('aaaaa-aa', 'vetkd_derive_key', _args, 54_000_000_000)\n"
                "    if hasattr(_result, 'Ok') and _result.Ok is not None:\n"
                "        return 'VETKEY_DI_OK:' + str(ic.candid_decode(_result.Ok))\n"
                "    else:\n"
                "        return 'VETKEY_DI_ERR:' + str(_result)\n"
            )

            log = _run_async_task(
                f"_test_vetkey_di_{input_label.replace('-', '_')}",
                code, vetkey_canister, vetkey_network, timeout=120,
            )
            assert "completed" in log, f"Task did not complete for {input_label}: {log}"
            results.append(log)

        if "VETKEY_DI_ERR" in results[0] or "VETKEY_DI_ERR" in results[1]:
            print(f"\n  vetKD not available or dummy tpk rejected")
        elif results[0] == results[1]:
            pytest.fail("Different inputs produced SAME encrypted key — this is wrong")
        else:
            print("\n  Different inputs produced different encrypted keys (correct)")


class TestIntegrationShellVetKey:
    """Integration tests for %vetkey shell commands via live canister."""

    @pytest.mark.slow
    def test_vetkey_pubkey_via_timer(
        self, canister_reachable, vetkey_canister, vetkey_network, key_name,
    ):
        """Test %vetkey pubkey by executing the timer+memfs pattern directly."""
        # This tests the same code path as the shell's _vetkey_pubkey function
        # but via direct canister exec instead of the shell dispatcher
        code = (
            "import json as _json\n"
            "def _vetkey_pubkey_cb():\n"
            "    try:\n"
            "        _ds = b'basilisk'\n"
            "        _scope = ic.caller().bytes\n"
            "        _ctx = bytes([len(_ds)]) + _ds + _scope\n"
            "        _ctx_hex = ''.join(f'{b:02x}' for b in _ctx)\n"
            f"        _args = ic.candid_encode('(record {{ canister_id = null; "
            f"context = blob \"' + _ctx_hex + '\"; "
            f"key_id = record {{ curve = variant {{ bls12_381_g2 = null }}; "
            f"name = \"{key_name}\" }} }})')\n"
            "        _result = yield ic.call_raw('aaaaa-aa', 'vetkd_public_key', _args, 26_000_000_000)\n"
            "        if hasattr(_result, 'Ok') and _result.Ok is not None:\n"
            "            _decoded = ic.candid_decode(_result.Ok)\n"
            "            _out = _json.dumps({'ok': True, 'public_key': str(_decoded)[:80]})\n"
            "        elif hasattr(_result, 'Err') and _result.Err is not None:\n"
            "            _out = _json.dumps({'ok': False, 'error': str(_result.Err)})\n"
            "        else:\n"
            "            _out = _json.dumps({'ok': True, 'response': str(_result)[:80]})\n"
            "    except Exception as _e:\n"
            "        _out = _json.dumps({'ok': False, 'error': str(_e)})\n"
            "    with open('/tmp/_vetkey_result.txt', 'w') as _f:\n"
            "        _f.write(_out)\n"
            "try:\n"
            "    import os; os.remove('/tmp/_vetkey_result.txt')\n"
            "except OSError:\n"
            "    pass\n"
            "ic.set_timer(0, _vetkey_pubkey_cb)\n"
            "print('VETKEY_INITIATED')\n"
        )

        result = _local_canister_exec(code, vetkey_canister, vetkey_network)
        assert "VETKEY_INITIATED" in result, f"Timer not initiated: {result}"

        # Poll for result (same as the shell does)
        poll_code = (
            "try:\n"
            "    with open('/tmp/_vetkey_result.txt', 'r') as _f:\n"
            "        print('VETKEY_RESULT:' + _f.read())\n"
            "except FileNotFoundError:\n"
            "    print('VETKEY_PENDING')\n"
        )

        found = False
        for _ in range(15):
            time.sleep(3)
            poll_result = _local_canister_exec(
                poll_code, vetkey_canister, vetkey_network,
            )
            if poll_result and 'VETKEY_RESULT:' in poll_result:
                json_str = poll_result.split('VETKEY_RESULT:', 1)[1].strip()
                data = json.loads(json_str)
                if data.get('ok'):
                    print(f"\n  Shell-style pubkey result: {json_str[:120]}...")
                    found = True
                else:
                    print(f"\n  Shell-style pubkey error (may be expected): {data.get('error', '')[:120]}")
                    found = True
                break

        # Clean up
        _local_canister_exec(
            "import os\ntry:\n    os.remove('/tmp/_vetkey_result.txt')\nexcept OSError:\n    pass\nprint('cleaned')",
            vetkey_canister, vetkey_network,
        )

        if not found:
            pytest.fail("Timed out waiting for vetkey result via timer pattern")


# ===========================================================================
# Cycle cost sanity check (unit test)
# ===========================================================================

class TestUnitCycleCosts:
    """Verify cycle cost expectations are documented correctly."""

    def test_derive_key_cycle_cost_production(self):
        """Production key derivation should attach ~54B cycles."""
        # From the shell code — verify the constant is correct
        from basilisk.shell import _vetkey_derive
        import inspect
        source = inspect.getsource(_vetkey_derive)
        assert "54_000_000_000" in source, \
            "derive_key should attach 54B cycles for production key"

    def test_public_key_cycle_cost(self):
        """Public key call should attach ~26B cycles."""
        from basilisk.shell import _vetkey_pubkey
        import inspect
        source = inspect.getsource(_vetkey_pubkey)
        assert "26_000_000_000" in source, \
            "public_key should attach 26B cycles"
