"""Integration tests for tests/fixtures/stdlib — standard library modules in canister."""

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
    assert re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", result) and not result.startswith("1970")


def test_time_is_the_ic_time(canister):
    """time.time() and datetime.now() read the IC clock, not 0 (#73)."""
    result = parse_candid_text(call_canister(canister, "test_time_is_the_ic_time", example_dir=EXAMPLE_DIR))
    time_time, now, ic_time = (float(part) for part in result.split("|"))
    assert ic_time > 1_700_000_000
    assert abs(time_time - ic_time) < 1e-6
    assert abs(now - ic_time) < 1e-6


def test_datetime_values(canister):
    """Calendar arithmetic and formatting give the real answers, not 1970 and zero (#73)."""
    result = parse_candid_text(call_canister(canister, "test_datetime_values", example_dir=EXAMPLE_DIR))
    assert result.split("|") == [
        "2027-01-15 08:00:00", "1157 days, 9:46:40", "1800000000.0", "2027-01-15T08:00:00.123000"]


def test_sleep_refuses(canister):
    result = parse_candid_text(call_canister(canister, "test_sleep_refuses", example_dir=EXAMPLE_DIR))
    assert result == "refused"


def test_enum_members(canister):
    """Members are instances with values, classes iterate, auto() counts (#67)."""
    result = parse_candid_text(call_canister(canister, "test_enum_members", example_dir=EXAMPLE_DIR))
    assert result.split("|") == ["Color", "<Color.BLUE: 2>", "RED,BLUE", "True"]


def test_weakref_frees(canister):
    """A weak reference does not keep its object alive (#67)."""
    result = parse_candid_text(call_canister(canister, "test_weakref_frees", example_dir=EXAMPLE_DIR))
    assert result == "True|0"


def test_struct_pack(canister):
    """struct is the compiled-in _struct, not an empty stub (#67)."""
    result = parse_candid_text(call_canister(canister, "test_struct_pack", example_dir=EXAMPLE_DIR))
    assert result == "010000000200|(1, 2)"


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
