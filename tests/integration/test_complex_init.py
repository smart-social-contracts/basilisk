"""Integration tests for tests/fixtures/complex_init — complex initialization."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "complex_init"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_greet_user(canister):
    result = parse_candid_text(call_canister(canister, "greet_user", example_dir=EXAMPLE_DIR))
    assert isinstance(result, str) and len(result) > 0
