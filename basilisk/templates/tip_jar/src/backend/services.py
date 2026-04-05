"""Tip Jar — Service initialization (wallet, FX rates, encryption).

Service objects are instantiated at module level (lightweight — no DB or
inter-canister calls).  ``setup_services()`` must be called **after**
``Database.init()`` to register tokens and FX pairs in the DB.
"""

from basilisk.os.wallet import Wallet
from basilisk.os.fx import FXService
from basilisk.os.vetkeys import VetKeyService
from basilisk.os.crypto import CryptoService

# ---------------------------------------------------------------------------
# Service singletons
# ---------------------------------------------------------------------------

wallet = Wallet()
fx = FXService()
vetkeys = VetKeyService()
crypto = CryptoService(vetkeys)


def setup_services():
    """Register tokens and FX pairs (requires DB to be initialized first)."""

    # --- Wallet: ICRC-1 token management ---
    wallet.register_token(
        "ckBTC",
        ledger="mxzaz-hqaaa-aaaar-qaada-cai",
        indexer="n5wcd-faaaa-aaaar-qaaea-cai",
        decimals=8,
        fee=10,
    )
    wallet.register_token(
        "ckETH",
        ledger="ss2fx-dyaaa-aaaar-qacoq-cai",
        indexer="s3zol-vqaaa-aaaar-qacpa-cai",
        decimals=18,
        fee=2_000_000_000_000,
    )
    wallet.register_token(
        "ICP",
        ledger="ryjl3-tyaaa-aaaaa-aaaba-cai",
        indexer="qhbym-qaaaa-aaaaa-aaafq-cai",
        decimals=8,
        fee=10_000,
    )

    # --- FX rates: exchange rate queries via IC XRC canister ---
    fx.register_pair("ICP", "USD")
    fx.register_pair("BTC", "USD")
    fx.register_pair("ETH", "USD")
