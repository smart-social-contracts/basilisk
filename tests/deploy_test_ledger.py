#!/usr/bin/env python3
"""
Deploy local ckBTC ledger and indexer for Basilisk wallet integration tests.

This script:
1. Starts dfx (if not running)
2. Creates and deploys ckBTC ledger with initial balance
3. Creates and deploys ckBTC indexer
4. Sends test tokens to the shell_test canister
5. Verifies setup

Usage:
    cd basilisk/tests/test_canister
    python3 ../deploy_test_ledger.py

Requires: dfx installed and shell_test canister deployed locally.
"""

import json
import os
import subprocess
import sys
import time


def run_command(cmd, capture_output=True, check=True):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            cmd, capture_output=capture_output, text=True, check=check,
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(cmd)}")
        print(f"stderr: {e.stderr}")
        raise


def get_principal():
    """Get the current dfx identity principal."""
    result = run_command(["dfx", "identity", "get-principal"])
    return result.stdout.strip()


def get_canister_id(name):
    """Get canister ID by name."""
    result = run_command(["dfx", "canister", "id", name])
    return result.stdout.strip()


def deploy_ledger(principal):
    """Deploy ckBTC ledger with initial balance for the principal."""
    print("\n[1/5] Deploying ckbtc_ledger...")

    init_arg = (
        "(variant { Init = record { "
        'minting_account = record { owner = principal "aaaaa-aa"; subaccount = null }; '
        "transfer_fee = 10; "
        'token_symbol = "ckBTC"; '
        'token_name = "ckBTC Test"; '
        "decimals = opt 8; "
        "metadata = vec {}; "
        f'initial_balances = vec {{ record {{ record {{ owner = principal "{principal}"; subaccount = null }}; 10_000_000_000 }} }}; '
        "feature_flags = opt record { icrc2 = true }; "
        f'archive_options = record {{ num_blocks_to_archive = 1000; trigger_threshold = 2000; controller_id = principal "{principal}" }} '
        "} })"
    )

    run_command(
        ["dfx", "deploy", "ckbtc_ledger", "--no-wallet", "--yes",
         f"--argument={init_arg}"],
        capture_output=False,
    )

    ledger_id = get_canister_id("ckbtc_ledger")
    print(f"  Ledger canister ID: {ledger_id}")
    return ledger_id


def deploy_indexer(ledger_id):
    """Deploy ckBTC indexer pointing at the local ledger."""
    print("\n[2/5] Deploying ckbtc_indexer...")

    init_arg = (
        f"(opt variant {{ Init = record {{ "
        f'ledger_id = principal "{ledger_id}"; '
        f"retrieve_blocks_from_ledger_interval_seconds = opt 1 "
        f"}} }})"
    )

    run_command(
        ["dfx", "deploy", "ckbtc_indexer", "--no-wallet",
         f"--argument={init_arg}"],
        capture_output=False,
    )

    indexer_id = get_canister_id("ckbtc_indexer")
    print(f"  Indexer canister ID: {indexer_id}")
    return indexer_id


def send_tokens(ledger_id, to_principal, amount):
    """Send ICRC-1 tokens to a principal. Returns tx ID."""
    transfer_arg = (
        f"(record {{"
        f"  to = record {{"
        f'    owner = principal "{to_principal}";'
        f"    subaccount = null;"
        f"  }};"
        f"  amount = {amount};"
        f"  fee = null;"
        f"  memo = null;"
        f"  from_subaccount = null;"
        f"  created_at_time = null;"
        f"}})"
    )

    result = run_command([
        "dfx", "canister", "call", "--output", "json",
        ledger_id, "icrc1_transfer", transfer_arg,
    ])

    data = json.loads(result.stdout)
    if "Ok" in data:
        return int(data["Ok"])
    else:
        print(f"  Transfer failed: {data}")
        sys.exit(1)


def check_balance(ledger_id, principal):
    """Check ICRC-1 balance for a principal."""
    balance_arg = (
        f"(record {{"
        f'  owner = principal "{principal}";'
        f"  subaccount = null;"
        f"}})"
    )
    result = run_command([
        "dfx", "canister", "call", "--output", "json",
        ledger_id, "icrc1_balance_of", balance_arg,
    ])
    balance_str = result.stdout.strip().strip('"')
    return int(balance_str.replace("_", ""))


def main():
    print("=" * 60)
    print("Basilisk Wallet Test — Deploy Local ckBTC Ledger + Indexer")
    print("=" * 60)

    principal = get_principal()
    print(f"Identity principal: {principal}")

    # Create all canisters
    print("\n[0/5] Creating canisters...")
    run_command(
        ["dfx", "canister", "create", "--all", "--no-wallet"],
        capture_output=False, check=False,
    )

    # Deploy ledger & indexer
    ledger_id = deploy_ledger(principal)
    indexer_id = deploy_indexer(ledger_id)

    # Wait for indexer init
    print("\n  Waiting 3s for indexer to initialize...")
    time.sleep(3)

    # Get shell_test canister ID
    print("\n[3/5] Getting shell_test canister ID...")
    try:
        shell_test_id = get_canister_id("shell_test")
        print(f"  shell_test canister ID: {shell_test_id}")
    except subprocess.CalledProcessError:
        print("  shell_test not deployed locally. Skipping token transfer.")
        print(f"\nDone. Ledger={ledger_id}, Indexer={indexer_id}")
        return ledger_id, indexer_id

    # Send test tokens to shell_test canister
    print(f"\n[4/5] Sending 100,000 test satoshis to shell_test...")
    tx_id = send_tokens(ledger_id, shell_test_id, 100_000)
    print(f"  Transfer TX ID: {tx_id}")

    # Send a few more small transactions for testing
    for i in range(1, 6):
        tx = send_tokens(ledger_id, shell_test_id, i * 100)
        print(f"  Additional TX: {i * 100} satoshis (TX ID: {tx})")
        time.sleep(0.5)

    # Wait for indexer to catch up
    print("\n  Waiting 3s for indexer to sync...")
    time.sleep(3)

    # Verify
    print(f"\n[5/5] Verifying...")
    balance = check_balance(ledger_id, shell_test_id)
    print(f"  shell_test balance: {balance:,} satoshis")

    print("\n" + "=" * 60)
    print("Setup complete!")
    print(f"  ckbtc_ledger:  {ledger_id}")
    print(f"  ckbtc_indexer: {indexer_id}")
    print(f"  shell_test:    {shell_test_id}")
    print(f"  Balance:       {balance:,} satoshis")
    print("=" * 60)

    return ledger_id, indexer_id


if __name__ == "__main__":
    main()
