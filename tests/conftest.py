"""
Shared pytest fixtures for Basilisk OS integration tests.

These tests run against a LIVE canister — they are integration tests,
not unit tests. This is intentional: mocks won't catch real issues with
Candid encoding, memfs edge cases, or timer callbacks.

Configuration:
    Set environment variables or use defaults:
        BASILISK_TEST_CANISTER  — canister ID (default: ru4ga-siaaa-aaaai-q7f3a-cai)
        BASILISK_TEST_NETWORK   — network (default: ic)

Usage:
    pytest tests/ -v
    pytest tests/test_shell.py -v -k "test_simple_print"
"""

import os
import subprocess
import sys

import pytest

# ---------------------------------------------------------------------------
# Add basilisk package to path
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.shell import canister_exec, _parse_candid, _handle_magic, _TASK_RESOLVE


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CANISTER = "ru4ga-siaaa-aaaai-q7f3a-cai"  # Dedicated Basilisk OS test canister
DEFAULT_NETWORK = "ic"


def _get_canister():
    return os.environ.get("BASILISK_TEST_CANISTER", DEFAULT_CANISTER)


def _get_network():
    return os.environ.get("BASILISK_TEST_NETWORK", DEFAULT_NETWORK)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def canister():
    """Canister ID for all tests."""
    return _get_canister()


@pytest.fixture(scope="session")
def network():
    """Network for all tests."""
    return _get_network()


@pytest.fixture(scope="session")
def dfx_available():
    """Check that dfx is installed and accessible."""
    try:
        r = subprocess.run(["dfx", "--version"], capture_output=True, text=True)
        assert r.returncode == 0, "dfx not found"
        return True
    except FileNotFoundError:
        pytest.skip("dfx not installed")


@pytest.fixture(scope="session")
def canister_reachable(canister, network, dfx_available):
    """Verify the canister is reachable before running tests."""
    result = canister_exec("print('ping')", canister, network)
    if "error" in result.lower() or "Error" in result:
        pytest.skip(f"Canister {canister} not reachable on {network}: {result}")
    assert result.strip() == "ping", f"Unexpected ping response: {result!r}"
    # Warm up the task entity classes in this principal's namespace.
    canister_exec(
        _TASK_RESOLVE +
        # Fix stale Task_count counter if it diverged from actual instances.
        "if 'Task' in dir():\n"
        "    _actual = len(Task.instances())\n"
        "    _stored = Task.count()\n"
        "    if _actual != _stored:\n"
        "        Task.db().save('_system', Task.get_full_type_name() + '_count', str(_actual))\n"
        "print('task_entities_ready')\n",
        canister, network,
    )
    return True


def exec_on_canister(code, canister=None, network=None):
    """Helper: execute code on the canister and return stripped output."""
    c = canister or _get_canister()
    n = network or _get_network()
    return canister_exec(code, c, n).strip()


def magic_on_canister(cmd, canister=None, network=None):
    """Helper: execute a magic command and return stripped output."""
    c = canister or _get_canister()
    n = network or _get_network()
    result = _handle_magic(cmd, c, n)
    return result.strip() if result else ""
