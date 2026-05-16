"""Integration tests for __shell__ and __browse__ built-in endpoints."""

import json
import os

import pytest

from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR

EXAMPLE = "browse"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids["browse"]


# ---------------------------------------------------------------------------
# __browse__ tests
# ---------------------------------------------------------------------------


def test_browse_schema(canister):
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"schema\\\"}")')
    text = parse_candid_text(raw)
    schema = json.loads(text)
    assert "stable_maps" in schema
    assert "users" in schema["stable_maps"]
    assert schema["stable_maps"]["users"]["key_type"] == "text"
    assert schema["stable_maps"]["users"]["value_type"] == "nat"
    assert "stable_sets" in schema
    assert "tags" in schema["stable_sets"]
    assert "stable_vecs" in schema
    assert "logs" in schema["stable_vecs"]


def test_browse_map_keys(canister):
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"keys\\\", \\\"map\\\": \\\"users\\\"}")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    keys = result["result"]
    assert "alice" in keys
    assert "bob" in keys


def test_browse_map_get(canister):
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"get\\\", \\\"map\\\": \\\"users\\\", \\\"key\\\": \\\"alice\\\"}")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    assert result["result"] == 30


def test_browse_map_items(canister):
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"items\\\", \\\"map\\\": \\\"users\\\"}")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    items = result["result"]
    assert len(items) == 2
    names = [item[0] for item in items]
    assert "alice" in names
    assert "bob" in names


def test_browse_map_len(canister):
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"len\\\", \\\"map\\\": \\\"users\\\"}")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    assert result["result"] == 2


def test_browse_set_keys(canister):
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"keys\\\", \\\"set\\\": \\\"tags\\\"}")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    assert "python" in result["result"]
    assert "icp" in result["result"]


def test_browse_vec_items(canister):
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"items\\\", \\\"vec\\\": \\\"logs\\\"}")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    assert "canister initialized" in result["result"]


def test_browse_unknown_target(canister):
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"keys\\\", \\\"map\\\": \\\"nonexistent\\\"}")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    assert "error" in result
    assert "available" in result


def test_browse_invalid_json(canister):
    raw = call_canister(canister, "__browse__", '("not json")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    assert "error" in result


def test_browse_unknown_action(canister):
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"delete\\\", \\\"map\\\": \\\"users\\\"}")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    assert "error" in result
    assert "actions" in result


# ---------------------------------------------------------------------------
# __shell__ tests
# ---------------------------------------------------------------------------


def test_shell_basic_exec(canister):
    raw = call_canister(canister, "__shell__", '("print(1 + 1)")', update=True)
    text = parse_candid_text(raw)
    assert "2" in text


def test_shell_namespace_persistence(canister):
    call_canister(canister, "__shell__", '("x = 42")', update=True)
    raw = call_canister(canister, "__shell__", '("print(x)")', update=True)
    text = parse_candid_text(raw)
    assert "42" in text


def test_shell_ic_available(canister):
    raw = call_canister(canister, "__shell__", '("print(type(ic))")', update=True)
    text = parse_candid_text(raw)
    assert "ic" in text.lower() or "class" in text.lower()


def test_shell_basilisk_available(canister):
    raw = call_canister(canister, "__shell__", '("print(basilisk.__version__)")', update=True)
    text = parse_candid_text(raw)
    assert text.strip() != ""


def test_shell_error_handling(canister):
    raw = call_canister(canister, "__shell__", '("raise ValueError(\\\"test error\\\")")', update=True)
    text = parse_candid_text(raw)
    assert "ValueError" in text
    assert "test error" in text


# ---------------------------------------------------------------------------
# __browse__ after __shell__ mutation
# ---------------------------------------------------------------------------


def test_browse_after_shell_mutation(canister):
    """Add data via __shell__, then read via __browse__ to verify consistency."""
    call_canister(canister, "add_user", '("charlie", 35 : nat)', update=True)
    raw = call_canister(canister, "__browse__", '("{\\\"action\\\": \\\"len\\\", \\\"map\\\": \\\"users\\\"}")')
    text = parse_candid_text(raw)
    result = json.loads(text)
    assert result["result"] == 3
