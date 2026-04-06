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
    raw = call_canister(canister, "test_fs_diagnostics", example_dir=EXAMPLE_DIR, update=True)
    assert "python" in raw


def test_mkdir(canister):
    raw = call_canister(canister, "test_fs_mkdir", example_dir=EXAMPLE_DIR, update=True)
    assert "mkdir=OK" in raw or "mkdir=EXISTS" in raw


def test_path_exists(canister):
    raw = call_canister(canister, "test_fs_path_exists", example_dir=EXAMPLE_DIR, update=True)
    assert "True" in raw


def test_rename(canister):
    raw = call_canister(canister, "test_fs_rename", example_dir=EXAMPLE_DIR, update=True)
    assert "True" in raw


def test_rmdir(canister):
    raw = call_canister(canister, "test_fs_rmdir", example_dir=EXAMPLE_DIR, update=True)
    assert "True" in raw


def test_nested_mkdir(canister):
    raw = call_canister(canister, "test_fs_nested_mkdir", example_dir=EXAMPLE_DIR, update=True)
    assert "True" in raw
