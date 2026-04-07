"""Integration tests for tests/fixtures/manual_reply — manual reply mechanism."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "manual_reply"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_manual_update(canister):
    result = parse_candid_text(call_canister(canister, "manual_update", '("test")', example_dir=EXAMPLE_DIR))
    assert isinstance(result, str)


def test_manual_query(canister):
    result = parse_candid_text(call_canister(canister, "manual_query", '("test")', example_dir=EXAMPLE_DIR))
    assert isinstance(result, str)


def test_update_void(canister):
    raw = call_canister(canister, "update_void", example_dir=EXAMPLE_DIR)
    # void returns empty tuple
    assert raw.strip() == "()" or raw.strip() == ""


def test_query_void(canister):
    raw = call_canister(canister, "query_void", example_dir=EXAMPLE_DIR)
    assert raw.strip() == "()" or raw.strip() == ""
