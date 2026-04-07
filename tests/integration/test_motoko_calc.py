"""Integration tests for tests/fixtures/motoko_examples/calc — calculator canister."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "motoko_examples/calc"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_add(canister):
    call_canister(canister, "clearall", example_dir=EXAMPLE_DIR)
    result = parse_candid_text(call_canister(canister, "add", "(5 : int)", example_dir=EXAMPLE_DIR))
    assert result == 5


def test_sub(canister):
    result = parse_candid_text(call_canister(canister, "sub", "(2 : int)", example_dir=EXAMPLE_DIR))
    assert result == 3


def test_mul(canister):
    result = parse_candid_text(call_canister(canister, "mul", "(4 : int)", example_dir=EXAMPLE_DIR))
    assert result == 12


def test_div(canister):
    raw = call_canister(canister, "div", "(3 : int)", example_dir=EXAMPLE_DIR)
    assert "4" in raw


def test_div_by_zero(canister):
    raw = call_canister(canister, "div", "(0 : int)", example_dir=EXAMPLE_DIR)
    assert "null" in raw or "vec {}" in raw or "opt null" in raw


def test_clearall(canister):
    call_canister(canister, "clearall", example_dir=EXAMPLE_DIR)
    result = parse_candid_text(call_canister(canister, "add", "(0 : int)", example_dir=EXAMPLE_DIR))
    assert result == 0
