# stable size

This section is a work in progress.

Examples:

-   [stable_memory](https://github.com/demergent-labs/basilisk/tree/main/examples/stable_memory)

```python
from basilisk import ic, nat32, query


@query
def stable_size() -> nat32:
    return ic.stable_size()
```
