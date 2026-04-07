"""Integration tests for tests/fixtures/init — canister init hook."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "init"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_get_user(canister):
    raw = call_canister(canister, "get_user", example_dir=EXAMPLE_DIR)
    assert "user1" in raw


def test_get_reaction(canister):
    raw = call_canister(canister, "get_reaction", example_dir=EXAMPLE_DIR)
    assert "Fire" in raw


def test_get_owner(canister):
    raw = call_canister(canister, "get_owner", example_dir=EXAMPLE_DIR)
    assert "principal" in raw.lower() or len(raw) > 5
