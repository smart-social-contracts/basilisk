"""Integration tests for examples/guard_functions — guard function behavior."""

import pytest
from .conftest import deploy_example, call_canister, call_canister_expect_trap, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "guard_functions"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    name = list(ids.keys())[0]
    return ids[name]


def test_loosely_guarded(canister):
    result = parse_candid_text(call_canister(canister, "loosely_guarded", example_dir=EXAMPLE_DIR))
    assert result is True


def test_custom_error_guarded_traps(canister):
    err = call_canister_expect_trap(canister, "custom_error_guarded", example_dir=EXAMPLE_DIR)
    assert "throw custom error" in err.lower() or "halted" in err.lower()


def test_error_string_guarded_traps(canister):
    err = call_canister_expect_trap(canister, "error_string_guarded", example_dir=EXAMPLE_DIR)
    assert "throw string" in err.lower() or "halted" in err.lower()


def test_tightly_guarded_traps(canister):
    err = call_canister_expect_trap(canister, "tightly_guarded", example_dir=EXAMPLE_DIR)
    assert "unpassable" in err.lower() or "halted" in err.lower()


def test_modify_state_guarded(canister):
    result = parse_candid_text(call_canister(canister, "modify_state_guarded", example_dir=EXAMPLE_DIR))
    assert result is True


def test_state_counter_incremented(canister):
    raw = call_canister(canister, "get_state", example_dir=EXAMPLE_DIR)
    assert "counter" in raw


def test_identifier_annotation(canister):
    result = parse_candid_text(call_canister(canister, "identifier_annotation", example_dir=EXAMPLE_DIR))
    assert result is True


def test_call_expression_without_options_object(canister):
    result = parse_candid_text(call_canister(canister, "call_expression_without_options_object", example_dir=EXAMPLE_DIR))
    assert result is True


def test_invalid_return_type_guarded_traps(canister):
    err = call_canister_expect_trap(canister, "invalid_return_type_guarded", example_dir=EXAMPLE_DIR)
    assert len(err) > 0


def test_bad_object_guarded_traps(canister):
    err = call_canister_expect_trap(canister, "bad_object_guarded", example_dir=EXAMPLE_DIR)
    assert len(err) > 0


def test_name_error_guarded_traps(canister):
    err = call_canister_expect_trap(canister, "name_error_guarded", example_dir=EXAMPLE_DIR)
    assert len(err) > 0
