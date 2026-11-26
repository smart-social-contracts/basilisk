"""Integration tests for tests/fixtures/manual_reply — manual reply mechanism."""

import os
import re
import subprocess

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR

EXAMPLE = "manual_reply"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


def test_manual_update(canister):
    result = parse_candid_text(call_canister(canister, "manual_update", '("test")', example_dir=EXAMPLE_DIR))
    assert isinstance(result, str)


def test_manual_query(canister):
    result = parse_candid_text(call_canister(canister, "manual_query", '("test")', example_dir=EXAMPLE_DIR))
    assert isinstance(result, str)


def test_update_void(canister):
    raw = call_canister(canister, "update_void", example_dir=EXAMPLE_DIR)
    # void returns empty tuple
    assert raw.strip() == "()" or raw.strip() == ""


def test_query_void(canister):
    raw = call_canister(canister, "query_void", example_dir=EXAMPLE_DIR)
    assert raw.strip() == "()" or raw.strip() == ""


def test_manual_reply_keeps_its_type_while_other_methods_run(canister):
    """ic.reply() after an await used the return type of the method dispatched last (#69).

    count_call() -> nat64 runs while manual_reply_after_calls() -> Manual[str]
    waits; its text reply then had to be encoded as nat64, and trapped.
    """
    waiting = subprocess.Popen(
        ["icp", "canister", "call", canister, "manual_reply_after_calls", "()"],
        cwd=EXAMPLE_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    while waiting.poll() is None:
        call_canister(canister, "count_call", example_dir=EXAMPLE_DIR, update=True)
    out, err = waiting.communicate()
    assert waiting.returncode == 0, err
    calls = int(re.search(r"replied after (\d+) other calls", parse_candid_text(out)).group(1))
    assert calls > 0, "no call ran while the Manual method waited, so nothing was tested"
