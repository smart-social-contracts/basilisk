"""Integration tests for tests/fixtures/blob_array — blob type handling."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "blob_array"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_get_blob(canister):
    raw = call_canister(canister, "get_blob", example_dir=EXAMPLE_DIR)
    assert "blob" in raw or "hello" in raw


def test_get_blobs(canister):
    raw = call_canister(canister, "get_blobs", example_dir=EXAMPLE_DIR)
    assert "vec" in raw or "blob" in raw
