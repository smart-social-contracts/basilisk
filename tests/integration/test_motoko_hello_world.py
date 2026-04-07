"""Integration tests for tests/fixtures/motoko_examples/hello-world — minimal canister."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "motoko_examples/hello-world"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_main(canister):
    raw = call_canister(canister, "main", example_dir=EXAMPLE_DIR)
    # void return
    assert raw.strip() == "()" or raw.strip() == ""
