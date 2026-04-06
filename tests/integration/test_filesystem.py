"""Integration tests for examples/filesystem — in-memory filesystem operations."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "filesystem"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    name = list(ids.keys())[0]
    return ids[name]


def test_diagnostics(canister):
    raw = call_canister(canister, "diagnostics", example_dir=EXAMPLE_DIR)
    assert len(raw) > 0


def test_mkdir(canister):
    result = parse_candid_text(call_canister(canister, "create_dir", '("/test_dir")', example_dir=EXAMPLE_DIR))
    assert result is True or "true" in str(result).lower()


def test_path_exists(canister):
    result = parse_candid_text(call_canister(canister, "path_exists", '("/test_dir")', example_dir=EXAMPLE_DIR))
    assert result is True


def test_rename(canister):
    result = parse_candid_text(call_canister(canister, "rename_path", '("/test_dir", "/renamed_dir")', example_dir=EXAMPLE_DIR))
    assert result is True or "true" in str(result).lower()


def test_path_exists_after_rename(canister):
    result = parse_candid_text(call_canister(canister, "path_exists", '("/renamed_dir")', example_dir=EXAMPLE_DIR))
    assert result is True


def test_old_path_gone(canister):
    result = parse_candid_text(call_canister(canister, "path_exists", '("/test_dir")', example_dir=EXAMPLE_DIR))
    assert result is False


def test_rmdir(canister):
    result = parse_candid_text(call_canister(canister, "remove_dir", '("/renamed_dir")', example_dir=EXAMPLE_DIR))
    assert result is True or "true" in str(result).lower()


def test_nested_mkdir(canister):
    result = parse_candid_text(call_canister(canister, "create_dir_all", '("/a/b/c")', example_dir=EXAMPLE_DIR))
    assert result is True or "true" in str(result).lower()
