# stable64 size

This section is a work in progress.

Examples:

-   [stable_memory](https://github.com/demergent-labs/basilisk/tree/main/examples/stable_memory)

```python
from basilisk import ic, nat64, query


@query
def stable64_size() -> nat64:
    return ic.stable64_size()
```
