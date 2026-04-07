"""Integration tests for tests/fixtures/outgoing_http_requests — HTTP outcalls from canister."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "outgoing_http_requests"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_xkcd(canister):
    raw = call_canister(canister, "xkcd", example_dir=EXAMPLE_DIR)
    assert "200" in raw
