"""Integration tests for tests/fixtures/primitive_types — all Candid primitive types."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os
import math

EXAMPLE = "primitive_types"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_get_string(canister):
    result = parse_candid_text(call_canister(canister, "get_string", example_dir=EXAMPLE_DIR))
    assert result == "string"


def test_print_string(canister):
    result = parse_candid_text(call_canister(canister, "print_string", '("hello")', example_dir=EXAMPLE_DIR))
    assert result == "hello"


def test_get_text(canister):
    result = parse_candid_text(call_canister(canister, "get_text", example_dir=EXAMPLE_DIR))
    assert result == "text"


def test_print_text(canister):
    result = parse_candid_text(call_canister(canister, "print_text", '("hello")', example_dir=EXAMPLE_DIR))
    assert result == "hello"


def test_get_int(canister):
    result = parse_candid_text(call_canister(canister, "get_int", example_dir=EXAMPLE_DIR))
    assert result == 170_141_183_460_469_231_731_687_303_715_884_105_727


def test_print_int(canister):
    result = parse_candid_text(call_canister(canister, "print_int", "(42 : int)", example_dir=EXAMPLE_DIR))
    assert result == 42


def test_get_int64(canister):
    result = parse_candid_text(call_canister(canister, "get_int64", example_dir=EXAMPLE_DIR))
    assert result == 9_223_372_036_854_775_807


def test_get_int32(canister):
    result = parse_candid_text(call_canister(canister, "get_int32", example_dir=EXAMPLE_DIR))
    assert result == 2_147_483_647


def test_get_int16(canister):
    result = parse_candid_text(call_canister(canister, "get_int16", example_dir=EXAMPLE_DIR))
    assert result == 32_767


def test_get_int8(canister):
    result = parse_candid_text(call_canister(canister, "get_int8", example_dir=EXAMPLE_DIR))
    assert result == 127


def test_get_nat(canister):
    result = parse_candid_text(call_canister(canister, "get_nat", example_dir=EXAMPLE_DIR))
    assert result == 340_282_366_920_938_463_463_374_607_431_768_211_455


def test_get_nat64(canister):
    result = parse_candid_text(call_canister(canister, "get_nat64", example_dir=EXAMPLE_DIR))
    assert result == 18_446_744_073_709_551_615


def test_get_nat32(canister):
    result = parse_candid_text(call_canister(canister, "get_nat32", example_dir=EXAMPLE_DIR))
    assert result == 4_294_967_295


def test_get_nat16(canister):
    result = parse_candid_text(call_canister(canister, "get_nat16", example_dir=EXAMPLE_DIR))
    assert result == 65_535


def test_get_nat8(canister):
    result = parse_candid_text(call_canister(canister, "get_nat8", example_dir=EXAMPLE_DIR))
    assert result == 255


def test_get_float64(canister):
    raw = call_canister(canister, "get_float64", example_dir=EXAMPLE_DIR)
    # dfx outputs floats as e.g. (2.718281828459045 : float64)
    import re
    m = re.search(r'([\d.]+(?:e[+-]?\d+)?)\s*:\s*float64', raw)
    assert m is not None
    val = float(m.group(1))
    assert abs(val - math.e) < 0.0001


def test_get_float32(canister):
    raw = call_canister(canister, "get_float32", example_dir=EXAMPLE_DIR)
    import re
    m = re.search(r'([\d.]+(?:e[+-]?\d+)?)\s*:\s*float32', raw)
    assert m is not None
    val = float(m.group(1))
    assert abs(val - math.pi) < 0.001


def test_get_bool(canister):
    result = parse_candid_text(call_canister(canister, "get_bool", example_dir=EXAMPLE_DIR))
    assert result is True


def test_print_bool(canister):
    result = parse_candid_text(call_canister(canister, "print_bool", "(false)", example_dir=EXAMPLE_DIR))
    assert result is False


def test_get_principal(canister):
    raw = call_canister(canister, "get_principal", example_dir=EXAMPLE_DIR)
    assert "rrkah-fqaaa-aaaaa-aaaaq-cai" in raw


def test_get_null(canister):
    raw = call_canister(canister, "get_null", example_dir=EXAMPLE_DIR)
    assert "null" in raw


def test_get_reserved(canister):
    raw = call_canister(canister, "get_reserved", example_dir=EXAMPLE_DIR)
    assert "null" in raw or raw.strip() == "(null)"
