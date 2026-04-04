"""
Unit tests for Wallet._pre_transfer_hook — the OS-level choke point
for all outgoing token transfers.

These tests verify:
  1. Hook blocks transfers when it returns a non-None value
  2. Hook allows transfers when it returns None
  3. Hook receives correct arguments
  4. No hook set (None) means transfers proceed
  5. Hook is reset between tests (no leakage)
  6. Hook returning various error types is handled

These are unit tests that do NOT require a running dfx replica.
They test the hook dispatch logic, not the actual ICRC-1 transfer.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from basilisk.os.wallet import Wallet
except ImportError:
    pytest.skip(
        "basilisk.os.wallet requires canister-only modules (basilisk.logging)",
        allow_module_level=True,
    )


@pytest.fixture(autouse=True)
def reset_hook():
    """Ensure _pre_transfer_hook is reset before and after every test."""
    Wallet._pre_transfer_hook = None
    yield
    Wallet._pre_transfer_hook = None


class TestPreTransferHookDispatch:
    """Test that _transfer() correctly calls and respects the hook."""

    def test_no_hook_set_proceeds(self):
        """When _pre_transfer_hook is None, _transfer should not be blocked by the hook."""
        assert Wallet._pre_transfer_hook is None

    def test_hook_returning_none_allows(self):
        """A hook that returns None should not block the transfer."""
        calls = []

        def allow_hook(**kwargs):
            calls.append(kwargs)
            return None

        Wallet._pre_transfer_hook = allow_hook

        # Call the hook directly as _transfer would
        result = Wallet._pre_transfer_hook(
            token_name="ckBTC",
            to_principal="abc-def",
            amount=1000,
            from_subaccount=None,
            to_subaccount=None,
        )
        assert result is None
        assert len(calls) == 1
        assert calls[0]["token_name"] == "ckBTC"
        assert calls[0]["to_principal"] == "abc-def"
        assert calls[0]["amount"] == 1000

    def test_hook_returning_string_blocks(self):
        """A hook that returns a string error should block the transfer."""
        def block_hook(**kwargs):
            return "Access denied: no permission"

        Wallet._pre_transfer_hook = block_hook

        result = Wallet._pre_transfer_hook(
            token_name="ckBTC",
            to_principal="abc-def",
            amount=1000,
            from_subaccount=None,
            to_subaccount=None,
        )
        assert result == "Access denied: no permission"

    def test_hook_returning_dict_blocks(self):
        """A hook that returns a dict error should block the transfer."""
        def block_hook(**kwargs):
            return {"code": "UNAUTHORIZED", "message": "Not allowed"}

        Wallet._pre_transfer_hook = block_hook

        result = Wallet._pre_transfer_hook(
            token_name="ckBTC",
            to_principal="abc-def",
            amount=500,
            from_subaccount=None,
            to_subaccount=None,
        )
        assert result is not None
        assert result["code"] == "UNAUTHORIZED"

    def test_hook_receives_all_arguments(self):
        """The hook should receive token_name, to_principal, amount, from_subaccount, to_subaccount."""
        captured = {}

        def capture_hook(**kwargs):
            captured.update(kwargs)
            return None

        Wallet._pre_transfer_hook = capture_hook

        sub_from = b"\x01" * 32
        sub_to = b"\x02" * 32
        Wallet._pre_transfer_hook(
            token_name="ICP",
            to_principal="xyz-123",
            amount=999,
            from_subaccount=sub_from,
            to_subaccount=sub_to,
        )

        assert captured["token_name"] == "ICP"
        assert captured["to_principal"] == "xyz-123"
        assert captured["amount"] == 999
        assert captured["from_subaccount"] == sub_from
        assert captured["to_subaccount"] == sub_to

    def test_hook_reset_between_tests(self):
        """Verify the autouse fixture resets the hook (no leakage from prior test)."""
        assert Wallet._pre_transfer_hook is None

    def test_hook_can_be_replaced(self):
        """The hook can be swapped at runtime (e.g., different realm policies)."""
        def hook_v1(**kwargs):
            return "blocked by v1"

        def hook_v2(**kwargs):
            return None

        Wallet._pre_transfer_hook = hook_v1
        assert Wallet._pre_transfer_hook(token_name="X", to_principal="Y", amount=1,
                                          from_subaccount=None, to_subaccount=None) == "blocked by v1"

        Wallet._pre_transfer_hook = hook_v2
        assert Wallet._pre_transfer_hook(token_name="X", to_principal="Y", amount=1,
                                          from_subaccount=None, to_subaccount=None) is None


class TestPreTransferHookInTransfer:
    """Test that _transfer() integrates the hook correctly.

    Since _transfer() is an async generator that requires a real ledger,
    we test the hook blocking path which returns early (before the yield).
    """

    def test_transfer_blocked_by_hook_returns_err(self):
        """When the hook blocks, _transfer must return {"err": ...} without yielding."""
        def deny_all(**kwargs):
            return "Denied by policy"

        Wallet._pre_transfer_hook = deny_all
        wallet = Wallet()

        # _transfer is a generator; if the hook blocks, it should return
        # immediately without yielding (no inter-canister call).
        gen = wallet._transfer("ckBTC", "target-principal", 1000)

        # A blocked transfer returns a plain dict, not a generator that yields.
        # Since the hook blocks before the yield, the generator should return
        # the error on first next() via StopIteration.
        try:
            result = next(gen)
            # If we get here, gen yielded something — that means the hook didn't block.
            # This should NOT happen.
            pytest.fail(f"Expected StopIteration (hook should block), but got yielded value: {result}")
        except StopIteration as e:
            # The return value of the generator is in e.value
            assert e.value == {"err": "Denied by policy"}

    def test_transfer_allowed_by_hook_proceeds_to_yield(self):
        """When hook returns None, _transfer should proceed past the hook (and yield for ledger call)."""
        def allow_all(**kwargs):
            return None

        Wallet._pre_transfer_hook = allow_all
        wallet = Wallet()

        # This will fail at _require_token since no token is registered,
        # which proves the hook allowed execution to continue past itself.
        with pytest.raises(ValueError, match="not registered"):
            gen = wallet._transfer("NonExistentToken", "target", 100)
            next(gen)

    def test_transfer_no_hook_proceeds_to_yield(self):
        """When no hook is set, _transfer should proceed (and fail at token lookup)."""
        assert Wallet._pre_transfer_hook is None
        wallet = Wallet()

        with pytest.raises(ValueError, match="not registered"):
            gen = wallet._transfer("NonExistentToken", "target", 100)
            next(gen)
