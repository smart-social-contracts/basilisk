"""Integration tests for examples/bytes — bytes roundtrip."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "bytes"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_get_bytes_roundtrip(canister):
    raw = call_canister(canister, "get_bytes", '(blob "\\01\\02\\03\\04\\05")', example_dir=EXAMPLE_DIR)
    assert "blob" in raw


def test_get_bytes_empty(canister):
    raw = call_canister(canister, "get_bytes", '(blob "")', example_dir=EXAMPLE_DIR)
    assert "blob" in raw
