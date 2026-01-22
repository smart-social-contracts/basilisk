# bitcoin_get_utxos

This section is a work in progress.

Examples:

-   [bitcoin](https://github.com/demergent-labs/basilisk/tree/main/examples/bitcoin)

```python
from basilisk import Async, CallResult, match, update, Variant
from basilisk.canisters.management import GetUtxosResult, management_canister

BITCOIN_API_CYCLE_COST = 100_000_000


class ExecuteGetUtxosResult(Variant, total=False):
    Ok: GetUtxosResult
    Err: str


@update
def get_utxos(address: str) -> Async[ExecuteGetUtxosResult]:
    call_result: CallResult[
        GetUtxosResult
    ] = yield management_canister.bitcoin_get_utxos(
        {"address": address, "filter": None, "network": {"Regtest": None}}
    ).with_cycles(
        BITCOIN_API_CYCLE_COST
    )

    return match(
        call_result, {"Ok": lambda ok: {"Ok": ok}, "Err": lambda err: {"Err": err}}
    )
```
