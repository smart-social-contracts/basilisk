"""Integration tests for tests/fixtures/motoko_examples/phone-book — phone book CRUD."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "motoko_examples/phone-book"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_lookup_empty(canister):
    raw = call_canister(canister, "lookup", '("Alice")', example_dir=EXAMPLE_DIR)
    assert "null" in raw or "vec {}" in raw or "opt null" in raw


def test_insert(canister):
    call_canister(canister, "insert", '("Alice", record { desc = "Friend"; phone = "555-1234" })', example_dir=EXAMPLE_DIR)


def test_lookup_after_insert(canister):
    raw = call_canister(canister, "lookup", '("Alice")', example_dir=EXAMPLE_DIR)
    assert "Friend" in raw and "555-1234" in raw
