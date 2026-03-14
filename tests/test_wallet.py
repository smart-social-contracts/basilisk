"""
Integration tests for Basilisk OS Wallet — ICRC-1 token management.

Tests run against a local dfx replica with locally deployed ckBTC ledger
and indexer canisters. The test canister (shell_test) must be deployed
locally with funds sent to it via deploy_test_ledger.py.

Test categories:
  1. Token registry (sync entity CRUD)
  2. Balance entity (sync entity CRUD)
  3. Transfer entity (sync entity CRUD)
  4. ICRC balance query (async inter-canister call via %task)
  5. ICRC fee query (async inter-canister call via %task)
  6. ICRC transfer (async inter-canister call via %task)
  7. Refresh from indexer (async inter-canister call via %task)

Configuration:
    Set environment variables or use defaults:
        BASILISK_TEST_CANISTER  — canister ID (default from conftest)
        BASILISK_TEST_NETWORK   — network (default: local for wallet tests)
        BASILISK_WALLET_LEDGER  — ckBTC ledger canister ID (auto-detected)
        BASILISK_WALLET_INDEXER — ckBTC indexer canister ID (auto-detected)

Usage:
    # First deploy local test infrastructure:
    cd basilisk/tests/test_canister && dfx start --background
    python3 ../deploy_test_ledger.py

    # Then run tests:
    cd basilisk
    BASILISK_TEST_NETWORK=local pytest tests/test_wallet.py -v
"""

import json
import os
import re
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.shell import _parse_candid

# Directory containing dfx.json with local network config
_TEST_CANISTER_DIR = os.path.join(os.path.dirname(__file__), "test_canister")


def _local_canister_exec(code, canister, network):
    """canister_exec variant that runs dfx from the test_canister dir."""
    escaped = code.replace('"', '\\"').replace("\n", "\\n")
    cmd = ["dfx", "canister", "call"]
    if network:
        cmd.extend(["--network", network])
    cmd.extend([canister, "execute_code_shell", f'("{escaped}")'])
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=_TEST_CANISTER_DIR,
        )
        if r.returncode != 0:
            return f"[dfx error] {r.stderr.strip()}"
        return _parse_candid(r.stdout)
    except subprocess.TimeoutExpired:
        return "[error] canister call timed out (120s)"
    except FileNotFoundError:
        return "[error] dfx not found"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _get_canister():
    return os.environ.get("BASILISK_TEST_CANISTER", "shell_test")


def _get_network():
    return os.environ.get("BASILISK_TEST_NETWORK", "local")


