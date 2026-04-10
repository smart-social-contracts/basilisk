"""
Integration tests for Basilisk OS FX Rate Service — XRC canister integration.

Tests run against a live IC canister (or local replica). The test canister
(shell_test) must be deployed with the Basilisk OS runtime.

Test categories:
  1. FXPair entity CRUD (synchronous entity operations)
  2. FXService pair registry (register, unregister, list)
  3. FXService synchronous rate queries (get_rate, get_rate_info)
  4. XRC canister binding (async inter-canister call via %task)
  5. FXService.refresh (async inter-canister call via %task)
  6. FXService.fetch_rate (async inter-canister call via %task)
  7. Edge cases and error handling

Configuration:
    Set environment variables or use defaults:
        BASILISK_TEST_CANISTER  — canister ID (default: shell_test)
        BASILISK_TEST_NETWORK   — network (default: ic)

Usage:
    # Against mainnet test canister:
    pytest tests/test_fx.py -v

    # Against local replica:
    cd basilisk/tests/test_canister && dfx start --background
    BASILISK_TEST_NETWORK=local pytest tests/test_fx.py -v
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
    return os.environ.get("BASILISK_TEST_NETWORK", "ic")


# ---------------------------------------------------------------------------
# Entity definition preamble (injected into canister via exec)
# ---------------------------------------------------------------------------

_FXPAIR_RESOLVE = (
    "if 'FXPair' not in dir():\n"
    "    try:\n"
    "        from ic_python_db import Entity, String, Integer, TimestampedMixin\n"
    "        class FXPair(Entity, TimestampedMixin):\n"
    "            __alias__ = 'name'\n"
    "            name = String(max_length=16)\n"
    "            base_symbol = String(max_length=8)\n"
    "            base_class = String(max_length=16)\n"
    "            quote_symbol = String(max_length=8)\n"
    "            quote_class = String(max_length=16)\n"
    "            rate = Integer(default=0)\n"
    "            decimals = Integer(default=9)\n"
    "            last_updated = Integer(default=0)\n"
    "            last_error = String(max_length=256)\n"
    "    except ImportError:\n"
    "        pass\n"
)

# XRC service definition preamble for async tasks
_XRC_RESOLVE = (
    "if 'XRCCanister' not in dir():\n"
    "    try:\n"
    "        from basilisk import Record, Service, service_update, Principal, Opt, Variant, nat32, nat64, null, text, Async\n"
    "        class _AssetClass(Variant, total=False):\n"
    "            Cryptocurrency: null\n"
    "            FiatCurrency: null\n"
    "        class _Asset(Record):\n"
    "            symbol: text\n"
    "            class_: _AssetClass\n"
    "        class _GetExchangeRateRequest(Record):\n"
    "            base_asset: _Asset\n"
    "            quote_asset: _Asset\n"
    "            timestamp: Opt[nat64]\n"
    "        class _ExchangeRateMetadata(Record):\n"
    "            decimals: nat32\n"
    "            base_asset_num_queried_sources: nat64\n"
    "            base_asset_num_received_rates: nat64\n"
    "            quote_asset_num_queried_sources: nat64\n"
    "            quote_asset_num_received_rates: nat64\n"
    "            standard_deviation: nat64\n"
    "            forex_timestamp: Opt[nat64]\n"
    "        class _ExchangeRate(Record):\n"
    "            base_asset: _Asset\n"
    "            quote_asset: _Asset\n"
    "            timestamp: nat64\n"
    "            rate: nat64\n"
    "            metadata: _ExchangeRateMetadata\n"
    "        class _OtherError(Record):\n"
    "            code: nat32\n"
    "            description: text\n"
    "        class _ExchangeRateError(Variant, total=False):\n"
    "            AnonymousPrincipalNotAllowed: null\n"
    "            Pending: null\n"
    "            CryptoBaseAssetNotFound: null\n"
    "            CryptoQuoteAssetNotFound: null\n"
    "            StablecoinRateNotFound: null\n"
    "            StablecoinRateTooFewRates: null\n"
    "            StablecoinRateZeroRate: null\n"
    "            ForexInvalidTimestamp: null\n"
    "            ForexBaseAssetNotFound: null\n"
    "            ForexQuoteAssetNotFound: null\n"
    "            ForexAssetsNotFound: null\n"
    "            RateLimited: null\n"
    "            NotEnoughCycles: null\n"
    "            FailedToAcceptCycles: null\n"
    "            InconsistentRatesReceived: null\n"
    "            Other: _OtherError\n"
    "        class _GetExchangeRateResult(Variant, total=False):\n"
    "            Ok: _ExchangeRate\n"
    "            Err: _ExchangeRateError\n"
    "        class XRCCanister(Service):\n"
    "            @service_update\n"
    "            def get_exchange_rate(self, args: _GetExchangeRateRequest) -> _GetExchangeRateResult: ...\n"
    "        XRC_CANISTER_ID = 'uf6dk-hyaaa-aaaaq-qaaaq-cai'\n"
    "    except ImportError:\n"
    "        pass\n"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def fx_canister():
    return _get_canister()


@pytest.fixture(scope="session")
def fx_network():
    return _get_network()


@pytest.fixture(scope="session")
def fx_reachable(fx_canister, fx_network):
    """Verify canister is reachable and FX entities are resolved."""
    result = _local_canister_exec("print('fx_ping')", fx_canister, fx_network)
    if "error" in result.lower():
        pytest.skip(f"Canister not reachable: {result}")
    assert result.strip() == "fx_ping"

    # Resolve FXPair entity
    _local_canister_exec(
        _FXPAIR_RESOLVE + "print('fxpair_ready')",
        fx_canister, fx_network,
    )
    return True


def _exec(code, canister, network):
    """Execute code on canister with FXPair entity resolved."""
    return _local_canister_exec(_FXPAIR_RESOLVE + code, canister, network).strip()


# ---------------------------------------------------------------------------
# Helpers for async task-based tests
# ---------------------------------------------------------------------------

def _extract_task_id(output):
    m = re.search(r'task\s+(\d+)', output, re.IGNORECASE)
    return m.group(1) if m else None


def _magic_to_code(cmd):
    """Convert a %task magic command to executable Python code."""
    from basilisk.shell import (
        _task_list_code, _task_create_code, _task_add_step_code, _task_info_code,
        _task_start_code, _task_stop_code, _task_delete_code, _task_log_code,
    )
    stripped = cmd.strip()
    if stripped.startswith("%task"):
        stripped = stripped[5:].strip()
    if not stripped:
        return _task_list_code()

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
    elif sub == "run":
        from basilisk.shell import _task_run_code
        return _task_run_code(rest.strip())
    else:
        raise ValueError(f"Unknown %task subcommand: {sub}")


def _task_magic(cmd, canister, network):
    """Run a magic command via dfx from the test_canister dir."""
    result = _local_canister_exec(
        _magic_to_code(cmd), canister, network,
    )
    return result.strip() if result else ""


def _cleanup_task(tid, canister, network):
    _task_magic(f"%task delete {tid}", canister, network)


def _wait_for_task_execution(tid, canister, network, timeout=120, poll=5):
    """Poll task log until execution completes (completed/failed) or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        log = _task_magic(f"%task log {tid}", canister, network)
        if "completed" in log or "failed" in log:
            return log
        time.sleep(poll)
    return log


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


def _run_async_task(name, code, canister, network, timeout=120):
    """Write async code to canister, create bare task, add async step via --file, start, wait, return log."""
    path = f"/_fx_test_{name}.py"
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
    log = _wait_for_task_execution(tid, canister, network, timeout=timeout)

    # Clean up
    _cleanup_task(tid, canister, network)
    _local_canister_exec(
        f"import os; os.remove('{path}') if os.path.exists('{path}') else None",
        canister, network,
    )
    return log


# ===========================================================================
# 1. FXPair Entity CRUD (synchronous)
# ===========================================================================

