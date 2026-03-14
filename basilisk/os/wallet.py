"""
Basilisk OS — Wallet: native ICRC-1 token management for IC canisters.

Provides a high-level API for interacting with ICRC-1 tokens:

  - Token registry (register, list, get)
  - Balance queries (live from ledger, cached from local DB)
  - Transfers (outgoing ICRC-1 transfers)
  - Transaction history sync (from indexer to local DB)

All inter-canister operations (transfer, balance_of, fee, refresh) are
async generators that must be driven with ``yield``::

    from basilisk.os.wallet import Wallet

    wallet = Wallet(storage)
    wallet.register_token("ckBTC", ledger="mxzaz-hqaaa-aaaar-qaada-cai",
                          indexer="n5wcd-faaaa-aaaar-qaaea-cai")

    # In an @update endpoint:
    balance = yield wallet.balance_of("ckBTC")
    result = yield wallet.transfer("ckBTC", to_principal, 1000)
"""

import traceback

from basilisk import Async, Principal, ic, match
from basilisk.canisters.icrc import (
    Account,
    GetAccountTransactionsRequest,
    ICRCIndexer,
    ICRCLedger,
    TransferArg,
)
from ic_python_logging import get_logger

from .entities import Token, WalletBalance, WalletTransfer

logger = get_logger("basilisk.os.wallet")


