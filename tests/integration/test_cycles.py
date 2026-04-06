"""Integration tests for examples/cycles — cycle transfer between canisters."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "cycles"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canisters(replica):
    ids = deploy_example(EXAMPLE)
    return ids


def test_send_cycles(canisters):
    intermediary = canisters.get("intermediary") or list(canisters.values())[-1]
    raw = call_canister(intermediary, "send_cycles", example_dir=EXAMPLE_DIR, update=True)
    assert len(raw) > 0
