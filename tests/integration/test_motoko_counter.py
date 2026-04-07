"""Integration tests for tests/fixtures/motoko_examples/counter — simple counter with get/inc/set."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "motoko_examples/counter"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_get_initial(canister):
    result = parse_candid_text(call_canister(canister, "get", example_dir=EXAMPLE_DIR))
    assert result == 0


def test_inc(canister):
    call_canister(canister, "inc", example_dir=EXAMPLE_DIR)
    result = parse_candid_text(call_canister(canister, "get", example_dir=EXAMPLE_DIR))
    assert result == 1


def test_set(canister):
    call_canister(canister, "set", "(42 : nat)", example_dir=EXAMPLE_DIR)
    result = parse_candid_text(call_canister(canister, "get", example_dir=EXAMPLE_DIR))
    assert result == 42


def test_inc_after_set(canister):
    call_canister(canister, "inc", example_dir=EXAMPLE_DIR)
    result = parse_candid_text(call_canister(canister, "get", example_dir=EXAMPLE_DIR))
    assert result == 43
