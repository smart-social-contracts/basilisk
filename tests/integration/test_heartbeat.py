"""Integration tests for examples/heartbeat — heartbeat callback (async and sync)."""

import time
import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "heartbeat"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canisters(replica):
    ids = deploy_example(EXAMPLE)
    return ids


def test_heartbeat_async_initialized(canisters):
    # Wait for heartbeats to fire
    time.sleep(10)
    async_canister = canisters.get("heartbeat_async") or list(canisters.values())[0]
    result = parse_candid_text(call_canister(async_canister, "get_initialized", example_dir=EXAMPLE_DIR))
    assert result is True


def test_heartbeat_sync_initialized(canisters):
    sync_canister = canisters.get("heartbeat_sync") or list(canisters.values())[-1]
    result = parse_candid_text(call_canister(sync_canister, "get_initialized", example_dir=EXAMPLE_DIR))
    assert result is True