class Wallet:
    """
    Native ICRC-1 wallet for Basilisk OS canisters.

    Manages a token registry (persisted via ic-python-db) and provides
    async helpers for ledger and indexer interactions.

    Args:
        storage: The StableBTreeMap instance used by ic-python-db.
                 Must be the same storage passed to ``Database.init()``.
    """

    def __init__(self, storage=None):
        self._storage = storage

    # ------------------------------------------------------------------
    # Token registry (synchronous — local DB only)
    # ------------------------------------------------------------------

    def register_token(
        self,
        name,
        ledger,
        indexer="",
        decimals=8,
        fee=10,
    ):
        """
        Register or update an ICRC-1 token in the local registry.

        If a token with the same name already exists, its fields are updated.

        Args:
            name: Token symbol (e.g. "ckBTC", "ckETH")
            ledger: Ledger canister principal ID string
            indexer: Indexer canister principal ID string (optional)
            decimals: Number of decimal places (default 8)
            fee: Default transfer fee in smallest units (default 10)

        Returns:
            The Token entity instance.
        """
        token = Token[name]
        if token is None:
            token = Token(
                name=name,
                ledger=ledger,
                indexer=indexer,
                decimals=decimals,
                fee=fee,
            )
            logger.info(f"Registered token: {name} (ledger={ledger})")
        else:
            token.ledger = ledger
            token.indexer = indexer
            token.decimals = decimals
            token.fee = fee
            logger.info(f"Updated token: {name} (ledger={ledger})")
        return token

    def get_token(self, name):
        """
        Look up a registered token by name.

        Args:
            name: Token symbol (e.g. "ckBTC")

        Returns:
            Token entity or None if not found.
        """
        return Token[name]

    def list_tokens(self):
        """
        List all registered tokens.

        Returns:
            List of dicts with token info.
        """
        tokens = []
        for token in Token.instances():
            tokens.append({
                "name": token.name,
                "ledger": token.ledger,
                "indexer": token.indexer,
                "decimals": token.decimals,
                "fee": token.fee,
            })
        return tokens

    # ------------------------------------------------------------------
    # Cached balance (synchronous — local DB only)
    # ------------------------------------------------------------------

    def cached_balance(self, token_name, principal=None):
        """
        Read the locally cached balance for a token/principal pair.

        This does NOT make an inter-canister call. Use ``balance_of()``
        to query the ledger directly.

        Args:
            token_name: Token symbol (e.g. "ckBTC")
            principal: Principal ID string. Defaults to this canister's ID.

        Returns:
            Cached balance as int, or 0 if not found.
        """
        if principal is None:
            principal = ic.id().to_str()
        token = Token[token_name]
        if token is None:
            return 0
        for bal in token.balances:
            if bal.principal == principal:
                return bal.amount
        return 0

    def list_transfers(self, token_name, limit=20):
        """
        List locally cached transfer records for a token.

        Args:
            token_name: Token symbol (e.g. "ckBTC")
            limit: Maximum number of transfers to return (most recent first).

        Returns:
            List of dicts with transfer info.
        """
        token = Token[token_name]
        if token is None:
            return []
        transfers = []
        for t in token.transfers:
            transfers.append({
                "tx_id": t.tx_id,
                "kind": t.kind,
                "from": t.principal_from,
                "to": t.principal_to,
                "amount": t.amount,
                "fee": t.fee,
                "timestamp": t.timestamp,
            })
        # Sort by timestamp descending, return latest
        transfers.sort(key=lambda x: x["timestamp"], reverse=True)
        return transfers[:limit]

    # ------------------------------------------------------------------
    # Async: balance query (inter-canister call)
    # ------------------------------------------------------------------

    def balance_of(self, token_name, principal=None):
        """
        Query the token's balance from the ledger canister (async).

        Must be called with ``yield``::

            balance = yield wallet.balance_of("ckBTC")

        Args:
            token_name: Token symbol
            principal: Principal ID string. Defaults to this canister's ID.

        Returns:
            Generator that yields an inter-canister call and returns the balance as int.
        """
        return self._balance_of(token_name, principal)

    def _balance_of(self, token_name, principal=None) -> Async[int]:
        if principal is None:
            principal = ic.id().to_str()

        token = self._require_token(token_name)
        ledger = ICRCLedger(Principal.from_str(token.ledger))

        balance_result = yield ledger.icrc1_balance_of(
            Account(owner=Principal.from_str(principal), subaccount=None)
        )

        balance = self._extract_ok_value(balance_result)
        balance_int = self._to_int(balance)

        # Update cached balance
        self._update_cached_balance(token, principal, balance_int)

        logger.info(f"balance_of({token_name}, {principal}) = {balance_int}")
        return balance_int

    # ------------------------------------------------------------------
    # Async: fee query (inter-canister call)
    # ------------------------------------------------------------------

    def fee(self, token_name):
        """
        Query the transfer fee from the ledger canister (async).

        Must be called with ``yield``::

            fee = yield wallet.fee("ckBTC")

        Returns:
            Generator that yields an inter-canister call and returns the fee as int.
        """
        return self._fee(token_name)

    def _fee(self, token_name) -> Async[int]:
        token = self._require_token(token_name)
        ledger = ICRCLedger(Principal.from_str(token.ledger))

        fee_result = yield ledger.icrc1_fee()
        fee_int = self._to_int(self._extract_ok_value(fee_result))

        logger.info(f"fee({token_name}) = {fee_int}")
        return fee_int

    # ------------------------------------------------------------------
    # Async: transfer (inter-canister call)
    # ------------------------------------------------------------------

    def transfer(
        self,
        token_name,
        to_principal,
        amount,
        from_subaccount=None,
        to_subaccount=None,
        memo=None,
    ):
        """
        Perform an ICRC-1 transfer (async).

        Must be called with ``yield``::

            result = yield wallet.transfer("ckBTC", "abc-...", 1000)

        Args:
            token_name: Token symbol
            to_principal: Recipient principal ID string
            amount: Amount in smallest units (e.g. satoshis for ckBTC)
            from_subaccount: Optional source subaccount bytes
            to_subaccount: Optional destination subaccount bytes
            memo: Optional memo bytes

        Returns:
            Generator yielding inter-canister call. Returns dict:
            ``{"ok": tx_id}`` on success or ``{"err": error_dict}`` on failure.
        """
        return self._transfer(
            token_name, to_principal, amount,
            from_subaccount, to_subaccount, memo,
        )

    def _transfer(
        self, token_name, to_principal, amount,
        from_subaccount=None, to_subaccount=None, memo=None,
    ) -> Async[dict]:
        token = self._require_token(token_name)
        ledger = ICRCLedger(Principal.from_str(token.ledger))

        to_account = Account(
            owner=Principal.from_str(to_principal),
            subaccount=to_subaccount,
        )
        args = TransferArg(
            to=to_account,
            fee=None,
            memo=memo,
            from_subaccount=from_subaccount,
            created_at_time=None,
            amount=amount,
        )

        logger.info(
            f"transfer({token_name}, to={to_principal}, amount={amount})"
        )

        transfer_result = yield ledger.icrc1_transfer(args)

        raw = self._extract_ok_value(transfer_result)

        # Check for Ok/Err variant
        if isinstance(raw, dict):
            if "Ok" in raw:
                tx_id = raw["Ok"]
                self._record_transfer(
                    token, str(tx_id), "transfer",
                    ic.id().to_str(), to_principal, amount, token.fee,
                )
                logger.info(f"Transfer succeeded: tx_id={tx_id}")
                return {"ok": tx_id}
            elif "Err" in raw:
                logger.error(f"Transfer failed: {raw['Err']}")
                return {"err": raw["Err"]}

        # Fallback: treat as tx_id directly
        tx_id = self._to_int(raw)
        self._record_transfer(
            token, str(tx_id), "transfer",
            ic.id().to_str(), to_principal, amount, token.fee,
        )
        logger.info(f"Transfer succeeded: tx_id={tx_id}")
        return {"ok": tx_id}

    # ------------------------------------------------------------------
    # Async: refresh transactions from indexer
    # ------------------------------------------------------------------

    def refresh(self, token_name, max_results=100):
        """
        Sync transaction history from the indexer canister (async).

        Fetches recent transactions, creates WalletTransfer entities for
        new ones, and updates cached balances.

        Must be called with ``yield``::

            summary = yield wallet.refresh("ckBTC")

        Returns:
            Generator yielding inter-canister call. Returns dict:
            ``{"new_txs": int, "balance": int}``
        """
        return self._refresh(token_name, max_results)

    def _refresh(self, token_name, max_results=100) -> Async[dict]:
        token = self._require_token(token_name)
        canister_principal = ic.id().to_str()

        if not token.indexer:
            logger.warning(f"No indexer configured for {token_name}")
            return {"new_txs": 0, "balance": self.cached_balance(token_name)}

        indexer = ICRCIndexer(Principal.from_str(token.indexer))
        request = GetAccountTransactionsRequest(
            account=Account(
                owner=Principal.from_str(canister_principal),
                subaccount=None,
            ),
            start=None,
            max_results=max_results,
        )

        result = yield indexer.get_account_transactions(request)
        raw = self._extract_ok_value(result)

        # Parse the response
        if isinstance(raw, dict) and "Ok" in raw:
            data = raw["Ok"]
        elif isinstance(raw, dict) and "transactions" in raw:
            data = raw
        else:
            logger.error(f"Unexpected indexer response: {type(raw)}")
            return {"new_txs": 0, "balance": self.cached_balance(token_name)}

        balance = self._to_int(data.get("balance", 0))
        transactions = data.get("transactions", [])

        # Collect existing tx_ids to avoid duplicates
        existing_tx_ids = set()
        for t in token.transfers:
            existing_tx_ids.add(t.tx_id)

        new_count = 0
        for tx_record in transactions:
            tx_id = str(tx_record.get("id", ""))
            if tx_id in existing_tx_ids:
                continue

            tx = tx_record.get("transaction", {})
            kind = tx.get("kind", "unknown")
            timestamp = self._to_int(tx.get("timestamp", 0))

            principal_from = ""
            principal_to = ""
            amount = 0
            fee = 0

            if kind == "transfer" and tx.get("transfer"):
                t = tx["transfer"]
                principal_from = self._extract_principal(t.get("from_", {}))
                principal_to = self._extract_principal(t.get("to", {}))
                amount = self._to_int(t.get("amount", 0))
                fee = self._to_int(t.get("fee", 0)) if t.get("fee") else 0
            elif kind == "mint" and tx.get("mint"):
                m = tx["mint"]
                principal_from = "minting_account"
                principal_to = self._extract_principal(m.get("to", {}))
                amount = self._to_int(m.get("amount", 0))
            elif kind == "burn" and tx.get("burn"):
                b = tx["burn"]
                principal_from = self._extract_principal(b.get("from_", {}))
                principal_to = "burn"
                amount = self._to_int(b.get("amount", 0))

            self._record_transfer(
                token, tx_id, kind,
                principal_from, principal_to, amount, fee, timestamp,
            )
            new_count += 1

        # Update cached balance from ledger
        self._update_cached_balance(token, canister_principal, balance)

        logger.info(
            f"refresh({token_name}): {new_count} new txs, balance={balance}"
        )
        return {"new_txs": new_count, "balance": balance}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_token(self, name):
        """Get a token by name or raise ValueError."""
        token = Token[name]
        if token is None:
            raise ValueError(f"Token '{name}' not registered. Call wallet.register_token() first.")
        return token

    def _update_cached_balance(self, token, principal, amount):
        """Create or update the WalletBalance entity for a token/principal."""
        for bal in token.balances:
            if bal.principal == principal:
                bal.amount = amount
                return
        WalletBalance(principal=principal, token=token, amount=amount)

    def _record_transfer(
        self, token, tx_id, kind,
        principal_from, principal_to, amount, fee=0, timestamp=0,
    ):
        """Create a WalletTransfer entity."""
        if timestamp == 0:
            try:
                timestamp = ic.time()
            except Exception:
                pass
        WalletTransfer(
            token=token,
            tx_id=tx_id,
            kind=kind,
            principal_from=principal_from,
            principal_to=principal_to,
            amount=amount,
            fee=fee,
            timestamp=timestamp,
        )

    @staticmethod
    def _extract_ok_value(result):
        """
        Extract the inner value from a CallResult.

        Handles both attribute-style (result.Ok) and dict-style (result["Ok"]).
        """
        if hasattr(result, "Ok") and result.Ok is not None:
            return result.Ok
        if isinstance(result, dict) and "Ok" in result:
            return result["Ok"]
        return result

    @staticmethod
    def _to_int(value):
        """Convert a value to int, handling string representations."""
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value.replace("_", ""))
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _extract_principal(account_dict):
        """Extract principal string from an Account dict."""
        if not account_dict:
            return ""
        owner = account_dict.get("owner", "")
        if hasattr(owner, "to_str"):
            return owner.to_str()
        return str(owner) if owner else ""
