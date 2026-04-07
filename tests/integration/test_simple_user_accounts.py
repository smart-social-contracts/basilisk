"""Integration tests for tests/fixtures/simple_user_accounts — user CRUD operations."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "simple_user_accounts"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_get_all_users_initially_empty(canister):
    raw = call_canister(canister, "get_all_users", example_dir=EXAMPLE_DIR)
    assert "vec {" in raw or "vec{" in raw or raw.strip() == "(vec {})"


def test_create_user(canister):
    raw = call_canister(canister, "create_user", '("alice")', example_dir=EXAMPLE_DIR)
    assert "alice" in raw


def test_get_user_by_id(canister):
    raw = call_canister(canister, "get_user_by_id", '("0")', example_dir=EXAMPLE_DIR)
    assert "alice" in raw


def test_create_second_user(canister):
    raw = call_canister(canister, "create_user", '("bob")', example_dir=EXAMPLE_DIR)
    assert "bob" in raw


def test_get_all_users_returns_both(canister):
    raw = call_canister(canister, "get_all_users", example_dir=EXAMPLE_DIR)
    assert "alice" in raw and "bob" in raw


def test_get_nonexistent_user(canister):
    raw = call_canister(canister, "get_user_by_id", '("999")', example_dir=EXAMPLE_DIR)
    # Should return empty opt or vec
    assert "null" in raw or "vec {}" in raw or "opt null" in raw or raw.strip() == "(vec {})"
