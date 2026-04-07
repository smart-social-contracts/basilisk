"""Integration tests for tests/fixtures/call_raw — raw canister calls."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "call_raw"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_execute_call_raw(canister):
    raw = call_canister(
        canister, "execute_call_raw",
        f'(principal "{canister}", "execute_call_raw", "(principal \\"{canister}\\", \\"execute_call_raw\\", \\"()\\", 0 : nat64)", 0 : nat64)',
        example_dir=EXAMPLE_DIR,
    )
    assert "Ok" in raw


def test_execute_call_raw128(canister):
    raw = call_canister(
        canister, "execute_call_raw128",
        f'(principal "{canister}", "execute_call_raw128", "(principal \\"{canister}\\", \\"execute_call_raw128\\", \\"()\\", 0 : nat)", 0 : nat)',
        example_dir=EXAMPLE_DIR,
    )
    assert "Ok" in raw
