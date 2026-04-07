"""Integration tests for tests/fixtures/principal — Principal type handling."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "principal"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_principal_return_type(canister):
    raw = call_canister(canister, "principal_return_type", example_dir=EXAMPLE_DIR)
    assert "aaaaa-aa" in raw


def test_principal_param(canister):
    raw = call_canister(canister, "principal_param", '(principal "aaaaa-aa")', example_dir=EXAMPLE_DIR)
    assert "aaaaa-aa" in raw


def test_principal_in_record(canister):
    raw = call_canister(canister, "principal_in_record", example_dir=EXAMPLE_DIR)
    assert "aaaaa-aa" in raw and "lastmjs" in raw


def test_principal_in_variant(canister):
    raw = call_canister(canister, "principal_in_variant", example_dir=EXAMPLE_DIR)
    assert "WaitingOn" in raw and "aaaaa-aa" in raw


def test_principal_from_text(canister):
    raw = call_canister(canister, "principal_from_text", '("aaaaa-aa")', example_dir=EXAMPLE_DIR)
    assert "aaaaa-aa" in raw


def test_principal_to_text(canister):
    raw = call_canister(canister, "principal_to_text", '(principal "aaaaa-aa")', example_dir=EXAMPLE_DIR)
    assert "aaaaa-aa" in raw


def test_principal_to_blob(canister):
    raw = call_canister(canister, "principal_to_blob", '(principal "aaaaa-aa")', example_dir=EXAMPLE_DIR)
    assert "blob" in raw


def test_principal_from_blob(canister):
    raw = call_canister(canister, "principal_from_blob", '(blob "\\00\\00\\00\\00\\00\\00\\00\\00\\01\\01")', example_dir=EXAMPLE_DIR)
    assert "aaaaa-aa" in raw
