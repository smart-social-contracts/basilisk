"""Integration tests for examples/stdlib — standard library modules in canister."""

import re
import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "stdlib"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_base64(canister):
    raw = call_canister(canister, "test_base64", example_dir=EXAMPLE_DIR)
    # Returns blob containing base64 encoded "Hello there sir"
    assert "blob" in raw or len(raw) > 5


def test_collections(canister):
    result = parse_candid_text(call_canister(canister, "test_collections", example_dir=EXAMPLE_DIR))
    assert result == "apple"


def test_datetime(canister):
    result = parse_candid_text(call_canister(canister, "test_datetime", example_dir=EXAMPLE_DIR))
    assert isinstance(result, str) and len(result) > 0


def test_itertools(canister):
    raw = call_canister(canister, "test_itertools", example_dir=EXAMPLE_DIR)
    assert "ab" in raw and "cd" in raw


def test_json(canister):
    result = parse_candid_text(call_canister(canister, "test_json", example_dir=EXAMPLE_DIR))
    assert "hello" in result and "world" in result


def test_random(canister):
    raw = call_canister(canister, "test_random", example_dir=EXAMPLE_DIR)
    # Should return a float64 between 0 and 1
    m = re.search(r'([\d.]+)', raw)
    assert m is not None
    val = float(m.group(1))
    assert 0 <= val <= 1


def test_string(canister):
    result = parse_candid_text(call_canister(canister, "test_string", example_dir=EXAMPLE_DIR))
    assert result == "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def test_urllib(canister):
    result = parse_candid_text(call_canister(canister, "test_urllib", example_dir=EXAMPLE_DIR))
    assert result == "https://www.example.com/search?query=test&page=1"


def test_uuid(canister):
    result = parse_candid_text(call_canister(canister, "test_uuid", example_dir=EXAMPLE_DIR))
    pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    assert re.match(pattern, result, re.IGNORECASE)


def test_fs_mkdir_and_listdir(canister):
    result = parse_candid_text(call_canister(canister, "test_fs_mkdir_and_listdir", example_dir=EXAMPLE_DIR))
    assert "subdir" in result


def test_fs_write_and_read(canister):
    result = parse_candid_text(call_canister(canister, "test_fs_write_and_read", example_dir=EXAMPLE_DIR))
    assert result == "hello from ic-wasi-polyfill"


def test_fs_path_exists(canister):
    raw = call_canister(canister, "test_fs_path_exists", example_dir=EXAMPLE_DIR)
    assert "True" in raw


def test_fs_stat(canister):
    raw = call_canister(canister, "test_fs_stat", example_dir=EXAMPLE_DIR)
    assert "10" in raw


def test_fs_remove_and_rename(canister):
    raw = call_canister(canister, "test_fs_remove_and_rename", example_dir=EXAMPLE_DIR)
    assert "True" in raw
