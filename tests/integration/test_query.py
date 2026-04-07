"""Integration tests for tests/fixtures/query — simple query canister."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "query"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    name = list(ids.keys())[0]
    return ids[name]


def test_simple_query(canister):
    result = parse_candid_text(call_canister(canister, "simple_query", example_dir=EXAMPLE_DIR))
    assert result == "This is a query function"
