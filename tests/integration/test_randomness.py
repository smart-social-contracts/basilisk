"""Integration tests for tests/fixtures/randomness — random number generation in canister."""

import re
import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "randomness"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_random_number(canister):
    raw = call_canister(canister, "random_number", example_dir=EXAMPLE_DIR)
    m = re.search(r'([\d.]+)', raw)
    assert m is not None
    val = float(m.group(1))
    assert 0 <= val <= 1


def test_random_number_is_different(canister):
    raw1 = call_canister(canister, "random_number", example_dir=EXAMPLE_DIR)
    raw2 = call_canister(canister, "random_number", example_dir=EXAMPLE_DIR)
    # Extremely unlikely to be identical
    assert raw1 != raw2
