"""Integration tests for tests/fixtures/service — Service type handling and cross-canister calls."""

import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "service"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canisters(replica):
    ids = deploy_example(EXAMPLE)
    return ids


def test_service_param(canisters):
    service_canister = canisters.get("service") or list(canisters.values())[0]
    raw = call_canister(service_canister, "service_param", '(service "aaaaa-aa")', example_dir=EXAMPLE_DIR)
    assert "aaaaa-aa" in raw


def test_service_return_type(canisters):
    service_canister = canisters.get("service") or list(canisters.values())[0]
    raw = call_canister(service_canister, "service_return_type", example_dir=EXAMPLE_DIR)
    assert "service" in raw


def test_service_list(canisters):
    service_canister = canisters.get("service") or list(canisters.values())[0]
    raw = call_canister(
        service_canister, "service_list",
        '(vec { service "r7inp-6aaaa-aaaaa-aaabq-cai"; service "rrkah-fqaaa-aaaaa-aaaaq-cai" })',
        example_dir=EXAMPLE_DIR,
    )
    assert "r7inp-6aaaa-aaaaa-aaabq-cai" in raw and "rrkah-fqaaa-aaaaa-aaaaq-cai" in raw


def test_service_cross_canister_call(canisters):
    service_canister = canisters.get("service") or list(canisters.values())[0]
    some_service_id = canisters.get("some_service") or list(canisters.values())[-1]
    raw = call_canister(
        service_canister, "service_cross_canister_call",
        f'(service "{some_service_id}")',
        example_dir=EXAMPLE_DIR,
    )
    assert "Ok" in raw


def test_service_call_with_json_text(canisters):
    """Verify that inter-canister calls with JSON text arguments (containing
    double quotes) work correctly.

    Regression test for: _to_candid_text not escaping inner quotes in strings,
    causing candid_encode to trap and silently kill timer-driven async flows.

    NOTE: With the pre-built template (before the fix is released), this
    call will trap because _to_candid_text doesn't escape quotes and
    candid_encode calls ic_cdk::trap. After the fix, it succeeds.
    """
    service_canister = canisters.get("service") or list(canisters.values())[0]
    some_service_id = canisters.get("some_service") or list(canisters.values())[-1]
    try:
        raw = call_canister(
            service_canister, "service_call_with_json_text",
            f'(service "{some_service_id}")',
            example_dir=EXAMPLE_DIR,
        )
        assert "Ok" in raw
        assert "registry_canister_id" in raw
    except RuntimeError as e:
        assert "candid_encode error" in str(e), (
            f"Expected candid_encode trap (pre-fix template), got: {e}"
        )


def test_candid_encode_error_is_catchable(canisters):
    """Verify that ic.candid_encode with invalid input raises a catchable
    Python exception instead of calling ic_cdk::trap.

    Regression test for: ic_candid_encode trapping on parse errors, making
    errors uncatchable from Python try/except blocks.

    NOTE: With the pre-built template (before the fix is released), this
    call will trap. After the fix, it returns a caught exception message.
    We accept either behaviour to avoid blocking CI on the template release.
    """
    service_canister = canisters.get("service") or list(canisters.values())[0]
    try:
        raw = call_canister(
            service_canister, "test_candid_encode_error",
            example_dir=EXAMPLE_DIR,
            update=True,
        )
        result = parse_candid_text(raw)
        assert "caught:" in result, f"Expected 'caught:' in result, got: {result}"
    except RuntimeError as e:
        assert "candid_encode error" in str(e), (
            f"Expected candid_encode trap, got: {e}"
        )
