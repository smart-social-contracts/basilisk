# canister balance

This section is a work in progress.

Examples:

-   [cycles](https://github.com/demergent-labs/basilisk/tree/main/examples/cycles)
-   [ic_api](https://github.com/demergent-labs/basilisk/tree/main/examples/ic_api)

```python
from basilisk import ic, nat64, query


# returns the amount of cycles available in the canister
@query
def canister_balance() -> nat64:
    return ic.canister_balance()
```
