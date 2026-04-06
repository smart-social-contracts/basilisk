"""Integration tests for examples/init_and_post_upgrade_recovery — init/upgrade error recovery."""

import subprocess
import os
import pytest
from .conftest import call_canister, parse_candid_text, _get_canister_id, EXAMPLES_DIR, _USE_PREBUILT

EXAMPLE = "init_and_post_upgrade_recovery"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)
CANISTER_NAME = "init_and_post_upgrade_recovery"


def _wasm_path():
    return os.path.join(EXAMPLE_DIR, ".basilisk", CANISTER_NAME, f"{CANISTER_NAME}.wasm")


@pytest.fixture(scope="module")
def canister(replica):
    if _USE_PREBUILT:
        # Create canister + install pre-built WASM with init argument
        subprocess.run(
            ["dfx", "canister", "create", CANISTER_NAME],
            cwd=EXAMPLE_DIR, capture_output=True, text=True, timeout=60,
        )
        result = subprocess.run(
            ["dfx", "canister", "install", CANISTER_NAME, "--wasm", _wasm_path(), "--argument", "(false)"],
            cwd=EXAMPLE_DIR, capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"install failed: {result.stderr}"
    else:
        subprocess.run(
            ["dfx", "deploy", CANISTER_NAME, "--argument", "(false)"],
            cwd=EXAMPLE_DIR, capture_output=True, text=True, timeout=1800,
        )
    cid = _get_canister_id(EXAMPLE_DIR, CANISTER_NAME)
    assert cid, f"Failed to deploy {CANISTER_NAME}"
    return cid


def test_init_succeeded(canister):
    result = parse_candid_text(call_canister(canister, "get_message", example_dir=EXAMPLE_DIR))
    assert result == "init_"


def test_post_upgrade_succeeds(canister):
    if _USE_PREBUILT:
        result = subprocess.run(
            ["dfx", "canister", "install", CANISTER_NAME, "--wasm", _wasm_path(),
             "--argument", "(false)", "--mode", "upgrade"],
            cwd=EXAMPLE_DIR, capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"upgrade failed: {result.stderr}"
    else:
        subprocess.run(
            ["dfx", "deploy", "--upgrade-unchanged", CANISTER_NAME, "--argument", "(false)"],
            cwd=EXAMPLE_DIR, capture_output=True, text=True, timeout=1800,
        )
    result = parse_candid_text(call_canister(canister, "get_message", example_dir=EXAMPLE_DIR))
    assert result == "post_upgrade_"
