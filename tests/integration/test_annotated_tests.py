"""Integration tests for tests/fixtures/annotated_tests — type annotations and func types."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "annotated_tests"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_is_empty(canister):
    result = parse_candid_text(call_canister(canister, "is_empty", example_dir=EXAMPLE_DIR))
    assert result is True


def test_get_type_alias(canister):
    result = parse_candid_text(call_canister(canister, "get_type_alias", example_dir=EXAMPLE_DIR))
    assert result is True


def test_get_func(canister):
    raw = call_canister(canister, "get_func", example_dir=EXAMPLE_DIR)
    assert "create_canister" in raw
