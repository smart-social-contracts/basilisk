"""Integration tests for examples/date — datetime operations in canister."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "date"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    name = list(ids.keys())[0]
    return ids[name]


def test_get_date(canister):
    result = parse_candid_text(call_canister(canister, "get_date", '("2023-06-26T00:00:00.000")', example_dir=EXAMPLE_DIR))
    assert result == 26


def test_get_day(canister):
    result = parse_candid_text(call_canister(canister, "get_day", '("2023-06-26T00:00:00.000")', example_dir=EXAMPLE_DIR))
    assert result == 0


def test_get_full_year(canister):
    result = parse_candid_text(call_canister(canister, "get_full_year", '("2023-06-26T00:00:00.000")', example_dir=EXAMPLE_DIR))
    assert result == 2023


def test_get_hours(canister):
    result = parse_candid_text(call_canister(canister, "get_hours", '("2023-06-26T12:34:56.789")', example_dir=EXAMPLE_DIR))
    assert result == 12


def test_get_milliseconds(canister):
    result = parse_candid_text(call_canister(canister, "get_milliseconds", '("2023-06-26T12:34:56.789")', example_dir=EXAMPLE_DIR))
    assert result == 789


def test_get_minutes(canister):
    result = parse_candid_text(call_canister(canister, "get_minutes", '("2023-06-26T12:34:56.789")', example_dir=EXAMPLE_DIR))
    assert result == 34


def test_get_month(canister):
    result = parse_candid_text(call_canister(canister, "get_month", '("2023-06-26T12:34:56.789")', example_dir=EXAMPLE_DIR))
    assert result == 6


def test_get_seconds(canister):
    result = parse_candid_text(call_canister(canister, "get_seconds", '("2023-06-26T12:34:56.789")', example_dir=EXAMPLE_DIR))
    assert result == 56


def test_get_time(canister):
    result = parse_candid_text(call_canister(canister, "get_time", '("1970-01-01T00:00:01.000")', example_dir=EXAMPLE_DIR))
    assert result == 1000


def test_get_timezone_offset(canister):
    result = parse_candid_text(call_canister(canister, "get_timezone_offset", '("2023-06-26T12:34:56.789")', example_dir=EXAMPLE_DIR))
    assert result == 0
