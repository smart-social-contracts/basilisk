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
    wallet.register_well_known_tokens("ckBTC", "ckETH", "ICP", "ckUSDC")

    # --- FX rates: exchange rate queries via IC XRC canister ---
    fx.register_pair("ICP", "USD")
    fx.register_pair("BTC", "USD")
    fx.register_pair("ETH", "USD")
    fx.register_pair("USDC", "USD")
