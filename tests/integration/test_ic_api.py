"""Integration tests for tests/fixtures/ic_api — IC system API calls."""

import pytest
from .conftest import deploy_example, call_canister, call_canister_expect_trap, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "ic_api"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_caller(canister):
    raw = call_canister(canister, "caller", example_dir=EXAMPLE_DIR)
    assert "principal" in raw.lower() or len(raw) > 5


def test_id(canister):
    raw = call_canister(canister, "id", example_dir=EXAMPLE_DIR)
    assert "principal" in raw.lower() or len(raw) > 5


def test_time(canister):
    result = parse_candid_text(call_canister(canister, "time", example_dir=EXAMPLE_DIR))
    assert isinstance(result, int) and result > 0


def test_canister_balance(canister):
    result = parse_candid_text(call_canister(canister, "canister_balance", example_dir=EXAMPLE_DIR))
    assert isinstance(result, int) and result > 0


def test_canister_balance128(canister):
    result = parse_candid_text(call_canister(canister, "canister_balance128", example_dir=EXAMPLE_DIR))
    assert isinstance(result, int) and result > 0


def test_trap(canister):
    err = call_canister_expect_trap(canister, "trap", '("here is the message")', example_dir=EXAMPLE_DIR)
    assert "here is the message" in err