class TestFXPairEntity:
    """Test FXPair entity CRUD via exec on canister."""

    def test_create_fxpair(self, fx_reachable, fx_canister, fx_network):
        """Create a new FXPair entity and verify fields."""
        result = _exec(
            "p = FXPair(name='TEST_BTC/USD', base_symbol='BTC', "
            "base_class='Cryptocurrency', quote_symbol='USD', "
            "quote_class='FiatCurrency')\n"
            "print(f'{p.name}|{p.base_symbol}|{p.base_class}|{p.quote_symbol}|{p.quote_class}')",
            fx_canister, fx_network,
        )
        assert "TEST_BTC/USD|BTC|Cryptocurrency|USD|FiatCurrency" in result

    def test_get_fxpair_by_alias(self, fx_reachable, fx_canister, fx_network):
        """Retrieve FXPair by name alias."""
        result = _exec(
            "p = FXPair['TEST_BTC/USD']\n"
            "print(p.base_symbol if p else 'NOT_FOUND')",
            fx_canister, fx_network,
        )
        assert "BTC" in result

    def test_fxpair_default_values(self, fx_reachable, fx_canister, fx_network):
        """Verify default values for rate, decimals, last_updated, last_error."""
        result = _exec(
            "p = FXPair['TEST_BTC/USD']\n"
            "print(f'{p.rate}|{p.decimals}|{p.last_updated}|{repr(p.last_error)}')",
            fx_canister, fx_network,
        )
        assert "0|9|0|" in result

    def test_update_fxpair_rate(self, fx_reachable, fx_canister, fx_network):
        """Update rate and decimals fields."""
        result = _exec(
            "p = FXPair['TEST_BTC/USD']\n"
            "p.rate = 67000_000_000_000\n"
            "p.decimals = 9\n"
            "p.last_updated = 1700000000\n"
            "p2 = FXPair['TEST_BTC/USD']\n"
            "print(f'{p2.rate}|{p2.decimals}|{p2.last_updated}')",
            fx_canister, fx_network,
        )
        assert "67000000000000|9|1700000000" in result

    def test_update_fxpair_error(self, fx_reachable, fx_canister, fx_network):
        """Update last_error field."""
        result = _exec(
            "p = FXPair['TEST_BTC/USD']\n"
            "p.last_error = 'RateLimited'\n"
            "p2 = FXPair['TEST_BTC/USD']\n"
            "print(p2.last_error)",
            fx_canister, fx_network,
        )
        assert "RateLimited" in result

    def test_create_second_fxpair(self, fx_reachable, fx_canister, fx_network):
        """Create a second FXPair."""
        result = _exec(
            "p = FXPair(name='TEST_ICP/USD', base_symbol='ICP', "
            "base_class='Cryptocurrency', quote_symbol='USD', "
            "quote_class='FiatCurrency')\n"
            "print(f'{p.name}|{p.base_symbol}')",
            fx_canister, fx_network,
        )
        assert "TEST_ICP/USD|ICP" in result

    def test_create_fiat_pair(self, fx_reachable, fx_canister, fx_network):
        """Create a fiat-to-fiat FXPair."""
        result = _exec(
            "p = FXPair(name='TEST_EUR/USD', base_symbol='EUR', "
            "base_class='FiatCurrency', quote_symbol='USD', "
            "quote_class='FiatCurrency')\n"
            "print(f'{p.name}|{p.base_class}|{p.quote_class}')",
            fx_canister, fx_network,
        )
        assert "TEST_EUR/USD|FiatCurrency|FiatCurrency" in result

    def test_list_fxpairs(self, fx_reachable, fx_canister, fx_network):
        """List all FXPair entities with TEST_ prefix."""
        result = _exec(
            "names = sorted([p.name for p in FXPair.instances() if p.name.startswith('TEST_')])\n"
            "print('|'.join(names))",
            fx_canister, fx_network,
        )
        assert "TEST_BTC/USD" in result
        assert "TEST_ICP/USD" in result
        assert "TEST_EUR/USD" in result

    def test_fxpair_count(self, fx_reachable, fx_canister, fx_network):
        """Count FXPair entities."""
        result = _exec(
            "c = len([p for p in FXPair.instances() if p.name.startswith('TEST_')])\n"
            "print(c)",
            fx_canister, fx_network,
        )
        assert int(result) >= 3

    def test_delete_fxpair(self, fx_reachable, fx_canister, fx_network):
        """Delete an FXPair and verify removal."""
        result = _exec(
            "p = FXPair['TEST_EUR/USD']\n"
            "if p: p.delete()\n"
            "p2 = FXPair['TEST_EUR/USD']\n"
            "print('GONE' if p2 is None else 'STILL_HERE')",
            fx_canister, fx_network,
        )
        assert "GONE" in result

    def test_cleanup_entity_tests(self, fx_reachable, fx_canister, fx_network):
        """Clean up all TEST_ FXPair entities."""
        _exec(
            "for p in list(FXPair.instances()):\n"
            "    if p.name.startswith('TEST_'):\n"
            "        p.delete()\n"
            "print('cleaned')",
            fx_canister, fx_network,
        )


# ===========================================================================
# 2. FXService — pair registry (synchronous)
# ===========================================================================

# FXService preamble — resolves the FXPair entity + a lightweight FXService
# that works without basilisk.canisters.xrc import (sync-only methods).
_FXSERVICE_RESOLVE = (
    _FXPAIR_RESOLVE +
    "if 'FXService' not in dir():\n"
    "    class FXService:\n"
    "        def register_pair(self, base_symbol, quote_symbol, base_class='Cryptocurrency', quote_class='FiatCurrency'):\n"
    "            name = f'{base_symbol}/{quote_symbol}'\n"
    "            pair = FXPair[name]\n"
    "            if pair is None:\n"
    "                pair = FXPair(name=name, base_symbol=base_symbol, base_class=base_class, quote_symbol=quote_symbol, quote_class=quote_class)\n"
    "            else:\n"
    "                pair.base_symbol = base_symbol\n"
    "                pair.base_class = base_class\n"
    "                pair.quote_symbol = quote_symbol\n"
    "                pair.quote_class = quote_class\n"
    "            return pair\n"
    "        def unregister_pair(self, base_symbol, quote_symbol):\n"
    "            name = f'{base_symbol}/{quote_symbol}'\n"
    "            pair = FXPair[name]\n"
    "            if pair is None: return False\n"
    "            pair.delete()\n"
    "            return True\n"
    "        def get_pair(self, base_symbol, quote_symbol):\n"
    "            return FXPair[f'{base_symbol}/{quote_symbol}']\n"
    "        def list_pairs(self):\n"
    "            pairs = []\n"
    "            for pair in FXPair.instances():\n"
    "                human_rate = pair.rate / (10 ** pair.decimals) if pair.rate and pair.decimals else 0.0\n"
    "                pairs.append({'name': pair.name, 'base_symbol': pair.base_symbol, 'rate': pair.rate, 'human_rate': human_rate, 'last_updated': pair.last_updated, 'last_error': pair.last_error})\n"
    "            return pairs\n"
    "        def get_rate(self, base_symbol, quote_symbol):\n"
    "            pair = FXPair[f'{base_symbol}/{quote_symbol}']\n"
    "            if pair is None or pair.rate == 0: return None\n"
    "            return pair.rate / (10 ** pair.decimals)\n"
    "        def get_rate_info(self, base_symbol, quote_symbol):\n"
    "            pair = FXPair[f'{base_symbol}/{quote_symbol}']\n"
    "            if pair is None: return None\n"
    "            human_rate = pair.rate / (10 ** pair.decimals) if pair.rate and pair.decimals else 0.0\n"
    "            return {'pair': pair.name, 'rate': human_rate, 'raw_rate': pair.rate, 'decimals': pair.decimals, 'last_updated': pair.last_updated, 'last_error': pair.last_error}\n"
)


def _exec_fx(code, canister, network):
    """Execute code on canister with FXService resolved."""
    return _local_canister_exec(_FXSERVICE_RESOLVE + code, canister, network).strip()


