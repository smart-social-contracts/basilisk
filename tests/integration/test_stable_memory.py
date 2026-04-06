"""Integration tests for examples/stable_memory — stable memory read/write/grow."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "stable_memory"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_stable_size(canister):
    result = parse_candid_text(call_canister(canister, "stable_size", example_dir=EXAMPLE_DIR))
    assert result == 0


def test_stable64_size(canister):
    result = parse_candid_text(call_canister(canister, "stable64_size", example_dir=EXAMPLE_DIR))
    assert result == 0


def test_stable_grow(canister):
    raw = call_canister(canister, "stable_grow", "(5 : nat32)", example_dir=EXAMPLE_DIR)
    assert "Ok" in raw


def test_stable64_grow(canister):
    raw = call_canister(canister, "stable64_grow", "(5 : nat64)", example_dir=EXAMPLE_DIR)
    assert "Ok" in raw


def test_stable_bytes(canister):
    raw = call_canister(canister, "stable_bytes", example_dir=EXAMPLE_DIR)
    assert "blob" in raw


def test_stable_write_read_no_offset(canister):
    call_canister(canister, "stable_write", "(0 : nat32, vec { 0 : nat8; 1 : nat8; 2 : nat8; 3 : nat8; 4 : nat8; 5 : nat8 })", example_dir=EXAMPLE_DIR)
    raw = call_canister(canister, "stable_read", "(0 : nat32, 6 : nat32)", example_dir=EXAMPLE_DIR)
    assert "0" in raw and "5" in raw


def test_stable_write_read_with_offset(canister):
    call_canister(canister, "stable_write", "(5 : nat32, vec { 0 : nat8; 1 : nat8; 2 : nat8; 3 : nat8; 4 : nat8; 5 : nat8 })", example_dir=EXAMPLE_DIR)
    raw = call_canister(canister, "stable_read", "(5 : nat32, 6 : nat32)", example_dir=EXAMPLE_DIR)
    assert "0" in raw and "5" in raw


def test_stable64_write_read_no_offset(canister):
    call_canister(canister, "stable64_write", "(0 : nat64, vec { 0 : nat8; 1 : nat8; 2 : nat8; 3 : nat8; 4 : nat8; 5 : nat8 })", example_dir=EXAMPLE_DIR)
    raw = call_canister(canister, "stable64_read", "(0 : nat64, 6 : nat64)", example_dir=EXAMPLE_DIR)
    assert "0" in raw and "5" in raw
