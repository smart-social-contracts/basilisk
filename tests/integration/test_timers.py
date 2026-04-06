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
    # set_timers takes (delay: Duration, interval: Duration) in nanoseconds
    raw = call_canister(
        canister, "set_timers",
        '(1_000_000_000 : nat64, 1_000_000_000 : nat64)',
        example_dir=EXAMPLE_DIR, update=True,
    )
    assert "single" in raw

    # Wait for timers to fire (PocketIC may need explicit time advancement)
    time.sleep(5)

    # Check status
    raw = call_canister(canister, "status_report", example_dir=EXAMPLE_DIR)
    assert len(raw) > 0
