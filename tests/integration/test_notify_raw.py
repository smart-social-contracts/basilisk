"""Integration tests for examples/notify_raw — one-way notification between canisters."""

import time
import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "notify_raw"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canisters(replica):
    ids = deploy_example(EXAMPLE)
    return ids


def test_send_notification_and_verify(canisters):
    canister1 = canisters.get("canister1") or list(canisters.values())[0]
    canister2 = canisters.get("canister2") or list(canisters.values())[-1]

    call_canister(canister1, "send_notification", example_dir=EXAMPLE_DIR, update=True)
    time.sleep(5)
    result = parse_candid_text(call_canister(canister2, "get_notified", example_dir=EXAMPLE_DIR))
    assert result is True
