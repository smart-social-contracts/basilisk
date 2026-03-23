"""
Basilisk OS — FX Rate Service: periodic exchange rate queries via the IC XRC canister.

Provides a high-level API for managing exchange rate pairs and querying
rates from the IC Exchange Rate Canister (XRC):

  - Pair registration (register, unregister, list)
  - Rate queries (synchronous from local DB, async from XRC)
  - Periodic refresh of all registered pairs

All inter-canister operations (refresh, fetch_rate) are async generators
that must be driven with ``yield``::

    from basilisk.os.fx import FXService

    fx = FXService()
    fx.register_pair("BTC", "USD")
    fx.register_pair("ICP", "USD")

    # In an @update endpoint:
    summary = yield fx.refresh()

    # Synchronous read from DB (no inter-canister call):
    rate = fx.get_rate("BTC", "USD")
"""

import traceback

from basilisk import Async, Principal, ic
from basilisk.canisters.xrc import (
    XRCCanister,
    XRC_CANISTER_ID,
)
from ic_python_logging import get_logger

from .entities import FXPair

logger = get_logger("basilisk.os.fx")

# Cycles to attach per XRC call (1B required, per XRC spec)
XRC_CYCLES_PER_CALL = 1_000_000_000

# Default refresh interval: 4 hours in seconds
DEFAULT_REFRESH_INTERVAL = 14400


