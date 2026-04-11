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
    from ic_basilisk_toolkit.tokens import WELL_KNOWN_TOKENS
    from basilisk import Principal

    ckbtc = WELL_KNOWN_TOKENS["ckBTC"]
    ledger = ICRCLedger(Principal.from_str(ckbtc["ledger"]))
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
        from ic_basilisk_toolkit.tokens import WELL_KNOWN_TOKENS
        ckbtc = WELL_KNOWN_TOKENS["ckBTC"]
        ledger = ICRCLedger(Principal.from_str(ckbtc["ledger"]))
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


# Candid type strings for typed encoding/decoding of inter-canister calls.
# Without these, the Rust Candid decoder falls back to typeless decoding
# which returns hashed field names (_NNNN) instead of proper names.
_ACCOUNT_CANDID = 'record { owner : principal; subaccount : opt blob }'
_SPENDER_CANDID = 'record { owner : principal; subaccount : opt blob }'
_TRANSFER_ERROR_CANDID = (
    'variant { BadFee : record { expected_fee : nat }; '
    'BadBurn : record { min_burn_amount : nat }; '
    'InsufficientFunds : record { balance : nat }; '
    'TooOld : null; CreatedInFuture : null; '
    'Duplicate : record { duplicate_of : nat }; '
    'TemporarilyUnavailable : null; '
    'GenericError : record { error_code : nat; message : text } }'
)
_TRANSFER_TX_CANDID = (
    f'record {{ to : {_ACCOUNT_CANDID}; fee : opt nat; '
    f'from : {_ACCOUNT_CANDID}; memo : opt vec nat; '
    f'created_at_time : opt nat64; amount : nat; '
    f'spender : opt {_SPENDER_CANDID} }}'
)
_MINT_TX_CANDID = (
    f'record {{ to : {_ACCOUNT_CANDID}; memo : opt vec nat; '
    f'created_at_time : opt nat64; amount : nat }}'
)
_BURN_TX_CANDID = (
    f'record {{ from : {_ACCOUNT_CANDID}; memo : opt vec nat; '
    f'created_at_time : opt nat64; amount : nat; '
    f'spender : opt {_SPENDER_CANDID} }}'
)
_APPROVE_CANDID = (
    f'record {{ fee : opt nat; from : {_ACCOUNT_CANDID}; '
    f'memo : opt vec nat; created_at_time : opt nat64; amount : nat; '
    f'expected_allowance : opt nat; expires_at : opt nat64; '
    f'spender : {_SPENDER_CANDID} }}'
)
_TRANSACTION_CANDID = (
    f'record {{ burn : opt {_BURN_TX_CANDID}; kind : text; '
    f'mint : opt {_MINT_TX_CANDID}; approve : opt {_APPROVE_CANDID}; '
    f'timestamp : nat64; transfer : opt {_TRANSFER_TX_CANDID} }}'
)
_ACCOUNT_TX_CANDID = f'record {{ id : nat; transaction : {_TRANSACTION_CANDID} }}'
_GET_TX_RESPONSE_CANDID = (
    f'record {{ balance : nat; transactions : vec {_ACCOUNT_TX_CANDID}; '
    f'oldest_tx_id : opt nat }}'
)
_GET_TX_RESULT_CANDID = (
    f'variant {{ Ok : {_GET_TX_RESPONSE_CANDID}; Err : text }}'
)

ICRCLedger._arg_types = {
    'icrc1_balance_of': _ACCOUNT_CANDID,
    'icrc1_transfer': (
        f'record {{ to : {_ACCOUNT_CANDID}; fee : opt nat; memo : opt blob; '
        f'from_subaccount : opt blob; created_at_time : opt nat64; amount : nat }}'
    ),
}
ICRCLedger._return_types = {
    'icrc1_balance_of': 'nat',
    'icrc1_fee': 'nat',
    'icrc1_transfer': f'variant {{ Ok : nat; Err : {_TRANSFER_ERROR_CANDID} }}',
}


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


ICRCIndexer._arg_types = {
    'get_account_transactions': (
        f'record {{ account : {_ACCOUNT_CANDID}; start : opt nat; max_results : nat }}'
    ),
}
ICRCIndexer._return_types = {
    'get_account_transactions': _GET_TX_RESULT_CANDID,
}
