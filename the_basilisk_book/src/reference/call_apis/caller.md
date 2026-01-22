# caller

This section is a work in progress.

Examples:

-   [ic_api](https://github.com/demergent-labs/basilisk/tree/main/examples/ic_api)
-   [whoami](https://github.com/demergent-labs/basilisk/tree/main/examples/motoko_examples/whoami)

```python
from basilisk import ic, Principal, query


# returns the principal of the identity that called this function
@query
def caller() -> Principal:
    return ic.caller()
```
