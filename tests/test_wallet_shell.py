"""
Integration and unit tests for %wallet shell commands.

Unit tests (TestParseSubaccount, TestCandidSubaccount, TestHandleWalletDispatch)
run without a canister.

Integration tests (TestWalletBalance, TestWalletHistory, TestWalletOneshot)
run against a live canister on IC mainnet via dfx.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.shell import (
    _parse_subaccount,
    _candid_subaccount,
    _handle_wallet,
    _wallet_balance,
    _wallet_deposit,
    _wallet_history,
    _LEDGER_IDS,
    _LEDGER_FEES,
    _LEDGER_DECIMALS,
    _LEDGER_SYMBOLS,
    _INDEX_IDS,
)
from tests.conftest import magic_on_canister


# ===========================================================================
# Pure unit tests — no canister needed
# ===========================================================================

class TestParseSubaccount:
    """Test _parse_subaccount argument extraction."""

    def test_no_flags(self):
        cleaned, sub, from_sub = _parse_subaccount("ckbtc balance")
        assert cleaned == "ckbtc balance"
        assert sub is None
        assert from_sub is None

    def test_sub_flag(self):
        cleaned, sub, from_sub = _parse_subaccount(
            "ckbtc balance --sub 0000000000000000000000000000000000000000000000000000000000000001"
        )
        assert cleaned == "ckbtc balance"
        assert sub == "0000000000000000000000000000000000000000000000000000000000000001"
        assert from_sub is None

    def test_from_sub_flag(self):
        cleaned, sub, from_sub = _parse_subaccount(
            "ckbtc transfer 100 abc --from-sub abcd"
        )
        assert cleaned == "ckbtc transfer 100 abc"
        assert sub is None
        assert from_sub == "abcd"

    def test_both_flags(self):
        cleaned, sub, from_sub = _parse_subaccount(
            "ckbtc transfer 100 abc --sub 01 --from-sub 02"
        )
        assert cleaned == "ckbtc transfer 100 abc"
        assert sub == "01"
        assert from_sub == "02"

    def test_flags_in_middle(self):
        cleaned, sub, from_sub = _parse_subaccount(
            "ckbtc --sub ff balance"
        )
        assert cleaned == "ckbtc balance"
        assert sub == "ff"

    def test_empty_args(self):
        cleaned, sub, from_sub = _parse_subaccount("")
        assert cleaned == ""
        assert sub is None
        assert from_sub is None

    def test_flag_without_value(self):
        """--sub at the end with no value should be ignored."""
        cleaned, sub, from_sub = _parse_subaccount("ckbtc balance --sub")
        assert cleaned == "ckbtc balance --sub"
        assert sub is None


class TestCandidSubaccount:
    """Test _candid_subaccount hex-to-Candid conversion."""

    def test_none_returns_null(self):
        assert _candid_subaccount(None) == "null"

    def test_empty_string_returns_null(self):
        assert _candid_subaccount("") == "null"

    def test_valid_64_char_hex(self):
        hex_str = "00" * 32
        result = _candid_subaccount(hex_str)
        assert result.startswith("opt blob")
        assert "\\00" in result

    def test_short_hex_padded(self):
        result = _candid_subaccount("1")
        assert result is not None
        assert result.startswith("opt blob")
        # Should be padded to 64 chars (32 bytes)
        assert "\\01" in result

    def test_invalid_hex_returns_none(self):
        result = _candid_subaccount("gg" * 32)
        assert result is None

    def test_too_long_returns_none(self):
        result = _candid_subaccount("aa" * 33)  # 66 chars > 64
        assert result is None

    def test_subaccount_1(self):
        """Standard subaccount 1 encoding."""
        result = _candid_subaccount(
            "0000000000000000000000000000000000000000000000000000000000000001"
        )
        assert result.startswith("opt blob")
        assert result.endswith('"')


class TestTokenDicts:
    """Verify token dictionaries are consistent."""

    def test_all_tokens_have_all_fields(self):
        for token in _LEDGER_IDS:
            assert token in _LEDGER_FEES, f"{token} missing from _LEDGER_FEES"
            assert token in _LEDGER_DECIMALS, f"{token} missing from _LEDGER_DECIMALS"
            assert token in _LEDGER_SYMBOLS, f"{token} missing from _LEDGER_SYMBOLS"
            assert token in _INDEX_IDS, f"{token} missing from _INDEX_IDS"

    def test_ckusdc_present(self):
        assert "ckusdc" in _LEDGER_IDS
        assert _LEDGER_IDS["ckusdc"] == "xevnm-gaaaa-aaaar-qafnq-cai"
        assert _LEDGER_DECIMALS["ckusdc"] == 6
        assert _LEDGER_SYMBOLS["ckusdc"] == "ckUSDC"

    def test_ckbtc_present(self):
        assert "ckbtc" in _LEDGER_IDS
        assert _LEDGER_DECIMALS["ckbtc"] == 8

    def test_icp_present(self):
        assert "icp" in _LEDGER_IDS

    def test_cketh_present(self):
        assert "cketh" in _LEDGER_IDS


class TestHandleWalletDispatch:
    """Test _handle_wallet routing without a canister (returns usage/error strings)."""

    def test_empty_args_returns_usage(self):
        result = _handle_wallet("", "dummy", "")
        assert "Usage" in result

    def test_unknown_token_returns_error(self):
        result = _handle_wallet("badtoken balance", "dummy", "")
        assert "Unknown token" in result
        assert "Supported" in result

    def test_result_subcommand(self):
        # 'result' without a live canister will error but should not crash
        result = _handle_wallet("result", "dummy", "")
        assert isinstance(result, str)

    def test_unknown_subcommand(self):
        result = _handle_wallet("ckbtc unknowncmd", "dummy", "")
        assert "Unknown wallet command" in result

    def test_transfer_no_args_returns_usage(self):
        result = _handle_wallet("ckbtc transfer", "dummy", "")
        assert "Usage" in result

    def test_deposit_returns_instructions(self):
        result = _handle_wallet("ckbtc deposit", "test-canister-id", "")
        assert "test-canister-id" in result
        assert "deposit" in result.lower() or "Transfer" in result

    def test_deposit_ckusdc(self):
        result = _handle_wallet("ckusdc deposit", "test-canister-id", "")
        assert "ckUSDC" in result
        assert "test-canister-id" in result

    def test_deposit_with_subaccount(self):
        sub = "0000000000000000000000000000000000000000000000000000000000000001"
        result = _handle_wallet(f"ckbtc deposit --sub {sub}", "test-canister-id", "")
        assert sub in result


# ===========================================================================
# Integration tests — require live canister + dfx
# ===========================================================================

class TestWalletBalance:
    """Test %wallet balance against a live canister."""

    def test_ckbtc_balance(self, canister_reachable, canister, network):
        result = magic_on_canister("%wallet ckbtc balance", canister, network)
        assert "ckBTC" in result
        assert "e8" in result

    def test_ckusdc_balance(self, canister_reachable, canister, network):
        result = magic_on_canister("%wallet ckusdc balance", canister, network)
        assert "ckUSDC" in result
        assert "e6" in result

    def test_icp_balance(self, canister_reachable, canister, network):
        result = magic_on_canister("%wallet icp balance", canister, network)
        assert "ICP" in result
        assert "e8" in result

    def test_cketh_balance(self, canister_reachable, canister, network):
        result = magic_on_canister("%wallet cketh balance", canister, network)
        assert "ckETH" in result
        assert "e18" in result

    def test_balance_with_subaccount(self, canister_reachable, canister, network):
        sub = "0000000000000000000000000000000000000000000000000000000000000001"
        result = magic_on_canister(f"%wallet ckbtc balance --sub {sub}", canister, network)
        assert "ckBTC" in result
        assert "e8" in result

    def test_balance_invalid_subaccount(self, canister_reachable, canister, network):
        result = magic_on_canister(
            "%wallet ckbtc balance --sub gggg", canister, network
        )
        assert "Invalid" in result or "error" in result.lower()


class TestWalletHistory:
    """Test %wallet history (on-chain Index canister query)."""

    def test_ckbtc_history(self, canister_reachable, canister, network):
        result = magic_on_canister("%wallet ckbtc history", canister, network)
        # Test canister has had ckBTC transfers
        assert "ckBTC" in result
        assert "transaction history" in result.lower() or "No ckBTC" in result

    def test_ckbtc_history_has_arrows(self, canister_reachable, canister, network):
        result = magic_on_canister("%wallet ckbtc history", canister, network)
        if "transaction history" in result.lower():
            # Should have direction arrows
            assert "→" in result or "←" in result or "↔" in result

    def test_ckbtc_history_has_tx_ids(self, canister_reachable, canister, network):
        result = magic_on_canister("%wallet ckbtc history", canister, network)
        if "transaction history" in result.lower():
            assert "#" in result  # tx IDs prefixed with #

    def test_history_custom_count(self, canister_reachable, canister, network):
        result = magic_on_canister("%wallet ckbtc history 3", canister, network)
        if "transaction history" in result.lower():
            lines = [l for l in result.split("\n") if l.strip().startswith("2")]
            assert len(lines) <= 3

    def test_ckusdc_history(self, canister_reachable, canister, network):
        result = magic_on_canister("%wallet ckusdc history", canister, network)
        # May have no transactions, that's fine
        assert "ckUSDC" in result

    def test_history_with_subaccount(self, canister_reachable, canister, network):
        sub = "0000000000000000000000000000000000000000000000000000000000000001"
        result = magic_on_canister(
            f"%wallet ckbtc history --sub {sub}", canister, network
        )
        assert "ckBTC" in result


class TestWalletOneshot:
    """Test %wallet commands via subprocess one-shot mode."""

    def _run_shell(self, code, canister, network):
        cmd = [
            sys.executable, "-m", "basilisk.shell",
            "--canister", canister,
            "--network", network,
            "-c", code,
        ]
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        return r.stdout.strip(), r.stderr.strip(), r.returncode

    def test_oneshot_wallet_usage(self, canister_reachable, canister, network):
        out, err, rc = self._run_shell("%wallet", canister, network)
        assert rc == 0
        assert "Usage" in out

    def test_oneshot_ckbtc_balance(self, canister_reachable, canister, network):
        out, err, rc = self._run_shell("%wallet ckbtc balance", canister, network)
        assert rc == 0
        assert "ckBTC" in out

    def test_oneshot_ckusdc_balance(self, canister_reachable, canister, network):
        out, err, rc = self._run_shell("%wallet ckusdc balance", canister, network)
        assert rc == 0
        assert "ckUSDC" in out

    def test_oneshot_history(self, canister_reachable, canister, network):
        out, err, rc = self._run_shell("%wallet ckbtc history", canister, network)
        assert rc == 0
        assert "ckBTC" in out
