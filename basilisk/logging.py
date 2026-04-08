# Re-export everything from ic_python_logging so that
# ``from basilisk.logging import get_logger`` works both on the local
# machine (via this shim) and inside the canister (via the sys.modules alias
# created at canister startup by the WASM builder).
from ic_python_logging import *  # noqa: F401,F403
from ic_python_logging import get_logger  # noqa: F401 — explicit for type checkers
