"""Integration tests for tests/fixtures/audio_recorder — CRUD for users and recordings."""

import re
import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "audio_recorder"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)

# Module-level state to pass principal IDs between ordered tests
_user_principal = None
_recording_principal = None


def _extract_principal(raw):
    """Extract a principal string from candid output like 'id = principal "xxx"'."""
    m = re.search(r'principal\s+"([^"]+)"', raw)
    return m.group(1) if m else None


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_create_user(canister):
    global _user_principal
    raw = call_canister(canister, "create_user", '("testuser")', example_dir=EXAMPLE_DIR, update=True)
    assert "testuser" in raw
    _user_principal = _extract_principal(raw)
    assert _user_principal, f"Could not extract principal from: {raw}"


def test_read_users(canister):
    raw = call_canister(canister, "read_users", example_dir=EXAMPLE_DIR)
    assert "testuser" in raw


def test_create_recording(canister):
    global _recording_principal
    assert _user_principal, "test_create_user must run first"
    raw = call_canister(
        canister, "create_recording",
        f'(blob "\\01\\02\\03\\04", "test recording", principal "{_user_principal}")',
        example_dir=EXAMPLE_DIR, update=True,
    )
    assert "Ok" in raw
    _recording_principal = _extract_principal(raw)


def test_read_recordings(canister):
    raw = call_canister(canister, "read_recordings", example_dir=EXAMPLE_DIR)
    assert "test recording" in raw


def test_delete_recording(canister):
    assert _recording_principal, "test_create_recording must run first"
    raw = call_canister(
        canister, "delete_recording",
        f'(principal "{_recording_principal}")',
        example_dir=EXAMPLE_DIR, update=True,
    )
    assert "Ok" in raw


def test_delete_user(canister):
    assert _user_principal, "test_create_user must run first"
    raw = call_canister(
        canister, "delete_user",
        f'(principal "{_user_principal}")',
        example_dir=EXAMPLE_DIR, update=True,
    )
    assert "Ok" in raw
