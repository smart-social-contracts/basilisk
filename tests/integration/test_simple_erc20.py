"""Integration tests for examples/simple_erc20 — ERC20-like token canister."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "simple_erc20"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_initialize_supply(canister):
    result = parse_candid_text(call_canister(
        canister, "initialize_supply",
        '("TestToken", "addr1", "TT", 1_000_000 : nat64)',
        example_dir=EXAMPLE_DIR, update=True,
    ))
    assert result is True


def test_name(canister):
    result = parse_candid_text(call_canister(canister, "name", example_dir=EXAMPLE_DIR))
    assert result == "TestToken"


def test_ticker(canister):
    result = parse_candid_text(call_canister(canister, "ticker", example_dir=EXAMPLE_DIR))
    assert result == "TT"


def test_total_supply(canister):
    result = parse_candid_text(call_canister(canister, "total_supply", example_dir=EXAMPLE_DIR))
    assert result == 1_000_000


def test_balance_original(canister):
    result = parse_candid_text(call_canister(canister, "balance", '("addr1")', example_dir=EXAMPLE_DIR))
    assert result == 1_000_000


def test_transfer(canister):
    result = parse_candid_text(call_canister(
        canister, "transfer", '("addr1", "addr2", 500 : nat64)',
        example_dir=EXAMPLE_DIR, update=True,
    ))
    assert result is True


def test_balance_after_transfer_sender(canister):
    result = parse_candid_text(call_canister(canister, "balance", '("addr1")', example_dir=EXAMPLE_DIR))
    assert result == 999_500


def test_balance_after_transfer_receiver(canister):
    result = parse_candid_text(call_canister(canister, "balance", '("addr2")', example_dir=EXAMPLE_DIR))
    assert result == 500
