"""Integration tests for examples/management_canister — IC management canister API."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "management_canister"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_execute_create_canister(canister):
    raw = call_canister(canister, "execute_create_canister", example_dir=EXAMPLE_DIR)
    assert "Ok" in raw


def test_get_canister_status(canister):
    cid_raw = call_canister(canister, "get_created_canister_id", example_dir=EXAMPLE_DIR)
    raw = call_canister(canister, "get_canister_status", f'(record {{ canister_id = {cid_raw.strip()} }})', example_dir=EXAMPLE_DIR)
    assert "Ok" in raw and "running" in raw


def test_execute_update_settings(canister):
    raw = call_canister(canister, "execute_update_settings", example_dir=EXAMPLE_DIR)
    assert "Ok" in raw


def test_execute_install_code(canister):
    raw = call_canister(canister, "execute_install_code", example_dir=EXAMPLE_DIR)
    assert "Ok" in raw


def test_execute_uninstall_code(canister):
    raw = call_canister(canister, "execute_uninstall_code", example_dir=EXAMPLE_DIR)
    assert "Ok" in raw


def test_get_raw_rand(canister):
    raw = call_canister(canister, "get_raw_rand", example_dir=EXAMPLE_DIR)
    assert "Ok" in raw


def test_execute_stop_canister(canister):
    raw = call_canister(canister, "execute_stop_canister", example_dir=EXAMPLE_DIR)
    assert "Ok" in raw


def test_execute_start_canister(canister):
    raw = call_canister(canister, "execute_start_canister", example_dir=EXAMPLE_DIR)
    assert "Ok" in raw


def test_execute_delete_canister(canister):
    raw = call_canister(canister, "execute_delete_canister", example_dir=EXAMPLE_DIR)
    assert "Ok" in raw
