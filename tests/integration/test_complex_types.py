"""Integration tests for examples/complex_types — record/variant types."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "complex_types"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_create_user(canister):
    raw = call_canister(canister, "create_user", '("testuser")', example_dir=EXAMPLE_DIR)
    assert "Ok" in raw


def test_get_all_users(canister):
    raw = call_canister(canister, "get_all_users", example_dir=EXAMPLE_DIR)
    assert "vec" in raw or "record" in raw
