"""Integration tests for tests/fixtures/motoko_examples/persistent-storage — persistent counter."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "motoko_examples/persistent-storage"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_reset(canister):
    result = parse_candid_text(call_canister(canister, "reset", example_dir=EXAMPLE_DIR))
    assert result == 0


def test_get_initial(canister):
    result = parse_candid_text(call_canister(canister, "get", example_dir=EXAMPLE_DIR))
    assert result == 0


def test_increment(canister):
    result = parse_candid_text(call_canister(canister, "increment", example_dir=EXAMPLE_DIR))
    assert result == 1


def test_increment_again(canister):
    result = parse_candid_text(call_canister(canister, "increment", example_dir=EXAMPLE_DIR))
    assert result == 2


def test_get_after_increments(canister):
    result = parse_candid_text(call_canister(canister, "get", example_dir=EXAMPLE_DIR))
    assert result == 2
