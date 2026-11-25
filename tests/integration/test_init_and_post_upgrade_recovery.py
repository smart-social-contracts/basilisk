"""Integration tests for tests/fixtures/init_and_post_upgrade_recovery — init/upgrade error recovery."""

import subprocess
import os
import pytest
from .conftest import call_canister, parse_candid_text, _get_canister_id, EXAMPLES_DIR, _USE_PREBUILT, _CANDID_MAP, _ensure_network

EXAMPLE = "init_and_post_upgrade_recovery"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)
CANISTER_NAME = "init_and_post_upgrade_recovery"


def _wasm_path():
    return os.path.join(EXAMPLE_DIR, ".basilisk", CANISTER_NAME, f"{CANISTER_NAME}.wasm")


@pytest.fixture(scope="module")
def canister(replica):
    _ensure_network(EXAMPLE_DIR)
    if _USE_PREBUILT:
        subprocess.run(
            ["icp", "canister", "create", CANISTER_NAME],
            cwd=EXAMPLE_DIR, capture_output=True, text=True, timeout=60,
        )
        result = subprocess.run(
            ["icp", "canister", "install", CANISTER_NAME, "--wasm", _wasm_path(), "--args", "(false)", "-y"],
            cwd=EXAMPLE_DIR, capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"install failed: {result.stderr}"
    else:
        subprocess.run(
            ["icp", "deploy", CANISTER_NAME, "--args", "(false)"],
            cwd=EXAMPLE_DIR, capture_output=True, text=True, timeout=1800,
        )
    cid = _get_canister_id(EXAMPLE_DIR, CANISTER_NAME)
    assert cid, f"Failed to deploy {CANISTER_NAME}"
    _CANDID_MAP[cid] = {"name": CANISTER_NAME, "example_dir": EXAMPLE_DIR}
    return cid


def test_init_succeeded(canister):
    result = parse_candid_text(call_canister(canister, "get_message", example_dir=EXAMPLE_DIR))
    assert result == "init_"


def _upgrade(args):
    """Upgrade the canister to its built wasm, passing post_upgrade_ the Candid args."""
    return subprocess.run(
        ["icp", "canister", "install", CANISTER_NAME, "--wasm", _wasm_path(),
         "--args", args, "--mode", "upgrade", "-y"],
        cwd=EXAMPLE_DIR, capture_output=True, text=True, timeout=120,
    )


def test_post_upgrade_succeeds(canister):
    """post_upgrade_ takes an argument, and the upgrade passes it through the build's wrapper (#66)."""
    result = _upgrade("(false)")
    assert result.returncode == 0, f"upgrade failed: {result.stderr}"
    # Only post_upgrade_ sets this: after install it reads "init_", so an
    # install that skipped the unchanged wasm would fail here.
    result = parse_candid_text(call_canister(canister, "get_message", example_dir=EXAMPLE_DIR))
    assert result == "post_upgrade_"


def test_post_upgrade_trap_rolls_back(canister):
    """(true) reaches post_upgrade_, which traps, and the IC keeps the canister as it was."""
    result = _upgrade("(true)")
    assert result.returncode != 0
    assert "post_upgrade_ trapped" in result.stderr + result.stdout
    result = parse_candid_text(call_canister(canister, "get_message", example_dir=EXAMPLE_DIR))
    assert result == "post_upgrade_"
