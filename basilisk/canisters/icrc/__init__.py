"""
Basilisk ICRC — Candid types and service definitions for ICRC-1/ICRC-2 tokens.

Provides typed Python interfaces for interacting with ICRC-compliant ledger
and indexer canisters on the Internet Computer:

  - Account, TransferArg, TransferResult — ICRC-1 transfer types
  - Approve, Allowance — ICRC-2 approval types
  - ICRCLedger — Service proxy for ledger canisters (ckBTC, ckETH, etc.)
  - ICRCIndexer — Service proxy for indexer canisters (transaction history)

Usage inside a canister::

    from basilisk.canisters.icrc import ICRCLedger, Account
    from basilisk import Principal

    ledger = ICRCLedger(Principal.from_str("mxzaz-hqaaa-aaaar-qaada-cai"))
    balance = yield ledger.icrc1_balance_of(
        Account(owner=ic.id(), subaccount=None)
    )
"""

from basilisk import (
    Async,
    Opt,
    Principal,
    Record,
    Service,
    Variant,
    Vec,
    blob,
    nat,
    nat64,
    null,
    service_query,
    service_update,
    text,
)


# ---------------------------------------------------------------------------
# ICRC-1 Account
# ---------------------------------------------------------------------------

class Account(Record):
    """ICRC-1 standard account: owner principal + optional 32-byte subaccount."""
    owner: Principal
    subaccount: Opt[blob]


# ---------------------------------------------------------------------------
# ICRC-1 Transfer
# ---------------------------------------------------------------------------

class TransferArg(Record):
    """Arguments for an ICRC-1 transfer operation."""
    to: Account
    fee: Opt[nat]
    memo: Opt[blob]
    from_subaccount: Opt[blob]
    created_at_time: Opt[nat64]
    amount: nat


class BadFee(Record):
    expected_fee: nat


class BadBurn(Record):
    min_burn_amount: nat


class InsufficientFunds(Record):
    balance: nat


class Duplicate(Record):
    duplicate_of: nat


class GenericError(Record):
    error_code: nat
    message: str


class TransferError(Variant, total=False):
    """ICRC-1 transfer error variants."""
    BadFee: BadFee
    BadBurn: BadBurn
    InsufficientFunds: InsufficientFunds
    TooOld: null
    CreatedInFuture: null
    Duplicate: Duplicate
    TemporarilyUnavailable: null
    GenericError: GenericError


class TransferResult(Variant, total=False):
    """ICRC-1 transfer result: Ok(nat) = transaction index, Err(TransferError)."""
    Ok: nat
    Err: TransferError


# ---------------------------------------------------------------------------
# ICRC-2 Approval (for approve/transfer_from flows)
# ---------------------------------------------------------------------------

class Spender(Record):
    """Spender account for ICRC-2 approvals."""
    owner: Principal
    subaccount: Opt[blob]


class Approve(Record):
    """ICRC-2 approval operation record."""
    fee: Opt[nat]
    from_: Account
    memo: Opt[Vec[nat]]
    created_at_time: Opt[nat64]
    amount: nat
    expected_allowance: Opt[nat]
    expires_at: Opt[nat64]
    spender: Spender


# ---------------------------------------------------------------------------
# Transaction types (returned by indexer)
# ---------------------------------------------------------------------------

class TransferTx(Record):
    """Transfer transaction details from the indexer."""
    to: Account
    fee: Opt[nat]
    from_: Account
    memo: Opt[Vec[nat]]
    created_at_time: Opt[nat64]
    amount: nat
    spender: Opt[Spender]


class MintTx(Record):
    """Mint transaction details from the indexer."""
    to: Account
    memo: Opt[Vec[nat]]
    created_at_time: Opt[nat64]
    amount: nat


class BurnTx(Record):
    """Burn transaction details from the indexer."""
    from_: Account
    memo: Opt[Vec[nat]]
    created_at_time: Opt[nat64]
    amount: nat
    spender: Opt[Spender]


class Transaction(Record):
    """Comprehensive transaction record from the indexer."""
    burn: Opt[BurnTx]
    kind: str
    mint: Opt[MintTx]
    approve: Opt[Approve]
    timestamp: nat64
    transfer: Opt[TransferTx]


class AccountTransaction(Record):
    """Transaction associated with a specific account, includes tx ID."""
    id: nat
    transaction: Transaction


# ---------------------------------------------------------------------------
# Indexer request/response types
# ---------------------------------------------------------------------------

class GetAccountTransactionsRequest(Record):
    """Request parameters for retrieving account transaction history."""
    account: Account
    start: Opt[nat]
    max_results: nat


class GetAccountTransactionsResponse(Record):
    """Response containing transaction history for an account."""
    balance: nat
    transactions: Vec[AccountTransaction]
    oldest_tx_id: Opt[nat]


class GetTransactionsResult(Variant):
    """Result of a get_transactions request."""
    Ok: GetAccountTransactionsResponse
    Err: str


# ---------------------------------------------------------------------------
# Service definitions
# ---------------------------------------------------------------------------

class ICRCLedger(Service):
    """
    Service proxy for an ICRC-1 token ledger canister.

    Usage::

        from basilisk.canisters.icrc import ICRCLedger, Account
        ledger = ICRCLedger(Principal.from_str("mxzaz-hqaaa-aaaar-qaada-cai"))
        balance = yield ledger.icrc1_balance_of(
            Account(owner=my_principal, subaccount=None)
        )
    """

    @service_query
    def icrc1_balance_of(self, account: Account) -> nat: ...

    @service_query
    def icrc1_fee(self) -> nat: ...

    @service_update
    def icrc1_transfer(self, args: TransferArg) -> TransferResult: ...


class ICRCIndexer(Service):
    """
    Service proxy for an ICRC token indexer canister.

    Usage::

        from basilisk.canisters.icrc import ICRCIndexer, Account, GetAccountTransactionsRequest
        indexer = ICRCIndexer(Principal.from_str("n5wcd-faaaa-aaaar-qaaea-cai"))
        result = yield indexer.get_account_transactions(
            GetAccountTransactionsRequest(
                account=Account(owner=my_principal, subaccount=None),
                start=None,
                max_results=100,
            )
        )
    """

    @service_query
    def get_account_transactions(
        self, request: GetAccountTransactionsRequest
    ) -> Async[GetTransactionsResult]: ...
