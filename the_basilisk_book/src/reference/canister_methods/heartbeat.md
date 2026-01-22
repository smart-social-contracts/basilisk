# heartbeat

This section is a work in progress.

Examples:

-   [heartbeat](https://github.com/demergent-labs/basilisk/tree/main/examples/heartbeat)

```python
from basilisk import heartbeat, ic, void


@heartbeat
def heartbeat_() -> void:
    ic.print("this runs ~1 time per second")
```
