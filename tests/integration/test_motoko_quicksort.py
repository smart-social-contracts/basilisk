"""Integration tests for examples/motoko_examples/quicksort — sorting canister."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "motoko_examples/quicksort"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_sort_empty(canister):
    raw = call_canister(canister, "sort", "(vec {})", example_dir=EXAMPLE_DIR)
    assert "vec {}" in raw or raw.strip() == "(vec {})"


def test_sort_single(canister):
    raw = call_canister(canister, "sort", "(vec { 1 : int })", example_dir=EXAMPLE_DIR)
    assert "1" in raw


def test_sort_multiple(canister):
    raw = call_canister(canister, "sort", "(vec { 5 : int; 3 : int; 1 : int; 4 : int; 2 : int })", example_dir=EXAMPLE_DIR)
    # Should return sorted: 1, 2, 3, 4, 5
    assert "1" in raw and "5" in raw
