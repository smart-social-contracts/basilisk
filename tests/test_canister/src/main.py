"""
Basilisk OS Test Canister — minimal canister for integration testing.

Provides:
  - execute_code_shell: Execute Python code and return output (the core bosh endpoint)
  - status: Health check

The frozen_stdlib_preamble automatically provides the in-memory filesystem (memfs).
ic-python-db provides the entity ORM for task/entity tests.
"""

from basilisk import query, update, text, ic, Async, Tuple, match, CallResult, Principal
from basilisk.canisters.management import management_canister, HttpResponse, HttpTransformArgs

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


# ---------------------------------------------------------------------------
# HTTP outcall support
# ---------------------------------------------------------------------------

@query
def http_transform(args: HttpTransformArgs) -> HttpResponse:
    """Transform function for HTTP requests — removes headers for consensus."""
    response = args["response"]
    response["headers"] = []
    return response


@update
def download_to_file(url: str, dest: str) -> Async[str]:
    """Download a file from a URL and save it to the canister filesystem.

    Makes an HTTP outcall via the IC management canister, then writes
    the response body (decoded as UTF-8) to *dest* on the in-memory
    filesystem.  Returns a human-readable status string.
    """
    http_result: CallResult[HttpResponse] = yield management_canister.http_request(
        {
            "url": url,
            "max_response_bytes": 2_097_152,  # 2 MB limit
            "method": {"get": None},
            "headers": [
                {"name": "User-Agent", "value": "Basilisk/1.0"},
            ],
            "body": None,
            "transform": {
                "function": (ic.id(), "http_transform"),
                "context": bytes(),
            },
        }
    ).with_cycles(15_000_000_000)

    def _handle_ok(response: HttpResponse) -> str:
        try:
            content = response["body"].decode("utf-8")
        except UnicodeDecodeError as e:
            return f"Error: failed to decode response as UTF-8: {e}"
        import os
        parent = os.path.dirname(dest)
        if parent and parent != "/":
            os.makedirs(parent, exist_ok=True)
        with open(dest, "w") as f:
            f.write(content)
        return f"Downloaded {len(content)} bytes to {dest}"

    def _handle_err(err: str) -> str:
        return f"Download failed: {err}"

    return match(http_result, {"Ok": _handle_ok, "Err": _handle_err})
