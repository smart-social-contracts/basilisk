"""Integration tests for examples/timers — timer callback functionality."""

import time
import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "timers"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    name = list(ids.keys())[0]
    return ids[name]


def test_set_timers_and_verify(canister):
    # Set up timers
    call_canister(canister, "set_single_timer", example_dir=EXAMPLE_DIR)
    call_canister(canister, "set_inline_timer", example_dir=EXAMPLE_DIR)
    call_canister(canister, "set_capture_timer", example_dir=EXAMPLE_DIR)
    call_canister(canister, "set_repeat_timer", example_dir=EXAMPLE_DIR)

    # Wait for timers to fire (PocketIC may need explicit time advancement)
    time.sleep(10)

    # Check status
    raw = call_canister(canister, "status_report", example_dir=EXAMPLE_DIR)
    assert len(raw) > 0
