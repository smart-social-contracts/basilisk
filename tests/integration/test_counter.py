"""Integration tests for examples/counter — basic counter canister."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "counter"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    name = list(ids.keys())[0]
    return ids[name]


def test_read_count_initial(canister):
    result = parse_candid_text(call_canister(canister, "read_count", example_dir=EXAMPLE_DIR))
    assert result == 0


def test_first_increment(canister):
    result = parse_candid_text(call_canister(canister, "increment_count", example_dir=EXAMPLE_DIR))
    assert result == 1


def test_read_count_after_first_increment(canister):
    result = parse_candid_text(call_canister(canister, "read_count", example_dir=EXAMPLE_DIR))
    assert result == 1


def test_second_increment(canister):
    result = parse_candid_text(call_canister(canister, "increment_count", example_dir=EXAMPLE_DIR))
    assert result == 2


def test_read_count_after_second_increment(canister):
    result = parse_candid_text(call_canister(canister, "read_count", example_dir=EXAMPLE_DIR))
    assert result == 2
