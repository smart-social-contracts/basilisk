"""
Basilisk OS — Wallet: native ICRC-1 token management for IC canisters.

Provides a high-level API for interacting with ICRC-1 tokens:

  - Token registry (register, list, get)
  - Balance queries (live from ledger, cached from local DB)
  - Transfers (outgoing ICRC-1 transfers)
  - Transaction history sync (from indexer to local DB)

All inter-canister operations (transfer, balance_of, fee, refresh) are
async generators that must be driven with ``yield``::

    from basilisk.toolkit.wallet import Wallet

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

from .entities import Token, WalletBalance, WalletSubaccount, WalletTransfer

logger = get_logger("basilisk.toolkit.wallet")

# Re-export from standalone module (no canister-side dependencies)
from .tokens import WELL_KNOWN_TOKENS  # noqa: F401


class Wallet:
    """
    Native ICRC-1 wallet for Basilisk OS canisters.

    Manages a token registry (persisted via the database layer) and provides
    async helpers for ledger and indexer interactions.

    Args:
        storage: The StableBTreeMap instance used by the database layer.
                 Must be the same storage passed to ``Database.init()``.
    """

    _pre_transfer_hook = None

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

    def register_well_known_tokens(self, *names):
        """
        Register well-known IC mainnet tokens by name.

        If no names are given, all well-known tokens are registered.

        Args:
            *names: Token symbols to register (e.g. "ckBTC", "ICP").
                    If empty, registers all tokens in WELL_KNOWN_TOKENS.

        Returns:
            List of registered Token entities.
        """
        targets = names or WELL_KNOWN_TOKENS.keys()
        tokens = []
        for name in targets:
            info = WELL_KNOWN_TOKENS.get(name)
            if info is None:
                # Try case-insensitive lookup
                for k, v in WELL_KNOWN_TOKENS.items():
                    if k.lower() == name.lower():
                        info = v
                        name = k
                        break
            if info is None:
                logger.warning(f"Unknown well-known token: {name}")
                continue
            tokens.append(self.register_token(name, **info))
        return tokens

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
    # Subaccount derivation (deterministic, no DB)
    # ------------------------------------------------------------------

    @staticmethod
    def make_subaccount(prefix, identifier):
        """
        Derive a 32-byte subaccount from a prefix and identifier.

        The subaccount is ``prefix + identifier`` encoded as UTF-8 and
        zero-padded (or truncated) to exactly 32 bytes.  The prefix
        makes subaccounts self-describing when viewed in hex.

        Common prefixes:
            ``usr_``  — per-user subaccount (identifier = principal text)
            ``inv_``  — per-invoice subaccount (identifier = invoice ID)

        Args:
            prefix: Short ASCII prefix, e.g. ``"usr_"`` or ``"inv_"``
            identifier: Arbitrary string (principal, invoice ID, etc.)

        Returns:
            32-byte ``bytes`` object suitable for ICRC-1 subaccount fields.
        """
        raw = f"{prefix}{identifier}".encode("utf-8")
        if len(raw) > 32:
            raw = raw[:32]
        return raw.ljust(32, b"\x00")

    @staticmethod
    def user_subaccount(principal):
        """Derive the canonical ``usr_`` subaccount for a principal.

        Args:
            principal: Principal ID string (e.g. ``"aaaaa-aa"``)

        Returns:
            32-byte subaccount: ``b"usr_<principal>"`` zero-padded to 32 bytes.
        """
        return Wallet.make_subaccount("usr_", principal)

    @staticmethod
    def invoice_subaccount(invoice_id):
        """Derive the canonical ``inv_`` subaccount for an invoice.

        Args:
            invoice_id: Invoice identifier string.

        Returns:
            32-byte subaccount: ``b"inv_<invoice_id>"`` zero-padded to 32 bytes.
        """
        return Wallet.make_subaccount("inv_", invoice_id)

    # ------------------------------------------------------------------
    # Subaccount registry (synchronous — local DB only)
    # ------------------------------------------------------------------

    def register_subaccount(self, token_name, subaccount_hex, label=""):
        """
        Register a subaccount for balance and transaction tracking.

        Other extensions (invoices, marketplace, etc.) should call this
        when they create subaccounts so the wallet tracks them during refresh.

        Args:
            token_name: Token symbol (e.g. "ckBTC")
            subaccount_hex: Hex-encoded 32-byte subaccount string
            label: Human-readable label (e.g. "Invoice #17f6a82d")

        Returns:
            The WalletSubaccount entity instance.
        """
        token = self._require_token(token_name)
        # Check for existing registration
        for sub in token.subaccounts:
            if sub.subaccount_hex == subaccount_hex:
                if label:
                    sub.label = label
                logger.info(f"Subaccount already registered for {token_name}: {label or subaccount_hex[:16]}")
                return sub
        sub = WalletSubaccount(
            token=token,
            subaccount_hex=subaccount_hex,
            label=label or subaccount_hex[:16],
        )
        logger.info(f"Registered subaccount for {token_name}: {label or subaccount_hex[:16]}")
        return sub

    def unregister_subaccount(self, token_name, subaccount_hex):
        """
        Remove a subaccount from tracking.

        Args:
            token_name: Token symbol
            subaccount_hex: Hex-encoded 32-byte subaccount string

        Returns:
            True if removed, False if not found.
        """
        token = self._require_token(token_name)
        for sub in token.subaccounts:
            if sub.subaccount_hex == subaccount_hex:
                sub.delete()
                logger.info(f"Unregistered subaccount for {token_name}: {subaccount_hex[:16]}")
                return True
        return False

    def list_subaccounts(self, token_name):
        """
        List all registered subaccounts for a token.

        Args:
            token_name: Token symbol

        Returns:
            List of dicts with subaccount info.
        """
        token = Token[token_name]
        if token is None:
            return []
        result = []
        for sub in token.subaccounts:
            result.append({
                "subaccount_hex": sub.subaccount_hex,
                "label": sub.label,
                "balance": sub.balance,
            })
        return result

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

    def balance_of(self, token_name, principal=None, subaccount=None):
        """
        Query the token's balance from the ledger canister (async).

        Must be called with ``yield``::

            balance = yield wallet.balance_of("ckBTC")
            balance = yield wallet.balance_of("ckBTC", subaccount=sub_bytes)

        Args:
            token_name: Token symbol
            principal: Principal ID string. Defaults to this canister's ID.
            subaccount: Optional 32-byte subaccount (bytes). Defaults to None.

        Returns:
            Generator that yields an inter-canister call and returns the balance as int.
        """
        return self._balance_of(token_name, principal, subaccount)

    def _balance_of(self, token_name, principal=None, subaccount=None) -> Async[int]:
        if principal is None:
            principal = ic.id().to_str()

        token = self._require_token(token_name)
        ledger = ICRCLedger(Principal.from_str(token.ledger))

        balance_result = yield ledger.icrc1_balance_of(
            Account(owner=Principal.from_str(principal), subaccount=subaccount)
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
        if Wallet._pre_transfer_hook is not None:
            hook_result = Wallet._pre_transfer_hook(
                token_name=token_name,
                to_principal=to_principal,
                amount=amount,
                from_subaccount=from_subaccount,
                to_subaccount=to_subaccount,
            )
            if hook_result is not None:
                logger.warning(f"Transfer blocked by pre_transfer_hook: {hook_result}")
                return {"err": hook_result}

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

    def refresh(self, token_name, max_results=100, subaccount=None):
        """
        Sync transaction history from the indexer canister (async).

        Fetches recent transactions, creates WalletTransfer entities for
        new ones, and updates cached balances.

        Must be called with ``yield``::

            summary = yield wallet.refresh("ckBTC")
            summary = yield wallet.refresh("REALMS", subaccount=sub_bytes)

        Args:
            token_name: Token symbol
            max_results: Maximum number of transactions to fetch (default 100)
            subaccount: Optional 32-byte subaccount (bytes). Defaults to None.

        Returns:
            Generator yielding inter-canister call. Returns dict:
            ``{"new_txs": int, "balance": int}``
        """
        return self._refresh(token_name, max_results, subaccount)

    def _refresh(self, token_name, max_results=100, subaccount=None) -> Async[dict]:
        token = self._require_token(token_name)
        canister_principal = ic.id().to_str()
        ledger = ICRCLedger(Principal.from_str(token.ledger))

        # --- 1. Refresh the default (or explicitly requested) account ----
        default_result = yield from self._refresh_account(
            token, ledger, canister_principal, subaccount, max_results,
        )
        total_new = default_result["new_txs"]
        default_balance = default_result["balance"]

        # --- 2. Refresh all registered subaccounts -----------------------
        sub_results = []
        if subaccount is None:
            for sub_entity in token.subaccounts:
                try:
                    sub_bytes = bytes.fromhex(sub_entity.subaccount_hex)
                    sub_res = yield from self._refresh_account(
                        token, ledger, canister_principal, sub_bytes, max_results,
                    )
                    sub_entity.balance = sub_res["balance"]
                    total_new += sub_res["new_txs"]
                    sub_results.append({
                        "subaccount_hex": sub_entity.subaccount_hex,
                        "label": sub_entity.label,
                        "balance": sub_res["balance"],
                        "new_txs": sub_res["new_txs"],
                    })
                except Exception as e:
                    logger.error(f"Subaccount refresh failed for {token_name}/{sub_entity.label}: {e}")

        aggregate_balance = default_balance + sum(s["balance"] for s in sub_results)

        logger.info(
            f"refresh({token_name}): {total_new} new txs, "
            f"default_balance={default_balance}, aggregate={aggregate_balance}, "
            f"subaccounts={len(sub_results)}"
        )
        return {
            "new_txs": total_new,
            "balance": default_balance,
            "aggregate_balance": aggregate_balance,
            "subaccounts": sub_results,
        }

    def _refresh_account(
        self, token, ledger, canister_principal, subaccount, max_results,
    ) -> Async[dict]:
        """Refresh balance + transactions for a single account (default or subaccount)."""
        token_name = token.name

        # --- Query the ledger for the authoritative balance ---
        balance_result = yield ledger.icrc1_balance_of(
            Account(
                owner=Principal.from_str(canister_principal),
                subaccount=subaccount,
            )
        )
        balance_raw = self._extract_ok_value(balance_result)
        if isinstance(balance_raw, dict) and "_call_error" in balance_raw:
            logger.error(f"Ledger balance query failed for {token_name}: {balance_raw['_call_error']}")
            balance = 0
        else:
            balance = self._to_int(balance_raw)

        # For default account, update the WalletBalance cache
        if subaccount is None:
            self._update_cached_balance(token, canister_principal, balance)

        # --- Best-effort: sync transactions from the indexer ---
        new_count = 0
        if not token.indexer:
            pass  # No indexer — balance-only
        else:
            try:
                new_count = yield from self._sync_indexer_txs(
                    token, canister_principal, subaccount, max_results,
                )
            except Exception as e:
                logger.error(f"Indexer sync failed for {token_name}: {e}")

        return {"new_txs": new_count, "balance": balance}

    def _sync_indexer_txs(
        self, token, canister_principal, subaccount, max_results,
    ) -> Async[int]:
        """Fetch transactions from the indexer for a single account. Returns new tx count."""
        indexer = ICRCIndexer(Principal.from_str(token.indexer))
        request = GetAccountTransactionsRequest(
            account=Account(
                owner=Principal.from_str(canister_principal),
                subaccount=subaccount,
            ),
            start=None,
            max_results=max_results,
        )

        result = yield indexer.get_account_transactions(request)
        raw = self._extract_ok_value(result)

        data = None
        if isinstance(raw, dict) and "_call_error" in raw:
            logger.error(f"Indexer call failed for {token.name}: {raw['_call_error']}")
        elif isinstance(raw, dict) and "Ok" in raw:
            data = raw["Ok"]
        elif isinstance(raw, dict) and "transactions" in raw:
            data = raw
        else:
            logger.warning(f"Unexpected indexer response for {token.name}: {type(raw)}")

        if data is None:
            return 0

        transactions = data.get("transactions", [])

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
                t = self._unwrap_opt(tx["transfer"])
                principal_from = self._extract_principal(t.get("from_") or t.get("from", {}))
                principal_to = self._extract_principal(t.get("to", {}))
                amount = self._to_int(t.get("amount", 0))
                raw_fee = self._unwrap_opt(t.get("fee", 0))
                fee = self._to_int(raw_fee) if raw_fee else 0
            elif kind == "mint" and tx.get("mint"):
                m = self._unwrap_opt(tx["mint"])
                principal_from = "minting_account"
                principal_to = self._extract_principal(m.get("to", {}))
                amount = self._to_int(m.get("amount", 0))
            elif kind == "burn" and tx.get("burn"):
                b = self._unwrap_opt(tx["burn"])
                principal_from = self._extract_principal(b.get("from_") or b.get("from", {}))
                principal_to = "burn"
                amount = self._to_int(b.get("amount", 0))

            self._record_transfer(
                token, tx_id, kind,
                principal_from, principal_to, amount, fee, timestamp,
            )
            new_count += 1

        return new_count

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
        Returns the Err string (prefixed) if the result is an error, so callers
        can check without exceptions (needed because the Rust shim doesn't
        propagate exceptions from nested generators back to Python try/except).
        """
        # Attribute-style CallResult (from Rust shim)
        if hasattr(result, "Ok"):
            if result.Ok is not None:
                return result.Ok
            if hasattr(result, "Err") and result.Err is not None:
                return {"_call_error": str(result.Err)}
        # Dict-style result
        if isinstance(result, dict):
            if "Ok" in result:
                return result["Ok"]
            if "Err" in result:
                return {"_call_error": str(result["Err"])}
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
    def _unwrap_opt(value):
        """Unwrap a Candid opt field: [] → None, [x] → x, other → as-is."""
        if isinstance(value, list):
            return value[0] if value else None
        return value

    @staticmethod
    def _extract_principal(account_dict):
        """Extract principal string from an Account dict."""
        if not account_dict:
            return ""
        owner = account_dict.get("owner", "")
        if hasattr(owner, "to_str"):
            return owner.to_str()
        return str(owner) if owner else ""