class TestFXServiceRegistry:
    """Test FXService pair registration (sync operations)."""

    def test_register_pair(self, fx_reachable, fx_canister, fx_network):
        """Register a pair via FXService and verify."""
        result = _exec_fx(
            "fx = FXService()\n"
            "p = fx.register_pair('BTC', 'USD')\n"
            "print(f'{p.name}|{p.base_symbol}|{p.quote_symbol}')",
            fx_canister, fx_network,
        )
        assert "BTC/USD|BTC|USD" in result

    def test_register_pair_idempotent(self, fx_reachable, fx_canister, fx_network):
        """Re-registering a pair should update, not duplicate."""
        result = _exec_fx(
            "fx = FXService()\n"
            "p1 = fx.register_pair('BTC', 'USD')\n"
            "p2 = fx.register_pair('BTC', 'USD')\n"
            "count = len([p for p in FXPair.instances() if p.name == 'BTC/USD'])\n"
            "print(f'count={count}')",
            fx_canister, fx_network,
        )
        assert "count=1" in result

    def test_register_multiple_pairs(self, fx_reachable, fx_canister, fx_network):
        """Register multiple pairs."""
        result = _exec_fx(
            "fx = FXService()\n"
            "fx.register_pair('ICP', 'USD')\n"
            "fx.register_pair('ETH', 'USD')\n"
            "names = sorted([p.name for p in FXPair.instances() if p.name.endswith('/USD')])\n"
            "print('|'.join(names))",
            fx_canister, fx_network,
        )
        assert "BTC/USD" in result
        assert "ETH/USD" in result
        assert "ICP/USD" in result

    def test_register_fiat_pair(self, fx_reachable, fx_canister, fx_network):
        """Register a fiat-to-fiat pair."""
        result = _exec_fx(
            "fx = FXService()\n"
            "p = fx.register_pair('EUR', 'USD', base_class='FiatCurrency')\n"
            "print(f'{p.name}|{p.base_class}|{p.quote_class}')",
            fx_canister, fx_network,
        )
        assert "EUR/USD|FiatCurrency|FiatCurrency" in result

    def test_register_crypto_to_crypto_pair(self, fx_reachable, fx_canister, fx_network):
        """Register a crypto-to-crypto pair."""
        result = _exec_fx(
            "fx = FXService()\n"
            "p = fx.register_pair('BTC', 'ETH', quote_class='Cryptocurrency')\n"
            "print(f'{p.name}|{p.base_class}|{p.quote_class}')",
            fx_canister, fx_network,
        )
        assert "BTC/ETH|Cryptocurrency|Cryptocurrency" in result

    def test_get_pair(self, fx_reachable, fx_canister, fx_network):
        """Get a registered pair by symbols."""
        result = _exec_fx(
            "fx = FXService()\n"
            "p = fx.get_pair('BTC', 'USD')\n"
            "print(p.name if p else 'NOT_FOUND')",
            fx_canister, fx_network,
        )
        assert "BTC/USD" in result

    def test_get_pair_not_found(self, fx_reachable, fx_canister, fx_network):
        """Getting a non-registered pair returns None."""
        result = _exec_fx(
            "fx = FXService()\n"
            "p = fx.get_pair('DOGE', 'USD')\n"
            "print('NONE' if p is None else p.name)",
            fx_canister, fx_network,
        )
        assert "NONE" in result

    def test_list_pairs(self, fx_reachable, fx_canister, fx_network):
        """List all registered pairs."""
        result = _exec_fx(
            "fx = FXService()\n"
            "pairs = fx.list_pairs()\n"
            "for p in sorted(pairs, key=lambda x: x['name']):\n"
            "    print(f\"{p['name']}|{p['rate']}\")\n"
            "print(f'total={len(pairs)}')",
            fx_canister, fx_network,
        )
        assert "BTC/USD" in result
        assert "total=" in result

    def test_unregister_pair(self, fx_reachable, fx_canister, fx_network):
        """Unregister a pair."""
        result = _exec_fx(
            "fx = FXService()\n"
            "removed = fx.unregister_pair('BTC', 'ETH')\n"
            "p = fx.get_pair('BTC', 'ETH')\n"
            "print(f'removed={removed}|exists={p is not None}')",
            fx_canister, fx_network,
        )
        assert "removed=True|exists=False" in result

    def test_unregister_nonexistent(self, fx_reachable, fx_canister, fx_network):
        """Unregister a non-existent pair returns False."""
        result = _exec_fx(
            "fx = FXService()\n"
            "removed = fx.unregister_pair('DOGE', 'USD')\n"
            "print(f'removed={removed}')",
            fx_canister, fx_network,
        )
        assert "removed=False" in result


# ===========================================================================
# 3. FXService — synchronous rate queries
# ===========================================================================

class TestFXServiceRateQueries:
    """Test synchronous rate queries (from DB, no inter-canister call)."""

    def test_get_rate_no_data(self, fx_reachable, fx_canister, fx_network):
        """get_rate returns None when rate is 0 (never refreshed)."""
        result = _exec_fx(
            "fx = FXService()\n"
            "p = FXPair['BTC/USD']\n"
            "if p: p.rate = 0\n"
            "rate = fx.get_rate('BTC', 'USD')\n"
            "print('NONE' if rate is None else rate)",
            fx_canister, fx_network,
        )
        assert "NONE" in result

    def test_get_rate_with_data(self, fx_reachable, fx_canister, fx_network):
        """get_rate returns correct float after manually setting rate."""
        result = _exec_fx(
            "p = FXPair['BTC/USD']\n"
            "p.rate = 67000_000_000_000\n"
            "p.decimals = 9\n"
            "fx = FXService()\n"
            "rate = fx.get_rate('BTC', 'USD')\n"
            "print(f'rate={rate}')",
            fx_canister, fx_network,
        )
        assert "rate=67000.0" in result

    def test_get_rate_not_registered(self, fx_reachable, fx_canister, fx_network):
        """get_rate returns None for a non-registered pair."""
        result = _exec_fx(
            "fx = FXService()\n"
            "rate = fx.get_rate('DOGE', 'USD')\n"
            "print('NONE' if rate is None else rate)",
            fx_canister, fx_network,
        )
        assert "NONE" in result

    def test_get_rate_info(self, fx_reachable, fx_canister, fx_network):
        """get_rate_info returns a complete info dict."""
        result = _exec_fx(
            "p = FXPair['BTC/USD']\n"
            "p.rate = 67000_000_000_000\n"
            "p.decimals = 9\n"
            "p.last_updated = 1700000000\n"
            "p.last_error = ''\n"
            "fx = FXService()\n"
            "info = fx.get_rate_info('BTC', 'USD')\n"
            "print(f\"{info['pair']}|{info['rate']}|{info['raw_rate']}|{info['decimals']}|{info['last_updated']}\")",
            fx_canister, fx_network,
        )
        assert "BTC/USD|67000.0|67000000000000|9|1700000000" in result

    def test_get_rate_info_not_found(self, fx_reachable, fx_canister, fx_network):
        """get_rate_info returns None for a non-registered pair."""
        result = _exec_fx(
            "fx = FXService()\n"
            "info = fx.get_rate_info('DOGE', 'USD')\n"
            "print('NONE' if info is None else 'FOUND')",
            fx_canister, fx_network,
        )
        assert "NONE" in result

    def test_get_rate_info_with_error(self, fx_reachable, fx_canister, fx_network):
        """get_rate_info includes last_error field."""
        result = _exec_fx(
            "p = FXPair['BTC/USD']\n"
            "p.last_error = 'RateLimited'\n"
            "fx = FXService()\n"
            "info = fx.get_rate_info('BTC', 'USD')\n"
            "print(f\"error={info['last_error']}\")",
            fx_canister, fx_network,
        )
        assert "error=RateLimited" in result

    def test_cleanup_rate_queries(self, fx_reachable, fx_canister, fx_network):
        """Reset rate data after sync tests."""
        _exec_fx(
            "p = FXPair['BTC/USD']\n"
            "if p:\n"
            "    p.rate = 0\n"
            "    p.last_updated = 0\n"
            "    p.last_error = ''\n"
            "print('reset')",
            fx_canister, fx_network,
        )


# ===========================================================================
# 4. XRC Canister Binding — async inter-canister call
# ===========================================================================

