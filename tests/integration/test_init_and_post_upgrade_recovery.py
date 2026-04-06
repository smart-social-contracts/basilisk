"""Integration tests for examples/init_and_post_upgrade_recovery — init/upgrade error recovery."""

import subprocess
import pytest
from .conftest import deploy_example, call_canister, parse_candid_text, EXAMPLES_DIR
import os

EXAMPLE = "init_and_post_upgrade_recovery"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    # Deploy with argument (false) so init succeeds
    example_dir = os.path.join(EXAMPLES_DIR, EXAMPLE)
    subprocess.run(
        ["dfx", "deploy", "init_and_post_upgrade_recovery", "--argument", "(false)"],
        cwd=example_dir,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    from .conftest import _get_canister_id
    cid = _get_canister_id(example_dir, "init_and_post_upgrade_recovery")
    assert cid, "Failed to deploy init_and_post_upgrade_recovery"
    return cid


def test_init_succeeded(canister):
    result = parse_candid_text(call_canister(canister, "get_message", example_dir=EXAMPLE_DIR))
    assert result == "init_"


def test_post_upgrade_succeeds(canister):
    subprocess.run(
        ["dfx", "deploy", "--upgrade-unchanged", "init_and_post_upgrade_recovery", "--argument", "(false)"],
        cwd=EXAMPLE_DIR,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    result = parse_candid_text(call_canister(canister, "get_message", example_dir=EXAMPLE_DIR))
    assert result == "post_upgrade_"