class FXService:
    """
    FX rate service for Basilisk OS canisters.

    Manages a registry of FX pairs (persisted via ic-python-db) and provides
    async helpers for querying the IC Exchange Rate Canister.

    Rates are cached in ``FXPair`` entities and can be read synchronously
    by any extension without an inter-canister call.
    """

    def __init__(self, xrc_canister_id=None):
        cid = xrc_canister_id or XRC_CANISTER_ID
        self._xrc = XRCCanister(Principal.from_str(cid))

    # ------------------------------------------------------------------
    # Pair registry (synchronous — local DB only)
    # ------------------------------------------------------------------

    def register_pair(
        self,
        base_symbol,
        quote_symbol,
        base_class="Cryptocurrency",
        quote_class="FiatCurrency",
    ):
        """
        Register an FX pair for periodic rate tracking.

        If a pair with the same name already exists, its fields are updated.

        Args:
            base_symbol: Base asset symbol (e.g. "BTC", "ICP")
            quote_symbol: Quote asset symbol (e.g. "USD", "EUR")
            base_class: Asset class — "Cryptocurrency" or "FiatCurrency"
            quote_class: Asset class — "Cryptocurrency" or "FiatCurrency"

        Returns:
            The FXPair entity instance.
        """
        name = f"{base_symbol}/{quote_symbol}"
        pair = FXPair[name]
        if pair is None:
            pair = FXPair(
                name=name,
                base_symbol=base_symbol,
                base_class=base_class,
                quote_symbol=quote_symbol,
                quote_class=quote_class,
            )
            logger.info(f"Registered FX pair: {name}")
        else:
            pair.base_symbol = base_symbol
            pair.base_class = base_class
            pair.quote_symbol = quote_symbol
            pair.quote_class = quote_class
            logger.info(f"Updated FX pair: {name}")
        return pair

    def unregister_pair(self, base_symbol, quote_symbol):
        """
        Remove an FX pair from tracking.

        Args:
            base_symbol: Base asset symbol (e.g. "BTC")
            quote_symbol: Quote asset symbol (e.g. "USD")

        Returns:
            True if removed, False if not found.
        """
        name = f"{base_symbol}/{quote_symbol}"
        pair = FXPair[name]
        if pair is None:
            logger.warning(f"FX pair not found: {name}")
            return False
        pair.delete()
        logger.info(f"Unregistered FX pair: {name}")
        return True

    def get_pair(self, base_symbol, quote_symbol):
        """
        Look up a registered FX pair by symbols.

        Args:
            base_symbol: Base asset symbol
            quote_symbol: Quote asset symbol

        Returns:
            FXPair entity or None if not found.
        """
        return FXPair[f"{base_symbol}/{quote_symbol}"]

    def list_pairs(self):
        """
        List all registered FX pairs with their latest rates.

        Returns:
            List of dicts with pair info.
        """
        pairs = []
        for pair in FXPair.instances():
            human_rate = (
                pair.rate / (10 ** pair.decimals)
                if pair.rate and pair.decimals
                else 0.0
            )
            pairs.append({
                "name": pair.name,
                "base_symbol": pair.base_symbol,
                "base_class": pair.base_class,
                "quote_symbol": pair.quote_symbol,
                "quote_class": pair.quote_class,
                "rate": pair.rate,
                "decimals": pair.decimals,
                "human_rate": human_rate,
                "last_updated": pair.last_updated,
                "last_error": pair.last_error,
            })
        return pairs

    # ------------------------------------------------------------------
    # Synchronous rate queries (read from DB, no inter-canister call)
    # ------------------------------------------------------------------

    def get_rate(self, base_symbol, quote_symbol):
        """
        Get the cached exchange rate as a float.

        This is a **synchronous** read from the local DB — no inter-canister
        call is needed.

        Args:
            base_symbol: Base asset symbol (e.g. "BTC")
            quote_symbol: Quote asset symbol (e.g. "USD")

        Returns:
            Float rate, or None if pair not found or never refreshed.
        """
        pair = FXPair[f"{base_symbol}/{quote_symbol}"]
        if pair is None or pair.rate == 0:
            return None
        return pair.rate / (10 ** pair.decimals)

    def get_rate_info(self, base_symbol, quote_symbol):
        """
        Get full rate information including staleness and metadata.

        Args:
            base_symbol: Base asset symbol
            quote_symbol: Quote asset symbol

        Returns:
            Dict with rate info, or None if pair not found.
        """
        pair = FXPair[f"{base_symbol}/{quote_symbol}"]
        if pair is None:
            return None
        human_rate = (
            pair.rate / (10 ** pair.decimals)
            if pair.rate and pair.decimals
            else 0.0
        )
        return {
            "pair": pair.name,
            "rate": human_rate,
            "raw_rate": pair.rate,
            "decimals": pair.decimals,
            "last_updated": pair.last_updated,
            "last_error": pair.last_error,
        }

    # ------------------------------------------------------------------
    # Async: refresh all pairs from XRC (inter-canister calls)
    # ------------------------------------------------------------------

    def refresh(self):
        """
        Refresh rates for all registered pairs from the XRC canister (async).

        Must be called with ``yield``::

            summary = yield fx.refresh()

        Returns:
            Generator that yields inter-canister calls and returns a summary
            string of all updated pairs.
        """
        return self._refresh()

    def _refresh(self) -> Async[str]:
        pairs = list(FXPair.instances())
        if not pairs:
            logger.info("No FX pairs registered, skipping refresh")
            return "No pairs registered"

        now = int(round(ic.time() / 1e9))
        results = []

        for pair in pairs:
            try:
                result = yield self._xrc.get_exchange_rate({
                    "base_asset": {
                        "symbol": pair.base_symbol,
                        "class": {pair.base_class: None},
                    },
                    "quote_asset": {
                        "symbol": pair.quote_symbol,
                        "class": {pair.quote_class: None},
                    },
                    "timestamp": None,
                }).with_cycles(XRC_CYCLES_PER_CALL)

                raw = result
                if hasattr(result, "Ok"):
                    raw = result.Ok if result.Ok else result.Err
                elif isinstance(result, dict):
                    pass

                if isinstance(raw, dict) and "Ok" in raw:
                    data = raw["Ok"]
                    pair.rate = data["rate"]
                    pair.decimals = data["metadata"]["decimals"]
                    pair.last_updated = now
                    pair.last_error = ""
                    human = data["rate"] / (10 ** data["metadata"]["decimals"])
                    results.append(f"{pair.name}={human}")
                    logger.info(f"Updated {pair.name}: {human}")
                elif isinstance(raw, dict) and "Err" in raw:
                    err_msg = str(raw["Err"])[:255]
                    pair.last_error = err_msg
                    pair.last_updated = now
                    results.append(f"{pair.name}=ERR:{err_msg}")
                    logger.error(f"XRC error for {pair.name}: {err_msg}")
                else:
                    err_msg = str(raw)[:255]
                    pair.last_error = err_msg
                    pair.last_updated = now
                    results.append(f"{pair.name}=ERR:{err_msg}")
                    logger.error(f"Unexpected XRC response for {pair.name}: {err_msg}")

            except Exception as e:
                err_msg = str(e)[:255]
                pair.last_error = err_msg
                pair.last_updated = now
                results.append(f"{pair.name}=ERR:{err_msg}")
                logger.error(
                    f"Exception refreshing {pair.name}: {traceback.format_exc()}"
                )

        summary = "; ".join(results)
        logger.info(f"FX refresh complete: {summary}")
        return summary

    # ------------------------------------------------------------------
    # Async: fetch a single pair from XRC (inter-canister call)
    # ------------------------------------------------------------------

    def fetch_rate(self, base_symbol, quote_symbol):
        """
        Fetch a single rate from the XRC canister and update the DB (async).

        Must be called with ``yield``::

            rate = yield fx.fetch_rate("BTC", "USD")

        Args:
            base_symbol: Base asset symbol
            quote_symbol: Quote asset symbol

        Returns:
            Generator that yields an inter-canister call and returns the
            human-readable rate as a float, or None on error.
        """
        return self._fetch_rate(base_symbol, quote_symbol)

    def _fetch_rate(self, base_symbol, quote_symbol) -> Async[float]:
        name = f"{base_symbol}/{quote_symbol}"
        pair = FXPair[name]
        if pair is None:
            logger.error(f"FX pair not found: {name}")
            return None

        now = int(round(ic.time() / 1e9))

        try:
            result = yield self._xrc.get_exchange_rate({
                "base_asset": {
                    "symbol": pair.base_symbol,
                    "class": {pair.base_class: None},
                },
                "quote_asset": {
                    "symbol": pair.quote_symbol,
                    "class": {pair.quote_class: None},
                },
                "timestamp": None,
            }).with_cycles(XRC_CYCLES_PER_CALL)

            raw = result
            if hasattr(result, "Ok"):
                raw = result.Ok if result.Ok else result.Err
            elif isinstance(result, dict):
                pass

            if isinstance(raw, dict) and "Ok" in raw:
                data = raw["Ok"]
                pair.rate = data["rate"]
                pair.decimals = data["metadata"]["decimals"]
                pair.last_updated = now
                pair.last_error = ""
                human = data["rate"] / (10 ** data["metadata"]["decimals"])
                logger.info(f"Fetched {name}: {human}")
                return human
            elif isinstance(raw, dict) and "Err" in raw:
                err_msg = str(raw["Err"])[:255]
                pair.last_error = err_msg
                pair.last_updated = now
                logger.error(f"XRC error for {name}: {err_msg}")
                return None
            else:
                err_msg = str(raw)[:255]
                pair.last_error = err_msg
                pair.last_updated = now
                logger.error(f"Unexpected XRC response for {name}: {err_msg}")
                return None

        except Exception as e:
            pair.last_error = str(e)[:255]
            pair.last_updated = now
            logger.error(f"Exception fetching {name}: {traceback.format_exc()}")
            return None
