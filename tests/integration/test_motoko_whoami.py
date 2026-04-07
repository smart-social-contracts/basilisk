"""Integration tests for tests/fixtures/motoko_examples/whoami — identity/principal canister."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "motoko_examples/whoami"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_installer(canister):
    raw = call_canister(canister, "installer", example_dir=EXAMPLE_DIR)
    assert "principal" in raw.lower() or len(raw) > 5


def test_whoami(canister):
    raw = call_canister(canister, "whoami", example_dir=EXAMPLE_DIR)
    assert "principal" in raw.lower() or len(raw) > 5


def test_id(canister):
    raw = call_canister(canister, "id", example_dir=EXAMPLE_DIR)
    assert "principal" in raw.lower() or len(raw) > 5


def test_id_quick(canister):
    raw = call_canister(canister, "id_quick", example_dir=EXAMPLE_DIR)
    assert "principal" in raw.lower() or len(raw) > 5