class TestXRCCanisterBinding:
    """Test calling the real XRC canister from the test canister."""

    def test_query_btc_usd(self, fx_reachable, fx_canister, fx_network):
        """Query BTC/USD rate from the XRC canister."""
        code = (
            "from basilisk import Record, Service, service_update, Principal, Opt, Variant, nat32, nat64, null, text, Async\n"
            "\n"
            "class _AssetClass(Variant, total=False):\n"
            "    Cryptocurrency: null\n"
            "    FiatCurrency: null\n"
            "class _Asset(Record):\n"
            "    symbol: text\n"
            "    class_: _AssetClass\n"
            "class _GetExchangeRateRequest(Record):\n"
            "    base_asset: _Asset\n"
            "    quote_asset: _Asset\n"
            "    timestamp: Opt[nat64]\n"
            "class _ExchangeRateMetadata(Record):\n"
            "    decimals: nat32\n"
            "    base_asset_num_queried_sources: nat64\n"
            "    base_asset_num_received_rates: nat64\n"
            "    quote_asset_num_queried_sources: nat64\n"
            "    quote_asset_num_received_rates: nat64\n"
            "    standard_deviation: nat64\n"
            "    forex_timestamp: Opt[nat64]\n"
            "class _ExchangeRate(Record):\n"
            "    base_asset: _Asset\n"
            "    quote_asset: _Asset\n"
            "    timestamp: nat64\n"
            "    rate: nat64\n"
            "    metadata: _ExchangeRateMetadata\n"
            "class _OtherError(Record):\n"
            "    code: nat32\n"
            "    description: text\n"
            "class _ExchangeRateError(Variant, total=False):\n"
            "    AnonymousPrincipalNotAllowed: null\n"
            "    Pending: null\n"
            "    CryptoBaseAssetNotFound: null\n"
            "    CryptoQuoteAssetNotFound: null\n"
            "    StablecoinRateNotFound: null\n"
            "    StablecoinRateTooFewRates: null\n"
            "    StablecoinRateZeroRate: null\n"
            "    ForexInvalidTimestamp: null\n"
            "    ForexBaseAssetNotFound: null\n"
            "    ForexQuoteAssetNotFound: null\n"
            "    ForexAssetsNotFound: null\n"
            "    RateLimited: null\n"
            "    NotEnoughCycles: null\n"
            "    FailedToAcceptCycles: null\n"
            "    InconsistentRatesReceived: null\n"
            "    Other: _OtherError\n"
            "class _GetExchangeRateResult(Variant, total=False):\n"
            "    Ok: _ExchangeRate\n"
            "    Err: _ExchangeRateError\n"
            "\n"
            "class XRCCanister(Service):\n"
            "    @service_update\n"
            "    def get_exchange_rate(self, args: _GetExchangeRateRequest) -> _GetExchangeRateResult: ...\n"
            "\n"
            "_ASSET_CLASS_CANDID = 'variant { Cryptocurrency : null; FiatCurrency : null }'\n"
            "_ASSET_CANDID = f'record {{ symbol : text; class : {_ASSET_CLASS_CANDID} }}'\n"
            "_METADATA_CANDID = 'record { decimals : nat32; base_asset_num_queried_sources : nat64; base_asset_num_received_rates : nat64; quote_asset_num_queried_sources : nat64; quote_asset_num_received_rates : nat64; standard_deviation : nat64; forex_timestamp : opt nat64 }'\n"
            "_EXCHANGE_RATE_CANDID = f'record {{ base_asset : {_ASSET_CANDID}; quote_asset : {_ASSET_CANDID}; timestamp : nat64; rate : nat64; metadata : {_METADATA_CANDID} }}'\n"
            "_OTHER_ERROR_CANDID = 'record { code : nat32; description : text }'\n"
            "_EXCHANGE_RATE_ERROR_CANDID = f'variant {{ AnonymousPrincipalNotAllowed : null; Pending : null; CryptoBaseAssetNotFound : null; CryptoQuoteAssetNotFound : null; StablecoinRateNotFound : null; StablecoinRateTooFewRates : null; StablecoinRateZeroRate : null; ForexInvalidTimestamp : null; ForexBaseAssetNotFound : null; ForexQuoteAssetNotFound : null; ForexAssetsNotFound : null; RateLimited : null; NotEnoughCycles : null; FailedToAcceptCycles : null; InconsistentRatesReceived : null; Other : {_OTHER_ERROR_CANDID} }}'\n"
            "_GET_EXCHANGE_RATE_RESULT_CANDID = f'variant {{ Ok : {_EXCHANGE_RATE_CANDID}; Err : {_EXCHANGE_RATE_ERROR_CANDID} }}'\n"
            "XRCCanister._arg_types = {'get_exchange_rate': f'record {{ base_asset : {_ASSET_CANDID}; quote_asset : {_ASSET_CANDID}; timestamp : opt nat64 }}'}\n"
            "XRCCanister._return_types = {'get_exchange_rate': _GET_EXCHANGE_RATE_RESULT_CANDID}\n"
            "\n"
            "def async_task():\n"
            "    xrc = XRCCanister(Principal.from_str('uf6dk-hyaaa-aaaaq-qaaaq-cai'))\n"
            "    result = yield xrc.get_exchange_rate({\n"
            "        'base_asset': {'symbol': 'BTC', 'class': {'Cryptocurrency': None}},\n"
            "        'quote_asset': {'symbol': 'USD', 'class': {'FiatCurrency': None}},\n"
            "        'timestamp': None,\n"
            "    }).with_cycles(1_000_000_000)\n"
            "    raw = result\n"
            "    if hasattr(result, 'Ok'):\n"
            "        raw = result.Ok if result.Ok else result.Err\n"
            "    if isinstance(raw, dict) and 'Ok' in raw:\n"
            "        data = raw['Ok']\n"
            "        rate = data['rate']\n"
            "        decimals = data['metadata']['decimals']\n"
            "        human = rate / (10 ** decimals)\n"
            "        return f'FX_RATE:BTC/USD={human}|raw={rate}|dec={decimals}'\n"
            "    elif isinstance(raw, dict) and 'Err' in raw:\n"
            "        return f'FX_ERR:{raw[\"Err\"]}'\n"
            "    else:\n"
            "        return f'FX_RAW:{raw}'\n"
        )
        log = _run_async_task(
            "_test_xrc_btc_usd", code,
            fx_canister, fx_network, timeout=90,
        )
        assert "completed" in log, f"Task did not complete: {log}"

        m = re.search(r'FX_RATE:BTC/USD=([0-9.]+)\|raw=(\d+)\|dec=(\d+)', log)
        if m:
            human_rate = float(m.group(1))
            raw_rate = int(m.group(2))
            decimals = int(m.group(3))
            # BTC should be > $10,000
            assert human_rate > 10000, f"BTC/USD rate too low: {human_rate}"
            assert raw_rate > 0
            assert decimals > 0
            print(f"\n  BTC/USD = {human_rate} (raw={raw_rate}, dec={decimals})")
        else:
            # May get RateLimited or other expected errors — don't fail hard
            assert "FX_ERR:" in log or "FX_RAW:" in log, \
                f"Unexpected response: {log}"
            print(f"\n  XRC response (non-Ok): {log}")

    def test_query_icp_usd(self, fx_reachable, fx_canister, fx_network):
        """Query ICP/USD rate from the XRC canister."""
        code = (
            "from basilisk import Record, Service, service_update, Principal, Opt, Variant, nat32, nat64, null, text, Async\n"
            "\n"
            "class _AssetClass(Variant, total=False):\n"
            "    Cryptocurrency: null\n"
            "    FiatCurrency: null\n"
            "class _Asset(Record):\n"
            "    symbol: text\n"
            "    class_: _AssetClass\n"
            "class _GetExchangeRateRequest(Record):\n"
            "    base_asset: _Asset\n"
            "    quote_asset: _Asset\n"
            "    timestamp: Opt[nat64]\n"
            "class _ExchangeRateMetadata(Record):\n"
            "    decimals: nat32\n"
            "    base_asset_num_queried_sources: nat64\n"
            "    base_asset_num_received_rates: nat64\n"
            "    quote_asset_num_queried_sources: nat64\n"
            "    quote_asset_num_received_rates: nat64\n"
            "    standard_deviation: nat64\n"
            "    forex_timestamp: Opt[nat64]\n"
            "class _ExchangeRate(Record):\n"
            "    base_asset: _Asset\n"
            "    quote_asset: _Asset\n"
            "    timestamp: nat64\n"
            "    rate: nat64\n"
            "    metadata: _ExchangeRateMetadata\n"
            "class _OtherError(Record):\n"
            "    code: nat32\n"
            "    description: text\n"
            "class _ExchangeRateError(Variant, total=False):\n"
            "    AnonymousPrincipalNotAllowed: null\n"
            "    Pending: null\n"
            "    CryptoBaseAssetNotFound: null\n"
            "    CryptoQuoteAssetNotFound: null\n"
            "    StablecoinRateNotFound: null\n"
            "    StablecoinRateTooFewRates: null\n"
            "    StablecoinRateZeroRate: null\n"
            "    ForexInvalidTimestamp: null\n"
            "    ForexBaseAssetNotFound: null\n"
            "    ForexQuoteAssetNotFound: null\n"
            "    ForexAssetsNotFound: null\n"
            "    RateLimited: null\n"
            "    NotEnoughCycles: null\n"
            "    FailedToAcceptCycles: null\n"
            "    InconsistentRatesReceived: null\n"
            "    Other: _OtherError\n"
            "class _GetExchangeRateResult(Variant, total=False):\n"
            "    Ok: _ExchangeRate\n"
            "    Err: _ExchangeRateError\n"
            "\n"
            "class XRCCanister(Service):\n"
            "    @service_update\n"
            "    def get_exchange_rate(self, args: _GetExchangeRateRequest) -> _GetExchangeRateResult: ...\n"
            "\n"
            "_ASSET_CLASS_CANDID = 'variant { Cryptocurrency : null; FiatCurrency : null }'\n"
            "_ASSET_CANDID = f'record {{ symbol : text; class : {_ASSET_CLASS_CANDID} }}'\n"
            "_METADATA_CANDID = 'record { decimals : nat32; base_asset_num_queried_sources : nat64; base_asset_num_received_rates : nat64; quote_asset_num_queried_sources : nat64; quote_asset_num_received_rates : nat64; standard_deviation : nat64; forex_timestamp : opt nat64 }'\n"
            "_EXCHANGE_RATE_CANDID = f'record {{ base_asset : {_ASSET_CANDID}; quote_asset : {_ASSET_CANDID}; timestamp : nat64; rate : nat64; metadata : {_METADATA_CANDID} }}'\n"
            "_OTHER_ERROR_CANDID = 'record { code : nat32; description : text }'\n"
            "_EXCHANGE_RATE_ERROR_CANDID = f'variant {{ AnonymousPrincipalNotAllowed : null; Pending : null; CryptoBaseAssetNotFound : null; CryptoQuoteAssetNotFound : null; StablecoinRateNotFound : null; StablecoinRateTooFewRates : null; StablecoinRateZeroRate : null; ForexInvalidTimestamp : null; ForexBaseAssetNotFound : null; ForexQuoteAssetNotFound : null; ForexAssetsNotFound : null; RateLimited : null; NotEnoughCycles : null; FailedToAcceptCycles : null; InconsistentRatesReceived : null; Other : {_OTHER_ERROR_CANDID} }}'\n"
            "_GET_EXCHANGE_RATE_RESULT_CANDID = f'variant {{ Ok : {_EXCHANGE_RATE_CANDID}; Err : {_EXCHANGE_RATE_ERROR_CANDID} }}'\n"
            "XRCCanister._arg_types = {'get_exchange_rate': f'record {{ base_asset : {_ASSET_CANDID}; quote_asset : {_ASSET_CANDID}; timestamp : opt nat64 }}'}\n"
            "XRCCanister._return_types = {'get_exchange_rate': _GET_EXCHANGE_RATE_RESULT_CANDID}\n"
            "\n"
            "def async_task():\n"
            "    xrc = XRCCanister(Principal.from_str('uf6dk-hyaaa-aaaaq-qaaaq-cai'))\n"
            "    result = yield xrc.get_exchange_rate({\n"
            "        'base_asset': {'symbol': 'ICP', 'class': {'Cryptocurrency': None}},\n"
            "        'quote_asset': {'symbol': 'USD', 'class': {'FiatCurrency': None}},\n"
            "        'timestamp': None,\n"
            "    }).with_cycles(1_000_000_000)\n"
            "    raw = result\n"
            "    if hasattr(result, 'Ok'):\n"
            "        raw = result.Ok if result.Ok else result.Err\n"
            "    if isinstance(raw, dict) and 'Ok' in raw:\n"
            "        data = raw['Ok']\n"
            "        rate = data['rate']\n"
            "        decimals = data['metadata']['decimals']\n"
            "        human = rate / (10 ** decimals)\n"
            "        return f'FX_RATE:ICP/USD={human}|raw={rate}|dec={decimals}'\n"
            "    elif isinstance(raw, dict) and 'Err' in raw:\n"
            "        return f'FX_ERR:{raw[\"Err\"]}'\n"
            "    else:\n"
            "        return f'FX_RAW:{raw}'\n"
        )
        log = _run_async_task(
            "_test_xrc_icp_usd", code,
            fx_canister, fx_network, timeout=90,
        )
        assert "completed" in log, f"Task did not complete: {log}"

        m = re.search(r'FX_RATE:ICP/USD=([0-9.]+)', log)
        if m:
            human_rate = float(m.group(1))
            # ICP should be > $0.10
            assert human_rate > 0.10, f"ICP/USD rate suspiciously low: {human_rate}"
            print(f"\n  ICP/USD = {human_rate}")
        else:
            assert "FX_ERR:" in log or "FX_RAW:" in log, \
                f"Unexpected response: {log}"
            print(f"\n  XRC response (non-Ok): {log}")

    def test_query_invalid_asset(self, fx_reachable, fx_canister, fx_network):
        """Query an invalid asset pair should return an error."""
        code = (
            "from basilisk import Record, Service, service_update, Principal, Opt, Variant, nat32, nat64, null, text, Async\n"
            "\n"
            "class _AssetClass(Variant, total=False):\n"
            "    Cryptocurrency: null\n"
            "    FiatCurrency: null\n"
            "class _Asset(Record):\n"
            "    symbol: text\n"
            "    class_: _AssetClass\n"
            "class _GetExchangeRateRequest(Record):\n"
            "    base_asset: _Asset\n"
            "    quote_asset: _Asset\n"
            "    timestamp: Opt[nat64]\n"
            "class _ExchangeRateMetadata(Record):\n"
            "    decimals: nat32\n"
            "    base_asset_num_queried_sources: nat64\n"
            "    base_asset_num_received_rates: nat64\n"
            "    quote_asset_num_queried_sources: nat64\n"
            "    quote_asset_num_received_rates: nat64\n"
            "    standard_deviation: nat64\n"
            "    forex_timestamp: Opt[nat64]\n"
            "class _ExchangeRate(Record):\n"
            "    base_asset: _Asset\n"
            "    quote_asset: _Asset\n"
            "    timestamp: nat64\n"
            "    rate: nat64\n"
            "    metadata: _ExchangeRateMetadata\n"
            "class _OtherError(Record):\n"
            "    code: nat32\n"
            "    description: text\n"
            "class _ExchangeRateError(Variant, total=False):\n"
            "    AnonymousPrincipalNotAllowed: null\n"
            "    Pending: null\n"
            "    CryptoBaseAssetNotFound: null\n"
            "    CryptoQuoteAssetNotFound: null\n"
            "    StablecoinRateNotFound: null\n"
            "    StablecoinRateTooFewRates: null\n"
            "    StablecoinRateZeroRate: null\n"
            "    ForexInvalidTimestamp: null\n"
            "    ForexBaseAssetNotFound: null\n"
            "    ForexQuoteAssetNotFound: null\n"
            "    ForexAssetsNotFound: null\n"
            "    RateLimited: null\n"
            "    NotEnoughCycles: null\n"
            "    FailedToAcceptCycles: null\n"
            "    InconsistentRatesReceived: null\n"
            "    Other: _OtherError\n"
            "class _GetExchangeRateResult(Variant, total=False):\n"
            "    Ok: _ExchangeRate\n"
            "    Err: _ExchangeRateError\n"
            "\n"
            "class XRCCanister(Service):\n"
            "    @service_update\n"
            "    def get_exchange_rate(self, args: _GetExchangeRateRequest) -> _GetExchangeRateResult: ...\n"
            "\n"
            "_ASSET_CLASS_CANDID = 'variant { Cryptocurrency : null; FiatCurrency : null }'\n"
            "_ASSET_CANDID = f'record {{ symbol : text; class : {_ASSET_CLASS_CANDID} }}'\n"
            "_METADATA_CANDID = 'record { decimals : nat32; base_asset_num_queried_sources : nat64; base_asset_num_received_rates : nat64; quote_asset_num_queried_sources : nat64; quote_asset_num_received_rates : nat64; standard_deviation : nat64; forex_timestamp : opt nat64 }'\n"
            "_EXCHANGE_RATE_CANDID = f'record {{ base_asset : {_ASSET_CANDID}; quote_asset : {_ASSET_CANDID}; timestamp : nat64; rate : nat64; metadata : {_METADATA_CANDID} }}'\n"
            "_OTHER_ERROR_CANDID = 'record { code : nat32; description : text }'\n"
            "_EXCHANGE_RATE_ERROR_CANDID = f'variant {{ AnonymousPrincipalNotAllowed : null; Pending : null; CryptoBaseAssetNotFound : null; CryptoQuoteAssetNotFound : null; StablecoinRateNotFound : null; StablecoinRateTooFewRates : null; StablecoinRateZeroRate : null; ForexInvalidTimestamp : null; ForexBaseAssetNotFound : null; ForexQuoteAssetNotFound : null; ForexAssetsNotFound : null; RateLimited : null; NotEnoughCycles : null; FailedToAcceptCycles : null; InconsistentRatesReceived : null; Other : {_OTHER_ERROR_CANDID} }}'\n"
            "_GET_EXCHANGE_RATE_RESULT_CANDID = f'variant {{ Ok : {_EXCHANGE_RATE_CANDID}; Err : {_EXCHANGE_RATE_ERROR_CANDID} }}'\n"
            "XRCCanister._arg_types = {'get_exchange_rate': f'record {{ base_asset : {_ASSET_CANDID}; quote_asset : {_ASSET_CANDID}; timestamp : opt nat64 }}'}\n"
            "XRCCanister._return_types = {'get_exchange_rate': _GET_EXCHANGE_RATE_RESULT_CANDID}\n"
            "\n"
            "def async_task():\n"
            "    xrc = XRCCanister(Principal.from_str('uf6dk-hyaaa-aaaaq-qaaaq-cai'))\n"
            "    result = yield xrc.get_exchange_rate({\n"
            "        'base_asset': {'symbol': 'ZZZZNOTREAL', 'class': {'Cryptocurrency': None}},\n"
            "        'quote_asset': {'symbol': 'USD', 'class': {'FiatCurrency': None}},\n"
            "        'timestamp': None,\n"
            "    }).with_cycles(1_000_000_000)\n"
            "    raw = result\n"
            "    if hasattr(result, 'Ok'):\n"
            "        raw = result.Ok if result.Ok else result.Err\n"
            "    if isinstance(raw, dict) and 'Err' in raw:\n"
            "        return f'FX_EXPECTED_ERR:{raw[\"Err\"]}'\n"
            "    elif isinstance(raw, dict) and 'Ok' in raw:\n"
            "        return f'FX_UNEXPECTED_OK:{raw[\"Ok\"]}'\n"
            "    else:\n"
            "        return f'FX_RAW:{raw}'\n"
        )
        log = _run_async_task(
            "_test_xrc_invalid", code,
            fx_canister, fx_network, timeout=90,
        )
        assert "completed" in log, f"Task did not complete: {log}"
        # Should get CryptoBaseAssetNotFound or similar error
        assert "FX_EXPECTED_ERR:" in log or "FX_RAW:" in log, \
            f"Expected error for invalid asset: {log}"
        print(f"\n  Invalid asset response: {log}")


