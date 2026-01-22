# performance counter

This section is a work in progress.

Examples:

-   [ic_api](https://github.com/demergent-labs/basilisk/tree/main/examples/ic_api)

```python
from basilisk import ic, nat64, query


@query
def performance_counter() -> nat64:
    return ic.performance_counter(0)
```
