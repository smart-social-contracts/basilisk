"""Integration tests for tests/fixtures/keywords — Python/Rust keyword handling in Candid."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "keywords"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_simple_keyword(canister):
    raw = call_canister(canister, "simple_keyword", '(record { "from" = "hello" })', example_dir=EXAMPLE_DIR)
    assert "hello" in raw


def test_rust_keyword(canister):
    raw = call_canister(canister, "rust_keyword", example_dir=EXAMPLE_DIR)
    assert "Become" in raw and "Function" in raw


def test_rust_keyword_variant(canister):
    raw = call_canister(canister, "rust_keyword_variant", example_dir=EXAMPLE_DIR)
    assert "type" in raw


def test_keyword_variant(canister):
    raw = call_canister(canister, "keyword_variant", '(variant { "raise" })', example_dir=EXAMPLE_DIR)
    assert "raise" in raw


def test_complex_keyword(canister):
    raw = call_canister(canister, "complex_keyword", example_dir=EXAMPLE_DIR)
    assert "False" in raw or "True" in raw
