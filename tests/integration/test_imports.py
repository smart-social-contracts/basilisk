"""Integration tests for examples/imports — multi-module imports and stdlib usage."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "imports"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_get_one(canister):
    result = parse_candid_text(call_canister(canister, "get_one", example_dir=EXAMPLE_DIR))
    assert isinstance(result, str) and len(result) > 0


def test_get_two(canister):
    result = parse_candid_text(call_canister(canister, "get_two", example_dir=EXAMPLE_DIR))
    assert isinstance(result, str) and len(result) > 0


def test_get_three(canister):
    result = parse_candid_text(call_canister(canister, "get_three", example_dir=EXAMPLE_DIR))
    assert isinstance(result, str) and len(result) > 0


def test_sha224_hash(canister):
    result = parse_candid_text(call_canister(canister, "sha224_hash", '("hello")', example_dir=EXAMPLE_DIR))
    assert isinstance(result, str) and len(result) == 56


def test_get_math_message(canister):
    result = parse_candid_text(call_canister(canister, "get_math_message", example_dir=EXAMPLE_DIR))
    assert result == 11


def test_boltons_floor(canister):
    result = parse_candid_text(call_canister(canister, "boltons_floor", "(456.76 : float64)", example_dir=EXAMPLE_DIR))
    assert result == 456
