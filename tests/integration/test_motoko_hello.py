"""Integration tests for tests/fixtures/motoko_examples/hello — greeting canister."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "motoko_examples/hello"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_greet(canister):
    result = parse_candid_text(call_canister(canister, "greet", '("World")', example_dir=EXAMPLE_DIR))
    assert result == "Hello, World!"


def test_greet_empty(canister):
    result = parse_candid_text(call_canister(canister, "greet", '("")', example_dir=EXAMPLE_DIR))
    assert result == "Hello, !"
