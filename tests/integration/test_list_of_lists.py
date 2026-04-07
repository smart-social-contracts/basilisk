"""Integration tests for examples/list_of_lists — nested list types."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "list_of_lists"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_list_of_string_one(canister):
    raw = call_canister(canister, "list_of_string_one", '(vec { "hello"; "world" })', example_dir=EXAMPLE_DIR)
    assert "hello" in raw and "world" in raw


def test_list_of_string_two(canister):
    raw = call_canister(canister, "list_of_string_two", '(vec { vec { "a"; "b" }; vec { "c" } })', example_dir=EXAMPLE_DIR)
    assert "a" in raw and "c" in raw


def test_list_of_bool(canister):
    raw = call_canister(canister, "list_of_bool", '(vec { vec { vec { true; false } } })', example_dir=EXAMPLE_DIR)
    assert "true" in raw and "false" in raw


def test_list_of_null(canister):
    raw = call_canister(canister, "list_of_null", '(vec { vec { vec { null; null } } })', example_dir=EXAMPLE_DIR)
    assert "null" in raw


def test_list_of_nat8(canister):
    raw = call_canister(canister, "list_of_nat8", '(vec { vec { vec { 1 : nat8; 2 : nat8; 3 : nat8 } } })', example_dir=EXAMPLE_DIR)
    assert "1" in raw and "3" in raw


def test_list_of_record(canister):
    raw = call_canister(
        canister, "list_of_record",
        '(vec { vec { vec { record { name = "Alice"; age = 30 : nat8 } } } })',
        example_dir=EXAMPLE_DIR,
    )
    assert "Alice" in raw


def test_list_of_variant(canister):
    raw = call_canister(
        canister, "list_of_variant",
        '(vec { vec { vec { variant { solid } } } })',
        example_dir=EXAMPLE_DIR,
    )
    assert "solid" in raw
