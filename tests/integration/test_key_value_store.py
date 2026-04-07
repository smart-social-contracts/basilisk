"""Integration tests for tests/fixtures/key_value_store — key-value CRUD operations."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "key_value_store"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_get_nonexistent_key(canister):
    raw = call_canister(canister, "get", '("nonexistent")', example_dir=EXAMPLE_DIR)
    assert "vec" in raw or "null" in raw or raw.strip() == "(opt null)" or "opt" in raw


def test_set_and_get_key(canister):
    call_canister(canister, "set", '("greeting", "hello")', example_dir=EXAMPLE_DIR)
    raw = call_canister(canister, "get", '("greeting")', example_dir=EXAMPLE_DIR)
    assert "hello" in raw


def test_overwrite_key(canister):
    call_canister(canister, "set", '("greeting", "world")', example_dir=EXAMPLE_DIR)
    raw = call_canister(canister, "get", '("greeting")', example_dir=EXAMPLE_DIR)
    assert "world" in raw


def test_set_multiple_keys(canister):
    call_canister(canister, "set", '("name", "basilisk")', example_dir=EXAMPLE_DIR)
    call_canister(canister, "set", '("version", "1")', example_dir=EXAMPLE_DIR)
    name = call_canister(canister, "get", '("name")', example_dir=EXAMPLE_DIR)
    version = call_canister(canister, "get", '("version")', example_dir=EXAMPLE_DIR)
    assert "basilisk" in name
    assert "1" in version
