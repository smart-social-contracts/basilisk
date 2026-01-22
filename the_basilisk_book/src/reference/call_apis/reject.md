# reject

This section is a work in progress.

Examples:

-   [ic_api](https://github.com/demergent-labs/basilisk/tree/main/examples/ic_api)
-   [manual_reply](https://github.com/demergent-labs/basilisk/tree/main/examples/manual_reply)
-   [rejections](https://github.com/demergent-labs/basilisk/tree/main/examples/rejections)

```python
from basilisk import empty, ic, Manual, query


@query
def reject(message: str) -> Manual[empty]:
    ic.reject(message)
```
