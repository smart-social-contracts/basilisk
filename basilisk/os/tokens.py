"""
Basilisk OS — Well-known ICRC-1 tokens on IC mainnet.

This module has NO canister-side dependencies and can be safely imported
from both host-side tools (shell, CLI) and canister-side code.
"""

WELL_KNOWN_TOKENS = {
    "ckBTC": {
        "ledger":   "mxzaz-hqaaa-aaaar-qaada-cai",
        "indexer":  "n5wcd-faaaa-aaaar-qaaea-cai",
        "decimals": 8,
        "fee":      10,
    },
    "ckETH": {
        "ledger":   "ss2fx-dyaaa-aaaar-qacoq-cai",
        "indexer":  "s3zol-vqaaa-aaaar-qacpa-cai",
        "decimals": 18,
        "fee":      2_000_000_000_000,
    },
    "ckUSDC": {
        "ledger":   "xevnm-gaaaa-aaaar-qafnq-cai",
        "indexer":  "xrs4b-hiaaa-aaaar-qafoa-cai",
        "decimals": 6,
        "fee":      10_000,
    },
    "ICP": {
        "ledger":   "ryjl3-tyaaa-aaaaa-aaaba-cai",
        "indexer":  "qhbym-qaaaa-aaaaa-aaafq-cai",
        "decimals": 8,
        "fee":      10_000,
    },
}
