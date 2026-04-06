"""Integration tests for examples/motoko_examples/echo — echo canister."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "motoko_examples/echo"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_say(canister):
    result = parse_candid_text(call_canister(canister, "say", '("Hello!")', example_dir=EXAMPLE_DIR))
    assert result == "Hello!"


def test_say_empty(canister):
    result = parse_candid_text(call_canister(canister, "say", '("")', example_dir=EXAMPLE_DIR))
    assert result == ""
