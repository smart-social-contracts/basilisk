"""Integration tests for examples/service — Service type handling and cross-canister calls."""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR, _get_canister_id
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
