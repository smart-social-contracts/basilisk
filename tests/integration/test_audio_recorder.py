"""Integration tests for examples/audio_recorder — CRUD for users and recordings."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "audio_recorder"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_create_user(canister):
    raw = call_canister(canister, "create_user", '("testuser")', example_dir=EXAMPLE_DIR)
    assert "testuser" in raw


def test_read_users(canister):
    raw = call_canister(canister, "read_users", example_dir=EXAMPLE_DIR)
    assert "testuser" in raw


def test_create_recording(canister):
    raw = call_canister(
        canister, "create_recording",
        '(blob "\\01\\02\\03\\04", "test recording", "0")',
        example_dir=EXAMPLE_DIR,
    )
    assert "Ok" in raw


def test_read_recordings(canister):
    raw = call_canister(canister, "read_recordings", example_dir=EXAMPLE_DIR)
    assert "test recording" in raw


def test_delete_recording(canister):
    raw = call_canister(canister, "delete_recording", '("0")', example_dir=EXAMPLE_DIR)
    assert "Ok" in raw


def test_delete_user(canister):
    raw = call_canister(canister, "delete_user", '("0")', example_dir=EXAMPLE_DIR)
    assert "Ok" in raw
