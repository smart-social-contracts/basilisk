"""Integration tests for examples/inspect_message — inspect message guard."""

import pytest
from .conftest import deploy_example, call_canister, call_canister_expect_trap, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "inspect_message"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_accessible(canister):
    result = parse_candid_text(call_canister(canister, "accessible", example_dir=EXAMPLE_DIR))
    assert result is True


def test_inaccessible_traps(canister):
    err = call_canister_expect_trap(canister, "inaccessible", example_dir=EXAMPLE_DIR)
    assert len(err) > 0
