"""Tip Jar — A basilisk canister template demonstrating all major features.

This is the **entry point** for the basilisk build system.  It sets up
persistent storage, imports entity models and service singletons, and
pulls all ``@query`` / ``@update`` endpoints into the global namespace
so the Rust dispatcher can find them at runtime.

Features demonstrated:
  - Persistent database (ic-python-db entities via StableBTreeMap)
  - ICRC-1 wallet (token balance, transfer, indexer sync)
  - FX rates (IC Exchange Rate Canister)
  - On-chain encryption (vetKeys + CryptoService)
  - HTTP outcalls (management canister)
  - Persistent filesystem (memfs, survives upgrades)
  - Timers (one-shot and periodic)
  - Guards (controller-only access)
  - Interactive shell (basilisk shell / SFTP)
  - Lifecycle hooks (init, post_upgrade)
"""

from basilisk import (
    query, update, text, nat64, ic, Async,
    StableBTreeMap, GuardResult, init, post_upgrade,
)
from basilisk.db import Database
from basilisk.logging import get_logger

_log = get_logger("tip_jar")

# ---------------------------------------------------------------------------
# Step 1: Persistent database storage (survives canister upgrades)
# ---------------------------------------------------------------------------

storage = StableBTreeMap[str, str](
    memory_id=1, max_key_size=100, max_value_size=10000,
)
Database.init(db_storage=storage, audit_enabled=True)

# ---------------------------------------------------------------------------
# Step 2: Import entity models (defines DB "tables")
# ---------------------------------------------------------------------------

import models  # noqa: F401 — registers Donor, TipMessage entities

# ---------------------------------------------------------------------------
# Step 3: Initialize services (wallet, FX, encryption)
# ---------------------------------------------------------------------------

from services import setup_services  # noqa: E402
setup_services()

# ---------------------------------------------------------------------------
# Step 4: Import all endpoints into global namespace
#
#   The Rust dispatcher looks up Python functions by name via
#   ``interpreter.get_global(name)``, so every @query / @update
#   function must be in this module's globals.
# ---------------------------------------------------------------------------

from endpoints import *  # noqa: F401,F403 — exposes all canister methods

# Re-import guarded endpoints so we can re-decorate them with a guard below
from endpoints import read_secret_notes as _read_secret_notes_unguarded
from endpoints import withdraw as _withdraw_unguarded

# ---------------------------------------------------------------------------
# Step 5: Controller guard + interactive shell
# ---------------------------------------------------------------------------

_shell_ns_by_principal = {}


def guard_against_non_controllers() -> GuardResult:
    if ic.is_controller(ic.caller()):
        return {"Ok": None}
    return {"Err": "Not Authorized: only controllers of this canister may call this method"}


# Guard the secret notes endpoint — only controllers can read them
@query(guard=guard_against_non_controllers)
def read_secret_notes() -> text:
    """Read all decrypted secret notes (controller-only)."""
    return _read_secret_notes_unguarded()


# Guard the withdraw endpoint — only controllers can withdraw tokens
@update(guard=guard_against_non_controllers)
def withdraw(token_name: text, to_principal: text, amount: nat64) -> Async[text]:
    """Withdraw donated tokens to a specified address (controller-only)."""
    result = yield from _withdraw_unguarded(token_name, to_principal, amount)
    return result


@update(guard=guard_against_non_controllers)
def execute_code_shell(code: str) -> str:
    """Execute Python code in a persistent namespace (basilisk shell).

    Each caller principal gets its own isolated namespace that persists
    across calls.  This is the core endpoint that ``basilisk shell`` and
    ``basilisk exec`` use.
    """
    import io
    import sys
    import traceback

    global _shell_ns_by_principal
    caller = str(ic.caller())
    if caller not in _shell_ns_by_principal:
        _shell_ns_by_principal[caller] = {"__builtins__": __builtins__}
        _shell_ns_by_principal[caller].update({"ic": ic})
        _shell_ns_by_principal[caller]["basilisk"] = __import__("basilisk")
    ns = _shell_ns_by_principal[caller]

    stdout = io.StringIO()
    stderr = io.StringIO()
    sys.stdout = stdout
    sys.stderr = stderr

    try:
        exec(code, ns, ns)
    except Exception:
        traceback.print_exc()

    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
    return stdout.getvalue() + stderr.getvalue()


# ---------------------------------------------------------------------------
# Step 6: Scheduled tasks (basilisk OS Task framework)
# ---------------------------------------------------------------------------

_FX_REFRESH_INTERVAL = 3600  # in seconds
_FX_TASK_NAME = "fx_refresh"

_FX_REFRESH_CODE = """\
from basilisk.logging import get_logger
from services import fx

logger = get_logger("tip_jar.fx_refresh")

def async_task():
    result = yield from fx.refresh()
    logger.info(f"done: {result}")
"""


def _ensure_fx_task():
    """Create the recurring FX refresh task if it doesn't exist yet."""
    from basilisk.os.entities import Task, Call, TaskStep, TaskSchedule, Codex
    from basilisk.os.task_manager import TaskManager

    task = Task[_FX_TASK_NAME]
    if task is None:
        codex = Codex(name=_FX_TASK_NAME)
        codex.code = _FX_REFRESH_CODE
        call = Call(codex=codex, is_async=True)
        task = Task(name=_FX_TASK_NAME, status="pending")
        TaskStep(task=task, call=call)
        TaskSchedule(
            name=_FX_TASK_NAME,
            task=task,
            repeat_every=_FX_REFRESH_INTERVAL,
        )
        _log.info(f"Created '{_FX_TASK_NAME}' task (every {_FX_REFRESH_INTERVAL}s)")
    TaskManager().run()


# ---------------------------------------------------------------------------
# Step 7: Lifecycle hooks
# ---------------------------------------------------------------------------

@init
def on_init():
    """Called once when the canister is first installed."""
    _log.info("Tip Jar canister initialized!")
    _ensure_fx_task()


@post_upgrade
def on_post_upgrade():
    """Called after every canister upgrade (code redeploy)."""
    _log.info("Tip Jar canister upgraded!")
    _ensure_fx_task()
