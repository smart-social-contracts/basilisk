"""Integration tests for tests/fixtures/motoko_tests/fixtures/superheroes — superhero CRUD canister."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "motoko_tests/fixtures/superheroes"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_create_superhero(canister):
    result = parse_candid_text(call_canister(
        canister, "create",
        '(record { name = "Superman"; superpowers = null })',
        example_dir=EXAMPLE_DIR, update=True,
    ))
    assert result == 0


def test_read_superhero(canister):
    raw = call_canister(canister, "read", "(0 : nat32)", example_dir=EXAMPLE_DIR)
    assert "Superman" in raw


def test_update_superhero(canister):
    result = parse_candid_text(call_canister(
        canister, "update_",
        '(0 : nat32, record { name = "Batman"; superpowers = null })',
        example_dir=EXAMPLE_DIR, update=True,
    ))
    assert result is True


def test_read_updated_superhero(canister):
    raw = call_canister(canister, "read", "(0 : nat32)", example_dir=EXAMPLE_DIR)
    assert "Batman" in raw


def test_delete_hero(canister):
    result = parse_candid_text(call_canister(canister, "delete_hero", "(0 : nat32)", example_dir=EXAMPLE_DIR, update=True))
    assert result is True


def test_read_deleted_superhero(canister):
    raw = call_canister(canister, "read", "(0 : nat32)", example_dir=EXAMPLE_DIR)
    assert "null" in raw or "opt null" in raw or "vec {}" in raw
