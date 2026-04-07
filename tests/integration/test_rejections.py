"""Integration tests for tests/fixtures/rejections — rejection code/message handling."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "rejections"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_get_rejection_code_no_error(canister):
    raw = call_canister(canister, "get_rejection_code_no_error", example_dir=EXAMPLE_DIR, update=True)
    assert len(raw) > 0


def test_get_rejection_message(canister):
    raw = call_canister(canister, "get_rejection_message", '("test")', example_dir=EXAMPLE_DIR, update=True)
    assert len(raw) > 0
