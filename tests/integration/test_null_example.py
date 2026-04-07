"""Integration tests for tests/fixtures/null_example — null type handling."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "null_example"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_null_function(canister):
    raw = call_canister(canister, "null_function", "(null)", example_dir=EXAMPLE_DIR)
    assert "null" in raw


def test_void_is_not_null(canister):
    raw = call_canister(canister, "void_is_not_null", example_dir=EXAMPLE_DIR)
    # void returns ()
    assert raw.strip() == "()" or raw.strip() == ""


def test_get_partially_null_record(canister):
    raw = call_canister(canister, "get_partially_null_record", example_dir=EXAMPLE_DIR)
    assert "first_item" in raw and "null" in raw and "third_item" in raw


def test_set_partially_null_record(canister):
    raw = call_canister(
        canister, "set_partially_null_record",
        '(record { first_item = 5 : int; second_item = null; third_item = 10 : int })',
        example_dir=EXAMPLE_DIR, update=True,
    )
    assert "5" in raw and "null" in raw and "10" in raw


def test_get_small_null_record(canister):
    raw = call_canister(canister, "get_small_null_record", example_dir=EXAMPLE_DIR)
    assert "null" in raw


def test_set_small_null_record(canister):
    raw = call_canister(
        canister, "set_small_null_record",
        '(record { first_item = null; second_item = null })',
        example_dir=EXAMPLE_DIR,
    )
    assert "null" in raw


def test_get_large_null_record(canister):
    raw = call_canister(canister, "get_large_null_record", example_dir=EXAMPLE_DIR)
    assert "null" in raw


def test_set_large_null_record(canister):
    raw = call_canister(
        canister, "set_large_null_record",
        '(record { first_item = null; second_item = null; third_item = null })',
        example_dir=EXAMPLE_DIR,
    )
    assert "null" in raw
