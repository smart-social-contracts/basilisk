"""Integration tests for tests/fixtures/generators — async generator (yield) patterns."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "generators"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    name = list(ids.keys())[0]
    return ids[name]


def test_get_randomness_directly(canister):
    raw = call_canister(canister, "get_randomness_directly", example_dir=EXAMPLE_DIR)
    # Result is a blob; dfx prints it as (blob "...") with 32 bytes
    assert "blob" in raw


def test_get_randomness_indirectly(canister):
    raw = call_canister(canister, "get_randomness_indirectly", example_dir=EXAMPLE_DIR)
    assert "blob" in raw


def test_get_randomness_super_indirectly(canister):
    raw = call_canister(canister, "get_randomness_super_indirectly", example_dir=EXAMPLE_DIR)
    assert "blob" in raw
