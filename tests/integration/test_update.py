"""Integration tests for tests/fixtures/update — simple update canister."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "update"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    name = list(ids.keys())[0]
    return ids[name]


def test_get_current_message_initial(canister):
    result = parse_candid_text(call_canister(canister, "get_current_message", example_dir=EXAMPLE_DIR))
    assert result == ""


def test_simple_update(canister):
    call_canister(canister, "simple_update", '("hello")', example_dir=EXAMPLE_DIR)
    result = parse_candid_text(call_canister(canister, "get_current_message", example_dir=EXAMPLE_DIR))
    assert result == "hello"


def test_simple_update_overwrite(canister):
    call_canister(canister, "simple_update", '("world")', example_dir=EXAMPLE_DIR)
    result = parse_candid_text(call_canister(canister, "get_current_message", example_dir=EXAMPLE_DIR))
    assert result == "world"
