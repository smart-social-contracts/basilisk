# raw_rand

This section is a work in progress.

Examples:

-   [generators](https://github.com/demergent-labs/basilisk/tree/main/examples/generators)
-   [heartbeat](https://github.com/demergent-labs/basilisk/tree/main/examples/heartbeat)
-   [management_canister](https://github.com/demergent-labs/basilisk/tree/main/examples/management_canister)
-   [timers](https://github.com/demergent-labs/basilisk/tree/main/examples/timers)

```python
from basilisk import Async, blob, CallResult, match, update
from basilisk.canisters.management import management_canister


@update
def get_randomness_directly() -> Async[blob]:
    randomness_result: CallResult[blob] = yield management_canister.raw_rand()

    return match(randomness_result, {"Ok": lambda ok: ok, "Err": lambda err: err})
```
