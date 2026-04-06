"""Integration tests for examples/optional_types — optional/opt type handling."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "optional_types"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_get_html(canister):
    raw = call_canister(canister, "get_html", example_dir=EXAMPLE_DIR)
    assert "head" in raw


def test_get_head(canister):
    raw = call_canister(canister, "get_head", example_dir=EXAMPLE_DIR)
    assert "elements" in raw


def test_get_head_with_elements(canister):
    raw = call_canister(canister, "get_head_with_elements", example_dir=EXAMPLE_DIR)
    assert "elements" in raw and "0" in raw


def test_get_element_empty(canister):
    raw = call_canister(canister, "get_element", "(vec {})", example_dir=EXAMPLE_DIR)
    assert "vec" in raw or "null" in raw or raw.strip() == "(vec {})"
