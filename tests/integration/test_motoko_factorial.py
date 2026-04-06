"""Integration tests for examples/motoko_examples/factorial — factorial computation."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "motoko_examples/factorial"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_fac_0(canister):
    result = parse_candid_text(call_canister(canister, "fac", "(0 : nat)", example_dir=EXAMPLE_DIR))
    assert result == 1


def test_fac_1(canister):
    result = parse_candid_text(call_canister(canister, "fac", "(1 : nat)", example_dir=EXAMPLE_DIR))
    assert result == 1


def test_fac_5(canister):
    result = parse_candid_text(call_canister(canister, "fac", "(5 : nat)", example_dir=EXAMPLE_DIR))
    assert result == 120


def test_fac_10(canister):
    result = parse_candid_text(call_canister(canister, "fac", "(10 : nat)", example_dir=EXAMPLE_DIR))
    assert result == 3_628_800
