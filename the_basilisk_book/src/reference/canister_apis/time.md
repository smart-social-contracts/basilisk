# time

This section is a work in progress.

Examples:

-   [audio_recorder](https://github.com/demergent-labs/basilisk/tree/main/examples/audio_recorder)
-   [ic_api](https://github.com/demergent-labs/basilisk/tree/main/examples/ic_api)

```python
from basilisk import ic, nat64, query


# returns the current timestamp
@query
def time() -> nat64:
    return ic.time()
```
