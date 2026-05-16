"""Integration tests for custom __shell__ and __browse__ overrides."""

import json
import os

import pytest

from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR

EXAMPLE = "browse_custom"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids["browse_custom"]


def test_custom_browse_schema(canister):
    """Custom __browse__ returns its own schema format."""
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"schema\\\"}")')
    text = parse_candid_text(raw)
    schema = json.loads(text)
    assert schema["custom"] is True
    assert "scores" in schema["maps"]


def test_custom_browse_after_mutation(canister):
    call_canister(canister, "set_score", '("alice", 100 : nat)', update=True)
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"get\\\", \\\"key\\\": \\\"alice\\\"}")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    assert result["result"] == 100


def test_custom_browse_keys(canister):
    call_canister(canister, "set_score", '("bob", 200 : nat)', update=True)
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"keys\\\"}")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    assert "alice" in result["result"]
    assert "bob" in result["result"]


def test_custom_shell_works(canister):
    raw = call_canister(canister, "__shell__", '("print(scores.len())")', update=True)
    text = parse_candid_text(raw)
    assert text.strip().isdigit()
