"""Integration tests for examples/stable_structures — StableBTreeMap operations across canisters."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "stable_structures"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canisters(replica):
    ids = deploy_example(EXAMPLE)
    return ids


def test_canister1_set_and_get(canisters):
    c1 = canisters.get("canister1") or list(canisters.values())[0]
    call_canister(c1, "stable_map0_insert", '(0 : nat8, "value0")', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(c1, "stable_map0_get", "(0 : nat8)", example_dir=EXAMPLE_DIR)
    assert "value0" in raw


def test_canister1_contains_key(canisters):
    c1 = canisters.get("canister1") or list(canisters.values())[0]
    raw = call_canister(c1, "stable_map0_contains_key", "(0 : nat8)", example_dir=EXAMPLE_DIR)
    assert "true" in raw


def test_canister2_set_and_get(canisters):
    c2 = canisters.get("canister2") or list(canisters.values())[1]
    call_canister(c2, "stable_map5_insert", '(opt "key5", 5.0 : float64)', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(c2, "stable_map5_get", '(opt "key5")', example_dir=EXAMPLE_DIR)
    assert "5" in raw


def test_canister3_set_and_get(canisters):
    c3 = canisters.get("canister3") or list(canisters.values())[2]
    call_canister(c3, "stable_map10_insert", '(10.0 : float32, opt opt true)', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(c3, "stable_map10_get", '(10.0 : float32)', example_dir=EXAMPLE_DIR)
    assert "true" in raw or "opt" in raw