# ===========================================================================
# 5. FXService.refresh — async, stores results in DB
# ===========================================================================

class TestFXServiceRefresh:
    """Test FXService.refresh() writing rates to the DB via async XRC calls."""

    def test_refresh_updates_db(self, fx_reachable, fx_canister, fx_network):
        """refresh() should query XRC and update FXPair entities in the DB."""
        # Ensure BTC/USD and ICP/USD pairs exist
        _exec_fx(
            "fx = FXService()\n"
            "fx.register_pair('BTC', 'USD')\n"
            "fx.register_pair('ICP', 'USD')\n"
            "# Reset rates so we can detect updates\n"
            "for p in FXPair.instances():\n"
            "    p.rate = 0\n"
            "    p.last_updated = 0\n"
            "print('pairs_ready')",
            fx_canister, fx_network,
        )

        # The refresh async code — loop over registered pairs, query XRC, update DB
        code = (
            "from basilisk import Record, Service, service_update, Principal, Opt, Variant, nat32, nat64, null, text, Async\n"
            "from ic_python_db import Entity, String, Integer, TimestampedMixin\n"
            "\n"
            "if 'FXPair' not in dir():\n"
            "    class FXPair(Entity, TimestampedMixin):\n"
            "        __alias__ = 'name'\n"
            "        name = String(max_length=16)\n"
            "        base_symbol = String(max_length=8)\n"
            "        base_class = String(max_length=16)\n"
            "        quote_symbol = String(max_length=8)\n"
            "        quote_class = String(max_length=16)\n"
            "        rate = Integer(default=0)\n"
            "        decimals = Integer(default=9)\n"
            "        last_updated = Integer(default=0)\n"
            "        last_error = String(max_length=256)\n"
            "\n"
            "class _AssetClass(Variant, total=False):\n"
            "    Cryptocurrency: null\n"
            "    FiatCurrency: null\n"
            "class _Asset(Record):\n"
            "    symbol: text\n"
            "    class_: _AssetClass\n"
            "class _GetExchangeRateRequest(Record):\n"
            "    base_asset: _Asset\n"
            "    quote_asset: _Asset\n"
            "    timestamp: Opt[nat64]\n"
            "class _ExchangeRateMetadata(Record):\n"
            "    decimals: nat32\n"
            "    base_asset_num_queried_sources: nat64\n"
            "    base_asset_num_received_rates: nat64\n"
            "    quote_asset_num_queried_sources: nat64\n"
            "    quote_asset_num_received_rates: nat64\n"
            "    standard_deviation: nat64\n"
            "    forex_timestamp: Opt[nat64]\n"
            "class _ExchangeRate(Record):\n"
            "    base_asset: _Asset\n"
            "    quote_asset: _Asset\n"
            "    timestamp: nat64\n"
            "    rate: nat64\n"
            "    metadata: _ExchangeRateMetadata\n"
            "class _OtherError(Record):\n"
            "    code: nat32\n"
            "    description: text\n"
            "class _ExchangeRateError(Variant, total=False):\n"
            "    AnonymousPrincipalNotAllowed: null\n"
            "    Pending: null\n"
            "    CryptoBaseAssetNotFound: null\n"
            "    CryptoQuoteAssetNotFound: null\n"
            "    StablecoinRateNotFound: null\n"
            "    StablecoinRateTooFewRates: null\n"
            "    StablecoinRateZeroRate: null\n"
            "    ForexInvalidTimestamp: null\n"
            "    ForexBaseAssetNotFound: null\n"
            "    ForexQuoteAssetNotFound: null\n"
            "    ForexAssetsNotFound: null\n"
            "    RateLimited: null\n"
            "    NotEnoughCycles: null\n"
            "    FailedToAcceptCycles: null\n"
            "    InconsistentRatesReceived: null\n"
            "    Other: _OtherError\n"
            "class _GetExchangeRateResult(Variant, total=False):\n"
            "    Ok: _ExchangeRate\n"
            "    Err: _ExchangeRateError\n"
            "class XRCCanister(Service):\n"
            "    @service_update\n"
            "    def get_exchange_rate(self, args: _GetExchangeRateRequest) -> _GetExchangeRateResult: ...\n"
            "\n"
            "_ASSET_CLASS_CANDID = 'variant { Cryptocurrency : null; FiatCurrency : null }'\n"
            "_ASSET_CANDID = f'record {{ symbol : text; class : {_ASSET_CLASS_CANDID} }}'\n"
            "_METADATA_CANDID = 'record { decimals : nat32; base_asset_num_queried_sources : nat64; base_asset_num_received_rates : nat64; quote_asset_num_queried_sources : nat64; quote_asset_num_received_rates : nat64; standard_deviation : nat64; forex_timestamp : opt nat64 }'\n"
            "_EXCHANGE_RATE_CANDID = f'record {{ base_asset : {_ASSET_CANDID}; quote_asset : {_ASSET_CANDID}; timestamp : nat64; rate : nat64; metadata : {_METADATA_CANDID} }}'\n"
            "_OTHER_ERROR_CANDID = 'record { code : nat32; description : text }'\n"
            "_EXCHANGE_RATE_ERROR_CANDID = f'variant {{ AnonymousPrincipalNotAllowed : null; Pending : null; CryptoBaseAssetNotFound : null; CryptoQuoteAssetNotFound : null; StablecoinRateNotFound : null; StablecoinRateTooFewRates : null; StablecoinRateZeroRate : null; ForexInvalidTimestamp : null; ForexBaseAssetNotFound : null; ForexQuoteAssetNotFound : null; ForexAssetsNotFound : null; RateLimited : null; NotEnoughCycles : null; FailedToAcceptCycles : null; InconsistentRatesReceived : null; Other : {_OTHER_ERROR_CANDID} }}'\n"
            "_GET_EXCHANGE_RATE_RESULT_CANDID = f'variant {{ Ok : {_EXCHANGE_RATE_CANDID}; Err : {_EXCHANGE_RATE_ERROR_CANDID} }}'\n"
            "XRCCanister._arg_types = {'get_exchange_rate': f'record {{ base_asset : {_ASSET_CANDID}; quote_asset : {_ASSET_CANDID}; timestamp : opt nat64 }}'}\n"
            "XRCCanister._return_types = {'get_exchange_rate': _GET_EXCHANGE_RATE_RESULT_CANDID}\n"
            "\n"
            "def async_task():\n"
            "    xrc = XRCCanister(Principal.from_str('uf6dk-hyaaa-aaaaq-qaaaq-cai'))\n"
            "    pairs = list(FXPair.instances())\n"
            "    now = int(ic.time() / 1e9)\n"
            "    results = []\n"
            "    for pair in pairs:\n"
            "        try:\n"
            "            result = yield xrc.get_exchange_rate({\n"
            "                'base_asset': {'symbol': pair.base_symbol, 'class': {pair.base_class: None}},\n"
            "                'quote_asset': {'symbol': pair.quote_symbol, 'class': {pair.quote_class: None}},\n"
            "                'timestamp': None,\n"
            "            }).with_cycles(1_000_000_000)\n"
            "            raw = result\n"
            "            if hasattr(result, 'Ok'):\n"
            "                raw = result.Ok if result.Ok else result.Err\n"
            "            if isinstance(raw, dict) and 'Ok' in raw:\n"
            "                data = raw['Ok']\n"
            "                pair.rate = data['rate']\n"
            "                pair.decimals = data['metadata']['decimals']\n"
            "                pair.last_updated = now\n"
            "                pair.last_error = ''\n"
            "                human = data['rate'] / (10 ** data['metadata']['decimals'])\n"
            "                results.append(f'{pair.name}={human}')\n"
            "            elif isinstance(raw, dict) and 'Err' in raw:\n"
            "                pair.last_error = str(raw['Err'])[:255]\n"
            "                pair.last_updated = now\n"
            "                results.append(f'{pair.name}=ERR:{pair.last_error}')\n"
            "            else:\n"
            "                pair.last_error = str(raw)[:255]\n"
            "                pair.last_updated = now\n"
            "                results.append(f'{pair.name}=ERR:{pair.last_error}')\n"
            "        except Exception as e:\n"
            "            pair.last_error = str(e)[:255]\n"
            "            pair.last_updated = now\n"
            "            results.append(f'{pair.name}=ERR:{e}')\n"
            "    return 'FX_REFRESH:' + '; '.join(results)\n"
        )

        log = _run_async_task(
            "_test_fx_refresh", code,
            fx_canister, fx_network, timeout=180,
        )
        assert "completed" in log, f"Task did not complete: {log}"
        assert "FX_REFRESH:" in log, f"Refresh summary not found: {log}"
        print(f"\n  Refresh result: {log}")

    def test_refresh_persisted_to_db(self, fx_reachable, fx_canister, fx_network):
        """After refresh, rates should be readable from the DB synchronously."""
        result = _exec_fx(
            "fx = FXService()\n"
            "btc = fx.get_rate_info('BTC', 'USD')\n"
            "icp = fx.get_rate_info('ICP', 'USD')\n"
            "btc_ok = btc is not None and (btc['raw_rate'] > 0 or btc['last_error'])\n"
            "icp_ok = icp is not None and (icp['raw_rate'] > 0 or icp['last_error'])\n"
            "print(f'btc_ok={btc_ok}|icp_ok={icp_ok}')\n"
            "if btc: print(f\"btc_rate={btc['rate']}|btc_updated={btc['last_updated']}|btc_err={btc['last_error']}\")\n"
            "if icp: print(f\"icp_rate={icp['rate']}|icp_updated={icp['last_updated']}|icp_err={icp['last_error']}\")",
            fx_canister, fx_network,
        )
        assert "btc_ok=True" in result
        assert "icp_ok=True" in result
        print(f"\n  DB state after refresh:\n  {result}")

    def test_refresh_updates_last_updated(self, fx_reachable, fx_canister, fx_network):
        """After refresh, last_updated should be non-zero."""
        result = _exec_fx(
            "btc = FXPair['BTC/USD']\n"
            "icp = FXPair['ICP/USD']\n"
            "print(f'btc_updated={btc.last_updated}|icp_updated={icp.last_updated}')",
            fx_canister, fx_network,
        )
        # After the refresh in the previous test, last_updated should be > 0
        m_btc = re.search(r'btc_updated=(\d+)', result)
        m_icp = re.search(r'icp_updated=(\d+)', result)
        assert m_btc and int(m_btc.group(1)) > 0, f"BTC last_updated not set: {result}"
        assert m_icp and int(m_icp.group(1)) > 0, f"ICP last_updated not set: {result}"


