# canister balance 128

This section is a work in progress.

Examples:

-   [cycles](https://github.com/demergent-labs/basilisk/tree/main/examples/cycles)
-   [ic_api](https://github.com/demergent-labs/basilisk/tree/main/examples/ic_api)

```python
from basilisk import ic, nat, query


# returns the amount of cycles available in the canister
@query
def canister_balance128() -> nat:
    return ic.canister_balance128()
```
