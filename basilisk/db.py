# Re-export everything from ic_python_db so that
# ``from basilisk.db import Database, Entity`` works both on the local
# machine (via this shim) and inside the canister (via the sys.modules alias
# created at canister startup by the WASM builder).
from ic_python_db import *  # noqa: F401,F403
from ic_python_db import Database, Entity  # noqa: F401 — explicit for type checkers