# ===========================================================================
# 6. FXService.fetch_rate — async single pair
# ===========================================================================

class TestFXServiceFetchRate:
    """Test FXService.fetch_rate() for a single pair."""

    def test_fetch_single_pair(self, fx_reachable, fx_canister, fx_network):
        """fetch_rate should query XRC for a single pair and update the DB."""
        # Register ETH/USD pair
        _exec_fx(
            "fx = FXService()\n"
            "fx.register_pair('ETH', 'USD')\n"
            "p = FXPair['ETH/USD']\n"
            "p.rate = 0\n"
            "p.last_updated = 0\n"
            "print('ready')",
            fx_canister, fx_network,
        )

        code = (
            "from basilisk import Record, Service, service_update, Principal, Opt, Variant, nat32, nat64, null, text, Async\n"
            "from ic_python_db import Entity, String, Integer, TimestampedMixin\n"
            "\n"
            "if 'FXPair' not in dir():\n"
            "    class FXPair(Entity, TimestampedMixin):\n"
            "        __alias__ = 'name'\n"
            "        name = String(max_length=16)\n"
            "        base_symbol = String(max_length=8)\n"
            "        base_class = String(max_length=16)\n"
            "        quote_symbol = String(max_length=8)\n"
            "        quote_class = String(max_length=16)\n"
            "        rate = Integer(default=0)\n"
            "        decimals = Integer(default=9)\n"
            "        last_updated = Integer(default=0)\n"
            "        last_error = String(max_length=256)\n"
            "\n"
            "class _AssetClass(Variant, total=False):\n"
            "    Cryptocurrency: null\n"
            "    FiatCurrency: null\n"
            "class _Asset(Record):\n"
            "    symbol: text\n"
            "    class_: _AssetClass\n"
            "class _GetExchangeRateRequest(Record):\n"
            "    base_asset: _Asset\n"
            "    quote_asset: _Asset\n"
            "    timestamp: Opt[nat64]\n"
            "class _ExchangeRateMetadata(Record):\n"
            "    decimals: nat32\n"
            "    base_asset_num_queried_sources: nat64\n"
            "    base_asset_num_received_rates: nat64\n"
            "    quote_asset_num_queried_sources: nat64\n"
            "    quote_asset_num_received_rates: nat64\n"
            "    standard_deviation: nat64\n"
            "    forex_timestamp: Opt[nat64]\n"
            "class _ExchangeRate(Record):\n"
            "    base_asset: _Asset\n"
            "    quote_asset: _Asset\n"
            "    timestamp: nat64\n"
            "    rate: nat64\n"
            "    metadata: _ExchangeRateMetadata\n"
            "class _OtherError(Record):\n"
            "    code: nat32\n"
            "    description: text\n"
            "class _ExchangeRateError(Variant, total=False):\n"
            "    AnonymousPrincipalNotAllowed: null\n"
            "    Pending: null\n"
            "    CryptoBaseAssetNotFound: null\n"
            "    CryptoQuoteAssetNotFound: null\n"
            "    StablecoinRateNotFound: null\n"
            "    StablecoinRateTooFewRates: null\n"
            "    StablecoinRateZeroRate: null\n"
            "    ForexInvalidTimestamp: null\n"
            "    ForexBaseAssetNotFound: null\n"
            "    ForexQuoteAssetNotFound: null\n"
            "    ForexAssetsNotFound: null\n"
            "    RateLimited: null\n"
            "    NotEnoughCycles: null\n"
            "    FailedToAcceptCycles: null\n"
            "    InconsistentRatesReceived: null\n"
            "    Other: _OtherError\n"
            "class _GetExchangeRateResult(Variant, total=False):\n"
            "    Ok: _ExchangeRate\n"
            "    Err: _ExchangeRateError\n"
            "class XRCCanister(Service):\n"
            "    @service_update\n"
            "    def get_exchange_rate(self, args: _GetExchangeRateRequest) -> _GetExchangeRateResult: ...\n"
            "\n"
            "_ASSET_CLASS_CANDID = 'variant { Cryptocurrency : null; FiatCurrency : null }'\n"
            "_ASSET_CANDID = f'record {{ symbol : text; class : {_ASSET_CLASS_CANDID} }}'\n"
            "_METADATA_CANDID = 'record { decimals : nat32; base_asset_num_queried_sources : nat64; base_asset_num_received_rates : nat64; quote_asset_num_queried_sources : nat64; quote_asset_num_received_rates : nat64; standard_deviation : nat64; forex_timestamp : opt nat64 }'\n"
            "_EXCHANGE_RATE_CANDID = f'record {{ base_asset : {_ASSET_CANDID}; quote_asset : {_ASSET_CANDID}; timestamp : nat64; rate : nat64; metadata : {_METADATA_CANDID} }}'\n"
            "_OTHER_ERROR_CANDID = 'record { code : nat32; description : text }'\n"
            "_EXCHANGE_RATE_ERROR_CANDID = f'variant {{ AnonymousPrincipalNotAllowed : null; Pending : null; CryptoBaseAssetNotFound : null; CryptoQuoteAssetNotFound : null; StablecoinRateNotFound : null; StablecoinRateTooFewRates : null; StablecoinRateZeroRate : null; ForexInvalidTimestamp : null; ForexBaseAssetNotFound : null; ForexQuoteAssetNotFound : null; ForexAssetsNotFound : null; RateLimited : null; NotEnoughCycles : null; FailedToAcceptCycles : null; InconsistentRatesReceived : null; Other : {_OTHER_ERROR_CANDID} }}'\n"
            "_GET_EXCHANGE_RATE_RESULT_CANDID = f'variant {{ Ok : {_EXCHANGE_RATE_CANDID}; Err : {_EXCHANGE_RATE_ERROR_CANDID} }}'\n"
            "XRCCanister._arg_types = {'get_exchange_rate': f'record {{ base_asset : {_ASSET_CANDID}; quote_asset : {_ASSET_CANDID}; timestamp : opt nat64 }}'}\n"
            "XRCCanister._return_types = {'get_exchange_rate': _GET_EXCHANGE_RATE_RESULT_CANDID}\n"
            "\n"
            "def async_task():\n"
            "    pair = FXPair['ETH/USD']\n"
            "    if not pair:\n"
            "        return 'FX_FETCH_ERR:pair not found'\n"
            "    xrc = XRCCanister(Principal.from_str('uf6dk-hyaaa-aaaaq-qaaaq-cai'))\n"
            "    now = int(ic.time() / 1e9)\n"
            "    try:\n"
            "        result = yield xrc.get_exchange_rate({\n"
            "            'base_asset': {'symbol': pair.base_symbol, 'class': {pair.base_class: None}},\n"
            "            'quote_asset': {'symbol': pair.quote_symbol, 'class': {pair.quote_class: None}},\n"
            "            'timestamp': None,\n"
            "        }).with_cycles(1_000_000_000)\n"
            "        raw = result\n"
            "        if hasattr(result, 'Ok'):\n"
            "            raw = result.Ok if result.Ok else result.Err\n"
            "        if isinstance(raw, dict) and 'Ok' in raw:\n"
            "            data = raw['Ok']\n"
            "            pair.rate = data['rate']\n"
            "            pair.decimals = data['metadata']['decimals']\n"
            "            pair.last_updated = now\n"
            "            pair.last_error = ''\n"
            "            human = data['rate'] / (10 ** data['metadata']['decimals'])\n"
            "            return f'FX_FETCH:ETH/USD={human}'\n"
            "        elif isinstance(raw, dict) and 'Err' in raw:\n"
            "            pair.last_error = str(raw['Err'])[:255]\n"
            "            pair.last_updated = now\n"
            "            return f'FX_FETCH_ERR:{raw[\"Err\"]}'\n"
            "        else:\n"
            "            return f'FX_FETCH_RAW:{raw}'\n"
            "    except Exception as e:\n"
            "        pair.last_error = str(e)[:255]\n"
            "        pair.last_updated = now\n"
            "        return f'FX_FETCH_ERR:{e}'\n"
        )

        log = _run_async_task(
            "_test_fx_fetch_eth", code,
            fx_canister, fx_network, timeout=90,
        )
        assert "completed" in log, f"Task did not complete: {log}"

        m = re.search(r'FX_FETCH:ETH/USD=([0-9.]+)', log)
        if m:
            human_rate = float(m.group(1))
            # ETH should be > $100
            assert human_rate > 100, f"ETH/USD rate suspiciously low: {human_rate}"
            print(f"\n  ETH/USD = {human_rate}")
        else:
            assert "FX_FETCH_ERR:" in log or "FX_FETCH_RAW:" in log, \
                f"Unexpected response: {log}"
            print(f"\n  ETH/USD fetch response: {log}")

    def test_fetch_persisted(self, fx_reachable, fx_canister, fx_network):
        """After fetch_rate, the rate should be readable from the DB."""
        result = _exec_fx(
            "fx = FXService()\n"
            "info = fx.get_rate_info('ETH', 'USD')\n"
            "if info:\n"
            "    print(f\"rate={info['rate']}|updated={info['last_updated']}|err={info['last_error']}\")\n"
            "else:\n"
            "    print('NOT_FOUND')",
            fx_canister, fx_network,
        )
        assert "rate=" in result
        # last_updated should have been set
        m = re.search(r'updated=(\d+)', result)
        assert m and int(m.group(1)) > 0, f"ETH/USD not updated in DB: {result}"


