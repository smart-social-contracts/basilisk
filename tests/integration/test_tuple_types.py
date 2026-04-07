"""Integration tests for tests/fixtures/tuple_types — tuple type handling."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "tuple_types"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_tuple_of_one(canister):
    raw = call_canister(canister, "primitive_one_tuple_return_type", example_dir=EXAMPLE_DIR)
    assert len(raw) > 0


def test_two_tuple(canister):
    raw = call_canister(canister, "primitive_two_tuple_return_type", example_dir=EXAMPLE_DIR)
    assert "record" in raw


def test_three_tuple(canister):
    raw = call_canister(canister, "primitive_three_tuple_return_type", example_dir=EXAMPLE_DIR)
    assert "record" in raw