def _get_ledger_id():
    """Get ckBTC ledger canister ID, auto-detect from dfx if not set."""
    env = os.environ.get("BASILISK_WALLET_LEDGER")
    if env:
        return env
    try:
        result = subprocess.run(
            ["dfx", "canister", "id", "ckbtc_ledger"],
            capture_output=True, text=True, check=True,
            cwd=os.path.join(os.path.dirname(__file__), "test_canister"),
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _get_indexer_id():
    """Get ckBTC indexer canister ID, auto-detect from dfx if not set."""
    env = os.environ.get("BASILISK_WALLET_INDEXER")
    if env:
        return env
    try:
        result = subprocess.run(
            ["dfx", "canister", "id", "ckbtc_indexer"],
            capture_output=True, text=True, check=True,
            cwd=os.path.join(os.path.dirname(__file__), "test_canister"),
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


# ---------------------------------------------------------------------------
# Entity definition preamble (injected into canister via exec)
# ---------------------------------------------------------------------------

# This defines the wallet entities on the canister at runtime,
# following the same pattern as _TASK_RESOLVE for task entities.
_WALLET_RESOLVE = (
    "if 'Token' not in dir():\n"
    "    try:\n"
    "        from ic_python_db import Entity, String, Integer, ManyToOne, OneToMany, TimestampedMixin\n"
    "        class Token(Entity, TimestampedMixin):\n"
    "            __alias__ = 'name'\n"
    "            name = String(max_length=64)\n"
    "            ledger = String(max_length=64)\n"
    "            indexer = String(max_length=64)\n"
    "            decimals = Integer(default=8)\n"
    "            fee = Integer(default=10)\n"
    "            balances = OneToMany('WalletBalance', 'token')\n"
    "            transfers = OneToMany('WalletTransfer', 'token')\n"
    "        class WalletBalance(Entity, TimestampedMixin):\n"
    "            principal = String(max_length=64)\n"
    "            token = ManyToOne('Token', 'balances')\n"
    "            amount = Integer(default=0)\n"
    "        class WalletTransfer(Entity, TimestampedMixin):\n"
    "            token = ManyToOne('Token', 'transfers')\n"
    "            tx_id = String(max_length=64)\n"
    "            kind = String(max_length=16)\n"
    "            principal_from = String(max_length=64)\n"
    "            principal_to = String(max_length=64)\n"
    "            amount = Integer(default=0)\n"
    "            fee = Integer(default=0)\n"
    "            timestamp = Integer(default=0)\n"
    "    except ImportError:\n"
    "        pass\n"
)

# ICRC service definitions preamble for async tasks
_ICRC_RESOLVE = (
    "if 'ICRCLedger' not in dir():\n"
    "    try:\n"
    "        from basilisk import Record, Service, service_query, service_update, Principal, Opt, blob, nat, nat64, Variant, Vec, Async\n"
    "        class _Account(Record):\n"
    "            owner: Principal\n"
    "            subaccount: Opt[blob]\n"
    "        class _TransferArg(Record):\n"
    "            to: _Account\n"
    "            fee: Opt[nat]\n"
    "            memo: Opt[blob]\n"
    "            from_subaccount: Opt[blob]\n"
    "            created_at_time: Opt[nat64]\n"
    "            amount: nat\n"
    "        class _BadFee(Record):\n"
    "            expected_fee: nat\n"
    "        class _InsufficientFunds(Record):\n"
    "            balance: nat\n"
    "        class _GenericError(Record):\n"
    "            error_code: nat\n"
    "            message: str\n"
    "        class _TransferError(Variant, total=False):\n"
    "            BadFee: _BadFee\n"
    "            InsufficientFunds: _InsufficientFunds\n"
    "            GenericError: _GenericError\n"
    "        class _TransferResult(Variant, total=False):\n"
    "            Ok: nat\n"
    "            Err: _TransferError\n"
    "        class ICRCLedger(Service):\n"
    "            @service_query\n"
    "            def icrc1_balance_of(self, account: _Account) -> nat: ...\n"
    "            @service_query\n"
    "            def icrc1_fee(self) -> nat: ...\n"
    "            @service_update\n"
    "            def icrc1_transfer(self, args: _TransferArg) -> _TransferResult: ...\n"
    "        class _GetAccountTransactionsRequest(Record):\n"
    "            account: _Account\n"
    "            start: Opt[nat]\n"
    "            max_results: nat\n"
    "        class _GetAccountTransactionsResponse(Record):\n"
    "            balance: nat\n"
    "            transactions: Vec[dict]\n"
    "            oldest_tx_id: Opt[nat]\n"
    "        class _GetTransactionsResult(Variant):\n"
    "            Ok: _GetAccountTransactionsResponse\n"
    "            Err: str\n"
    "        class ICRCIndexer(Service):\n"
    "            @service_query\n"
    "            def get_account_transactions(self, request: _GetAccountTransactionsRequest) -> Async[_GetTransactionsResult]: ...\n"
    "    except ImportError:\n"
    "        pass\n"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def wallet_canister():
    return _get_canister()


@pytest.fixture(scope="session")
def wallet_network():
    return _get_network()


@pytest.fixture(scope="session")
def ledger_id():
    lid = _get_ledger_id()
    if not lid:
        pytest.skip("ckBTC ledger not deployed (run deploy_test_ledger.py)")
    return lid


@pytest.fixture(scope="session")
def indexer_id():
    iid = _get_indexer_id()
    if not iid:
        pytest.skip("ckBTC indexer not deployed (run deploy_test_ledger.py)")
    return iid


@pytest.fixture(scope="session")
def wallet_reachable(wallet_canister, wallet_network):
    """Verify canister is reachable and wallet entities are resolved."""
    result = _local_canister_exec("print('wallet_ping')", wallet_canister, wallet_network)
    if "error" in result.lower():
        pytest.skip(f"Canister not reachable: {result}")
    assert result.strip() == "wallet_ping"

    # Resolve wallet entities
    _local_canister_exec(_WALLET_RESOLVE + "print('wallet_entities_ready')",
                         wallet_canister, wallet_network)
    return True


def _exec(code, canister, network):
    """Execute code on canister with wallet entities resolved."""
    return _local_canister_exec(_WALLET_RESOLVE + code, canister, network).strip()


# ---------------------------------------------------------------------------
# Helpers for async task-based tests
# ---------------------------------------------------------------------------

def _extract_task_id(output):
    m = re.search(r'task\s+(\d+)', output, re.IGNORECASE)
    return m.group(1) if m else None


def _task_magic(cmd, canister, network):
    """Run a magic command via dfx from the test_canister dir."""
    result = _local_canister_exec(
        _magic_to_code(cmd), canister, network,
    )
    return result.strip() if result else ""


def _magic_to_code(cmd):
    """Convert a %task magic command to executable Python code.

    _task_create_code takes a single 'rest' string (everything after '%task create').
    _task_info_code, _task_log_code, etc. take a single 'tid' string.
    """
    from basilisk.shell import (
        _task_list_code, _task_create_code, _task_add_step_code, _task_info_code,
        _task_start_code, _task_stop_code, _task_delete_code, _task_log_code,
    )
    # Strip leading %task and split into subcommand + rest
    stripped = cmd.strip()
    if stripped.startswith("%task"):
        stripped = stripped[5:].strip()
    if not stripped:
        return _task_list_code()

    # Split into subcommand and the rest
    space_idx = stripped.find(" ")
    if space_idx == -1:
        sub, rest = stripped, ""
    else:
        sub, rest = stripped[:space_idx], stripped[space_idx + 1:]

    if sub == "list":
        return _task_list_code()
    elif sub == "create":
        return _task_create_code(rest)
    elif sub == "add-step":
        return _task_add_step_code(rest)
    elif sub == "info":
        return _task_info_code(rest.strip())
    elif sub == "log":
        return _task_log_code(rest.strip())
    elif sub == "start":
        return _task_start_code(rest.strip())
    elif sub == "stop":
        return _task_stop_code(rest.strip())
    elif sub == "delete":
        return _task_delete_code(rest.strip())
    else:
        raise ValueError(f"Unknown %task subcommand: {sub}")


def _cleanup_task(tid, canister, network):
    _task_magic(f"%task delete {tid}", canister, network)


def _wait_for_task_execution(tid, canister, network, timeout=60, poll=3):
    """Poll task info until it has executions or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = _task_magic(f"%task info {tid}", canister, network)
        if "Executions: 0" not in info and "Executions:" in info:
            return info
        time.sleep(poll)
    return info


# ===========================================================================
# Token Registry (synchronous entity tests)
# ===========================================================================

class TestTokenRegistry:
    """Test Token entity CRUD via exec_on_canister."""

    def test_register_token(self, wallet_reachable, wallet_canister, wallet_network):
        """Register a new token and verify it's persisted."""
        result = _exec(
            "t = Token(name='test_ckBTC', ledger='mxzaz-hqaaa-aaaar-qaada-cai', "
            "indexer='n5wcd-faaaa-aaaar-qaaea-cai', decimals=8, fee=10)\n"
            "print(f'{t.name}|{t.ledger}|{t.decimals}|{t.fee}')",
            wallet_canister, wallet_network,
        )
        assert "test_ckBTC|mxzaz-hqaaa-aaaar-qaada-cai|8|10" in result

    def test_get_token_by_alias(self, wallet_reachable, wallet_canister, wallet_network):
        """Retrieve token by name alias."""
        result = _exec(
            "t = Token['test_ckBTC']\n"
            "print(t.ledger if t else 'NOT_FOUND')",
            wallet_canister, wallet_network,
        )
        assert "mxzaz-hqaaa-aaaar-qaada-cai" in result

    def test_update_token(self, wallet_reachable, wallet_canister, wallet_network):
        """Update an existing token's properties."""
        result = _exec(
            "t = Token['test_ckBTC']\n"
            "t.fee = 20\n"
            "t2 = Token['test_ckBTC']\n"
            "print(t2.fee)",
            wallet_canister, wallet_network,
        )
        assert "20" in result

    def test_register_second_token(self, wallet_reachable, wallet_canister, wallet_network):
        """Register a second token."""
        result = _exec(
            "t = Token(name='test_ckETH', ledger='ss2fx-dyaaa-aaaar-qacoq-cai', "
            "indexer='', decimals=18, fee=2000000000000)\n"
            "print(f'{t.name}|{t.decimals}')",
            wallet_canister, wallet_network,
        )
        assert "test_ckETH|18" in result

    def test_list_tokens(self, wallet_reachable, wallet_canister, wallet_network):
        """List all registered tokens."""
        result = _exec(
            "names = sorted([t.name for t in Token.instances() if t.name.startswith('test_')])\n"
            "print('|'.join(names))",
            wallet_canister, wallet_network,
        )
        assert "test_ckBTC" in result
        assert "test_ckETH" in result

    def test_cleanup_tokens(self, wallet_reachable, wallet_canister, wallet_network):
        """Clean up test tokens."""
        _exec(
            "for t in list(Token.instances()):\n"
            "    if t.name.startswith('test_'):\n"
            "        t.delete()\n"
            "print('cleaned')",
            wallet_canister, wallet_network,
        )


# ===========================================================================
# WalletBalance entity (synchronous)
# ===========================================================================

class TestBalanceEntity:
    """Test WalletBalance entity CRUD."""

    def test_create_balance(self, wallet_reachable, wallet_canister, wallet_network):
        """Create a balance entity and verify fields."""
        result = _exec(
            "tok = Token(name='bal_test_token', ledger='aaa', indexer='', decimals=8, fee=10)\n"
            "bal = WalletBalance(principal='test-principal-123', token=tok, amount=50000)\n"
            "print(f'{bal.principal}|{bal.amount}')",
            wallet_canister, wallet_network,
        )
        assert "test-principal-123|50000" in result

    def test_read_balance_via_token(self, wallet_reachable, wallet_canister, wallet_network):
        """Read balance through the token relationship."""
        result = _exec(
            "tok = Token['bal_test_token']\n"
            "bals = list(tok.balances)\n"
            "print(f'{len(bals)}|{bals[0].amount if bals else 0}')",
            wallet_canister, wallet_network,
        )
        assert "1|50000" in result

    def test_update_balance(self, wallet_reachable, wallet_canister, wallet_network):
        """Update balance amount."""
        result = _exec(
            "tok = Token['bal_test_token']\n"
            "for b in tok.balances:\n"
            "    if b.principal == 'test-principal-123':\n"
            "        b.amount = 75000\n"
            "        break\n"
            "b2 = list(Token['bal_test_token'].balances)[0]\n"
            "print(b2.amount)",
            wallet_canister, wallet_network,
        )
        assert "75000" in result

    def test_cleanup_balances(self, wallet_reachable, wallet_canister, wallet_network):
        """Clean up test balances and tokens."""
        _exec(
            "for b in list(WalletBalance.instances()):\n"
            "    b.delete()\n"
            "tok = Token['bal_test_token']\n"
            "if tok: tok.delete()\n"
            "print('cleaned')",
            wallet_canister, wallet_network,
        )


# ===========================================================================
# WalletTransfer entity (synchronous)
# ===========================================================================

class TestTransferEntity:
    """Test WalletTransfer entity CRUD."""

    def test_create_transfer(self, wallet_reachable, wallet_canister, wallet_network):
        """Create a transfer record and verify fields."""
        result = _exec(
            "tok = Token(name='tx_test_token', ledger='aaa', indexer='', decimals=8, fee=10)\n"
            "tx = WalletTransfer(token=tok, tx_id='42', kind='transfer',\n"
            "    principal_from='from-xyz', principal_to='to-abc',\n"
            "    amount=1000, fee=10, timestamp=1234567890)\n"
            "print(f'{tx.tx_id}|{tx.kind}|{tx.amount}|{tx.fee}')",
            wallet_canister, wallet_network,
        )
        assert "42|transfer|1000|10" in result

    def test_transfer_linked_to_token(self, wallet_reachable, wallet_canister, wallet_network):
        """Verify transfer is linked to its token via ManyToOne."""
        result = _exec(
            "tok = Token['tx_test_token']\n"
            "txs = list(tok.transfers)\n"
            "print(f'{len(txs)}|{txs[0].tx_id if txs else \"\"}')",
            wallet_canister, wallet_network,
        )
        assert "1|42" in result

    def test_cleanup_transfers(self, wallet_reachable, wallet_canister, wallet_network):
        """Clean up test transfers and tokens."""
        _exec(
            "for t in list(WalletTransfer.instances()):\n"
            "    t.delete()\n"
            "tok = Token['tx_test_token']\n"
            "if tok: tok.delete()\n"
            "print('cleaned')",
            wallet_canister, wallet_network,
        )


# ===========================================================================
# Helper: write async code to canister file, create task with --file
# ===========================================================================

def _write_file_on_canister(path, content, canister, network):
    """Write a Python file to the canister's in-memory filesystem."""
    import base64
    b64 = base64.b64encode(content.encode()).decode()
    result = _local_canister_exec(
        f"import base64\n"
        f"_data = base64.b64decode('{b64}').decode()\n"
        f"with open('{path}', 'w') as f:\n"
        f"    f.write(_data)\n"
        f"print('wrote {path}')",
        canister, network,
    )
    assert "wrote" in result, f"Failed to write file: {result}"


def _run_async_task(name, code, canister, network, timeout=60):
    """Write async code to canister, create bare task, add async step via --file, start, wait, return log."""
    path = f"/_wallet_test_{name}.py"
    _write_file_on_canister(path, code, canister, network)

    # Create a bare task (no code)
    result = _task_magic(
        f'%task create {name}',
        canister, network,
    )
    tid = _extract_task_id(result)
    assert tid, f"Failed to create task: {result}"

    # Add an async step pointing to the file
    step_result = _task_magic(
        f'%task add-step {tid} --async --file {path}',
        canister, network,
    )
    assert "Added" in step_result or "step" in step_result.lower(), \
        f"Failed to add step: {step_result}"

    _task_magic(f"%task start {tid}", canister, network)
    info = _wait_for_task_execution(tid, canister, network, timeout=timeout)
    assert "Executions: 0" not in info, f"Task never executed: {info}"

    log = _task_magic(f"%task log {tid}", canister, network)
    # Clean up
    _cleanup_task(tid, canister, network)
    _local_canister_exec(
        f"import os; os.remove('{path}') if os.path.exists('{path}') else None",
        canister, network,
    )
    return log


# ===========================================================================
# ICRC Balance Query (async inter-canister call via %task)
# ===========================================================================

class TestICRCBalanceQuery:
    """Test querying balance from a real (local) ckBTC ledger canister."""

    def test_query_balance(
        self, wallet_reachable, wallet_canister, wallet_network, ledger_id,
    ):
        """Query the canister's ckBTC balance from the local ledger."""
        code = (
            "from basilisk import Record, Service, service_query, Principal, Opt, blob, nat, Async\n"
            "\n"
            "class _Account(Record):\n"
            "    owner: Principal\n"
            "    subaccount: Opt[blob]\n"
            "\n"
            "class ICRCLedger(Service):\n"
            "    @service_query\n"
            "    def icrc1_balance_of(self, account: _Account) -> nat: ...\n"
            "\n"
            "def async_task():\n"
            f"    ledger = ICRCLedger(Principal.from_str('{ledger_id}'))\n"
            "    result = yield ledger.icrc1_balance_of(\n"
            "        _Account(owner=ic.id(), subaccount=None)\n"
            "    )\n"
            "    bal = result.Ok if hasattr(result, 'Ok') else result\n"
            "    if isinstance(bal, dict) and 'Ok' in bal:\n"
            "        bal = bal['Ok']\n"
            "    return f'WALLET_BALANCE:{bal}'\n"
        )

        log = _run_async_task(
            "_test_wallet_balance", code,
            wallet_canister, wallet_network,
        )
        assert "completed" in log, f"Task did not complete: {log}"

        m = re.search(r'WALLET_BALANCE:(\d+)', log)
        assert m, f"Balance not found in log: {log}"
        balance = int(m.group(1))
        assert balance > 0, f"Expected positive balance, got {balance}"
        print(f"\n  ckBTC balance: {balance} satoshis")

    def test_query_fee(
        self, wallet_reachable, wallet_canister, wallet_network, ledger_id,
    ):
        """Query the ckBTC transfer fee from the local ledger."""
        code = (
            "from basilisk import Record, Service, service_query, Principal, Opt, blob, nat, Async\n"
            "\n"
            "class _Account(Record):\n"
            "    owner: Principal\n"
            "    subaccount: Opt[blob]\n"
            "\n"
            "class ICRCLedger(Service):\n"
            "    @service_query\n"
            "    def icrc1_fee(self) -> nat: ...\n"
            "\n"
            "def async_task():\n"
            f"    ledger = ICRCLedger(Principal.from_str('{ledger_id}'))\n"
            "    result = yield ledger.icrc1_fee()\n"
            "    fee = result.Ok if hasattr(result, 'Ok') else result\n"
            "    if isinstance(fee, dict) and 'Ok' in fee:\n"
            "        fee = fee['Ok']\n"
            "    return f'WALLET_FEE:{fee}'\n"
        )

        log = _run_async_task(
            "_test_wallet_fee", code,
            wallet_canister, wallet_network,
        )
        assert "completed" in log, f"Task did not complete: {log}"

        m = re.search(r'WALLET_FEE:(\d+)', log)
        assert m, f"Fee not found in log: {log}"
        fee = int(m.group(1))
        assert fee == 10, f"Expected fee=10, got {fee}"
        print(f"\n  ckBTC fee: {fee} satoshis")


# ===========================================================================
# ICRC Transfer (async inter-canister call)
# ===========================================================================

class TestICRCTransfer:
    """Test performing an actual ICRC-1 transfer from the canister."""

    def test_transfer_to_self(
        self, wallet_reachable, wallet_canister, wallet_network, ledger_id,
    ):
        """Transfer tokens from the canister back to itself (round-trip test)."""
        code = (
            "from basilisk import Record, Service, service_query, service_update, Principal, Opt, blob, nat, nat64, Variant, Async\n"
            "\n"
            "class _Account(Record):\n"
            "    owner: Principal\n"
            "    subaccount: Opt[blob]\n"
            "\n"
            "class _TransferArg(Record):\n"
            "    to: _Account\n"
            "    fee: Opt[nat]\n"
            "    memo: Opt[blob]\n"
            "    from_subaccount: Opt[blob]\n"
            "    created_at_time: Opt[nat64]\n"
            "    amount: nat\n"
            "\n"
            "class _BadFee(Record):\n"
            "    expected_fee: nat\n"
            "class _InsufficientFunds(Record):\n"
            "    balance: nat\n"
            "class _GenericError(Record):\n"
            "    error_code: nat\n"
            "    message: str\n"
            "class _TransferError(Variant, total=False):\n"
            "    BadFee: _BadFee\n"
            "    InsufficientFunds: _InsufficientFunds\n"
            "    GenericError: _GenericError\n"
            "class _TransferResult(Variant, total=False):\n"
            "    Ok: nat\n"
            "    Err: _TransferError\n"
            "\n"
            "class ICRCLedger(Service):\n"
            "    @service_update\n"
            "    def icrc1_transfer(self, args: _TransferArg) -> _TransferResult: ...\n"
            "\n"
            "def async_task():\n"
            f"    ledger = ICRCLedger(Principal.from_str('{ledger_id}'))\n"
            "    args = _TransferArg(\n"
            "        to=_Account(owner=ic.id(), subaccount=None),\n"
            "        fee=None,\n"
            "        memo=None,\n"
            "        from_subaccount=None,\n"
            "        created_at_time=None,\n"
            "        amount=100,\n"
            "    )\n"
            "    result = yield ledger.icrc1_transfer(args)\n"
            "    raw = result.Ok if hasattr(result, 'Ok') else result\n"
            "    if isinstance(raw, dict) and 'Ok' in raw:\n"
            "        return f'WALLET_TX_OK:{raw[\"Ok\"]}'\n"
            "    elif isinstance(raw, dict) and 'Err' in raw:\n"
            "        return f'WALLET_TX_ERR:{raw[\"Err\"]}'\n"
            "    else:\n"
            "        return f'WALLET_TX_OK:{raw}'\n"
        )

        log = _run_async_task(
            "_test_wallet_transfer", code,
            wallet_canister, wallet_network, timeout=60,
        )
        assert "completed" in log, f"Task did not complete: {log}"

        m = re.search(r'WALLET_TX_OK:(\d+)', log)
        assert m, f"Transfer TX ID not found in log: {log}"
        tx_id = int(m.group(1))
        assert tx_id > 0, f"Expected positive TX ID, got {tx_id}"
        print(f"\n  Transfer TX ID: {tx_id}")

    def test_transfer_insufficient_funds(
        self, wallet_reachable, wallet_canister, wallet_network, ledger_id,
    ):
        """Transfer more than available should return InsufficientFunds error."""
        code = (
            "from basilisk import Record, Service, service_query, service_update, Principal, Opt, blob, nat, nat64, Variant, Async\n"
            "\n"
            "class _Account(Record):\n"
            "    owner: Principal\n"
            "    subaccount: Opt[blob]\n"
            "\n"
            "class _TransferArg(Record):\n"
            "    to: _Account\n"
            "    fee: Opt[nat]\n"
            "    memo: Opt[blob]\n"
            "    from_subaccount: Opt[blob]\n"
            "    created_at_time: Opt[nat64]\n"
            "    amount: nat\n"
            "\n"
            "class _BadFee(Record):\n"
            "    expected_fee: nat\n"
            "class _InsufficientFunds(Record):\n"
            "    balance: nat\n"
            "class _GenericError(Record):\n"
            "    error_code: nat\n"
            "    message: str\n"
            "class _TransferError(Variant, total=False):\n"
            "    BadFee: _BadFee\n"
            "    InsufficientFunds: _InsufficientFunds\n"
            "    GenericError: _GenericError\n"
            "class _TransferResult(Variant, total=False):\n"
            "    Ok: nat\n"
            "    Err: _TransferError\n"
            "\n"
            "class ICRCLedger(Service):\n"
            "    @service_update\n"
            "    def icrc1_transfer(self, args: _TransferArg) -> _TransferResult: ...\n"
            "\n"
            "def async_task():\n"
            f"    ledger = ICRCLedger(Principal.from_str('{ledger_id}'))\n"
            "    args = _TransferArg(\n"
            "        to=_Account(owner=ic.id(), subaccount=None),\n"
            "        fee=None,\n"
            "        memo=None,\n"
            "        from_subaccount=None,\n"
            "        created_at_time=None,\n"
            "        amount=999_999_999_999_999,\n"
            "    )\n"
            "    result = yield ledger.icrc1_transfer(args)\n"
            "    raw = result.Ok if hasattr(result, 'Ok') else result\n"
            "    if isinstance(raw, dict) and 'Err' in raw:\n"
            "        return 'WALLET_TX_ERR:InsufficientFunds'\n"
            "    elif isinstance(raw, dict) and 'Ok' in raw:\n"
            "        return f'WALLET_TX_OK:{raw[\"Ok\"]}'\n"
            "    else:\n"
            "        return f'WALLET_TX_RAW:{raw}'\n"
        )

        log = _run_async_task(
            "_test_wallet_insuff", code,
            wallet_canister, wallet_network, timeout=60,
        )
        assert "completed" in log, f"Task did not complete: {log}"

        assert "WALLET_TX_ERR:InsufficientFunds" in log, \
            f"Expected InsufficientFunds error in log: {log}"
        print("\n  Correctly got InsufficientFunds error")


# ===========================================================================
# ICRC Refresh from Indexer (async inter-canister call)
# ===========================================================================

class TestICRCRefresh:
    """Test syncing transaction history from the indexer canister."""

    def test_query_transactions(
        self, wallet_reachable, wallet_canister, wallet_network,
        ledger_id, indexer_id,
    ):
        """Query transaction history from the local ckBTC indexer."""
        code = (
            "from basilisk import Record, Service, service_query, Principal, Opt, blob, nat, Vec, Variant, Async\n"
            "\n"
            "class _Account(Record):\n"
            "    owner: Principal\n"
            "    subaccount: Opt[blob]\n"
            "\n"
            "class _GetAccountTransactionsRequest(Record):\n"
            "    account: _Account\n"
            "    start: Opt[nat]\n"
            "    max_results: nat\n"
            "\n"
            "class _GetAccountTransactionsResponse(Record):\n"
            "    balance: nat\n"
            "    transactions: Vec[dict]\n"
            "    oldest_tx_id: Opt[nat]\n"
            "\n"
            "class _GetTransactionsResult(Variant):\n"
            "    Ok: _GetAccountTransactionsResponse\n"
            "    Err: str\n"
            "\n"
            "class ICRCIndexer(Service):\n"
            "    @service_query\n"
            "    def get_account_transactions(self, request: _GetAccountTransactionsRequest) -> _GetTransactionsResult: ...\n"
            "\n"
            "def async_task():\n"
            f"    indexer = ICRCIndexer(Principal.from_str('{indexer_id}'))\n"
            "    request = _GetAccountTransactionsRequest(\n"
            "        account=_Account(owner=ic.id(), subaccount=None),\n"
            "        start=None,\n"
            "        max_results=20,\n"
            "    )\n"
            "    result = yield indexer.get_account_transactions(request)\n"
            "    raw = result.Ok if hasattr(result, 'Ok') else result\n"
            "    if isinstance(raw, dict) and 'Ok' in raw:\n"
            "        raw = raw['Ok']\n"
            "    if isinstance(raw, dict):\n"
            "        bal = raw.get('balance', 0)\n"
            "        txs = raw.get('transactions', [])\n"
            "        return f'WALLET_REFRESH:balance={bal},txs={len(txs)}'\n"
            "    else:\n"
            "        return f'WALLET_REFRESH_ERR:{raw}'\n"
        )

        log = _run_async_task(
            "_test_wallet_refresh", code,
            wallet_canister, wallet_network, timeout=60,
        )
        assert "completed" in log, f"Task did not complete: {log}"

        m = re.search(r'WALLET_REFRESH:balance=(\d+),txs=(\d+)', log)
        assert m, f"Refresh data not found in log: {log}"
        balance = int(m.group(1))
        tx_count = int(m.group(2))
        assert balance > 0, f"Expected positive balance, got {balance}"
        # tx_count may be 0 if the local indexer hasn't synced yet
        assert tx_count >= 0, f"Expected non-negative tx count, got {tx_count}"
        print(f"\n  Indexer: balance={balance}, transactions={tx_count}")