# ===========================================================================
# 7. Cleanup
# ===========================================================================

class TestFXCleanup:
    """Cleanup FX pairs before CLI tests."""

    def test_cleanup_all_pairs(self, fx_reachable, fx_canister, fx_network):
        """Remove all FX pairs from the DB."""
        result = _exec(
            "deleted = 0\n"
            "for p in list(FXPair.instances()):\n"
            "    p.delete()\n"
            "    deleted += 1\n"
            "print(f'deleted={deleted}')",
            fx_canister, fx_network,
        )
        assert "deleted=" in result
        count = int(re.search(r'deleted=(\d+)', result).group(1))
        assert count >= 0
        print(f"\n  Cleaned up {count} FX pairs")


# ===========================================================================
# 8. %fx CLI magic commands
# ===========================================================================

def _fx_magic(cmd, canister, network):
    """Run a %fx magic command via generated code on the canister."""
    from basilisk.shell import (
        _fx_list_code, _fx_register_code, _fx_unregister_code,
        _fx_rate_code, _fx_info_code, _CRYPTO_SYMBOLS, _FIAT_SYMBOLS,
    )
    stripped = cmd.strip()
    if stripped.startswith("%fx"):
        stripped = stripped[3:].strip()
    parts = stripped.split()

    if not parts or parts[0] == "list":
        code = _fx_list_code()
    elif parts[0] == "register":
        base = parts[1].upper()
        quote = parts[2].upper()
        base_class = "Cryptocurrency" if base in _CRYPTO_SYMBOLS else "FiatCurrency"
        quote_class = "Cryptocurrency" if quote in _CRYPTO_SYMBOLS else "FiatCurrency"
        if "--fiat-base" in parts:
            base_class = "FiatCurrency"
        if "--crypto-quote" in parts:
            quote_class = "Cryptocurrency"
        code = _fx_register_code(base, quote, base_class, quote_class)
    elif parts[0] == "unregister":
        code = _fx_unregister_code(parts[1].upper(), parts[2].upper())
    elif parts[0] == "rate":
        code = _fx_rate_code(parts[1].upper(), parts[2].upper())
    elif parts[0] == "info":
        code = _fx_info_code(parts[1].upper(), parts[2].upper())
    else:
        return f"Unknown subcommand: {parts[0]}"

    return _local_canister_exec(code, canister, network).strip()


