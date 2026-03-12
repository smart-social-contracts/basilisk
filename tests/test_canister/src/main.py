"""
Basilisk OS Test Canister — minimal canister for integration testing.

Provides:
  - execute_code_shell: Execute Python code and return output (the core bosh endpoint)
  - status: Health check

The frozen_stdlib_preamble automatically provides the in-memory filesystem (memfs).
ic-python-db provides the entity ORM for task/entity tests.
"""

from basilisk import query, update, text, ic

# ---------------------------------------------------------------------------
# Persistent shell namespace (per principal)
# ---------------------------------------------------------------------------

_shell_ns_by_principal = {}


@update
def execute_code_shell(code: str) -> str:
    """Execute Python code in a persistent namespace and return the output.

    Each caller principal gets its own isolated namespace that persists
    across calls. This is the core endpoint that bosh uses.
    """
    import io
    import sys
    import traceback

    global _shell_ns_by_principal
    caller = str(ic.caller())
    if caller not in _shell_ns_by_principal:
        _shell_ns_by_principal[caller] = {"__builtins__": __builtins__}
        _shell_ns_by_principal[caller].update({
            "ic": ic,
        })
        # Try to add ic-python-db if available
        try:
            import ic_python_db
            _shell_ns_by_principal[caller]["ic_python_db"] = ic_python_db
        except ImportError:
            pass
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


@query
def status() -> str:
    """Health check endpoint."""
    return "ok"


@query
def whoami() -> str:
    """Return the caller's principal ID."""
    return str(ic.caller())