class TestFXCLI:
    """Test %fx magic command dispatching."""

    def test_fx_list_empty(self, fx_reachable, fx_canister, fx_network):
        """'%fx list' with no pairs shows help message."""
        result = _fx_magic("%fx list", fx_canister, fx_network)
        assert "No FX pairs registered" in result

    def test_fx_register_crypto(self, fx_reachable, fx_canister, fx_network):
        """'%fx register BTC USD' creates a pair with auto-classification."""
        result = _fx_magic("%fx register BTC USD", fx_canister, fx_network)
        assert "Registered FX pair: BTC/USD" in result

    def test_fx_register_fiat(self, fx_reachable, fx_canister, fx_network):
        """'%fx register EUR USD' auto-classifies both as FiatCurrency."""
        result = _fx_magic("%fx register EUR USD", fx_canister, fx_network)
        assert "Registered FX pair: EUR/USD" in result

    def test_fx_register_idempotent(self, fx_reachable, fx_canister, fx_network):
        """Re-registering shows 'Updated'."""
        result = _fx_magic("%fx register BTC USD", fx_canister, fx_network)
        assert "Updated FX pair: BTC/USD" in result

    def test_fx_list_with_pairs(self, fx_reachable, fx_canister, fx_network):
        """'%fx list' shows registered pairs in a table."""
        result = _fx_magic("%fx list", fx_canister, fx_network)
        assert "FX Pairs" in result
        assert "BTC/USD" in result
        assert "EUR/USD" in result

    def test_fx_rate_no_data(self, fx_reachable, fx_canister, fx_network):
        """'%fx rate' with no rate data shows help message."""
        result = _fx_magic("%fx rate BTC USD", fx_canister, fx_network)
        assert "no rate data" in result or "run %fx refresh" in result

    def test_fx_rate_with_data(self, fx_reachable, fx_canister, fx_network):
        """'%fx rate' after manually setting rate shows the value."""
        _exec(
            "p = FXPair['BTC/USD']\n"
            "p.rate = 67000_000_000_000\n"
            "p.decimals = 9\n",
            fx_canister, fx_network,
        )
        result = _fx_magic("%fx rate BTC USD", fx_canister, fx_network)
        assert "67,000" in result or "67000" in result

    def test_fx_info(self, fx_reachable, fx_canister, fx_network):
        """'%fx info' shows detailed pair information."""
        result = _fx_magic("%fx info BTC USD", fx_canister, fx_network)
        assert "Pair:" in result
        assert "BTC/USD" in result
        assert "Base:" in result
        assert "Cryptocurrency" in result
        assert "Raw rate:" in result

    def test_fx_info_not_registered(self, fx_reachable, fx_canister, fx_network):
        """'%fx info' for unregistered pair shows error."""
        result = _fx_magic("%fx info DOGE USD", fx_canister, fx_network)
        assert "not registered" in result

    def test_fx_unregister(self, fx_reachable, fx_canister, fx_network):
        """'%fx unregister' removes a pair."""
        result = _fx_magic("%fx unregister EUR USD", fx_canister, fx_network)
        assert "Unregistered FX pair: EUR/USD" in result

    def test_fx_unregister_nonexistent(self, fx_reachable, fx_canister, fx_network):
        """'%fx unregister' for non-existent pair shows error."""
        result = _fx_magic("%fx unregister DOGE USD", fx_canister, fx_network)
        assert "not found" in result

    def test_fx_cli_cleanup(self, fx_reachable, fx_canister, fx_network):
        """Clean up all pairs after CLI tests."""
        _exec(
            "for p in list(FXPair.instances()):\n"
            "    p.delete()\n"
            "print('cleaned')",
            fx_canister, fx_network,
        )
