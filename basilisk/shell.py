"""
Basilisk Shell — minimal canister communication utilities.

Provides ``canister_exec`` and ``_parse_candid`` for sending Python code
to a canister and parsing the Candid-encoded response.

The full interactive shell, magic commands, SFTP, and SSH server live in
the ``ic-basilisk-toolkit`` package (``ic_basilisk_toolkit.shell``).
"""

import ast
import os
import re
import subprocess
import time as _time


# ---------------------------------------------------------------------------
# Version / git info (client-side)
# ---------------------------------------------------------------------------

def _get_basilisk_version() -> str:
    """Return the installed basilisk package version."""
    try:
        from basilisk import __version__
        return __version__
    except Exception:
        return "unknown"


def _get_git_info() -> dict:
    """Return commit hash and datetime from the basilisk package source."""
    info = {}
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(pkg_dir)  # parent of basilisk/
    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%H %aI"],
            capture_output=True, text=True, timeout=5,
            cwd=repo_dir,
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split(" ", 1)
            if len(parts) == 2:
                info["commit"] = parts[0][:8]
                info["commit_date"] = parts[1]
    except Exception:
        pass
    return info


# ---------------------------------------------------------------------------
# Candid parsing
# ---------------------------------------------------------------------------

def _parse_candid(output: str) -> str:
    """Parse a Candid-encoded string response from dfx into plain text."""
    output = output.strip()
    m = re.search(r'\(\s*"(.*)"\s*,?\s*\)', output, re.DOTALL)
    if m:
        try:
            return ast.literal_eval(f'"{m.group(1)}"')
        except (SyntaxError, ValueError):
            return m.group(1).replace("\\n", "\n").replace('\\"', '"')
    return output


# ---------------------------------------------------------------------------
# Canister communication
# ---------------------------------------------------------------------------

def _is_transient_dfx_error(stderr: str) -> bool:
    s = (stderr or "").lower()
    transient_markers = [
        "temporary failure in name resolution",
        "failed to lookup address information",
        "dns error",
        "client error (connect)",
        "an error happened during communication with the replica",
        "error sending request for url",
        "timed out",
        "timeout",
        "connection refused",
        "network is unreachable",
        "service unavailable",
        "gateway timeout",
    ]
    return any(m in s for m in transient_markers)


# Module-level identity — set once in main(), used by all dfx commands.
_IDENTITY: str | None = None


def _dfx_call_cmd(network: str = None, *, extra_flags: list[str] | None = None) -> list[str]:
    """Build the common `dfx canister call [--identity ...] [--network ...]` prefix."""
    cmd = ["dfx", "canister", "call"]
    if _IDENTITY:
        cmd.extend(["--identity", _IDENTITY])
    if extra_flags:
        cmd.extend(extra_flags)
    if network:
        cmd.extend(["--network", network])
    return cmd


def _run_dfx_with_retries(
    cmd: list[str],
    *,
    timeout_s: int,
    attempts: int = 5,
) -> subprocess.CompletedProcess:
    last: subprocess.CompletedProcess | None = None
    for attempt in range(attempts):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            if attempt >= attempts - 1:
                raise
            _time.sleep(min(2**attempt, 8))
            continue

        last = r
        if r.returncode == 0:
            return r
        if not _is_transient_dfx_error(r.stderr):
            return r
        if attempt >= attempts - 1:
            return r
        _time.sleep(min(2**attempt, 8))

    return last  # type: ignore[return-value]


def canister_exec(code: str, canister: str, network: str = None) -> str:
    """Send Python code to the canister and return the output."""
    escaped = code.replace('"', '\\"').replace("\n", "\\n")
    cmd = _dfx_call_cmd(network)
    cmd.extend([canister, "__shell__", f'("{escaped}")'])

    try:
        r = _run_dfx_with_retries(cmd, timeout_s=120)
        if r.returncode != 0:
            return f"[dfx error] {r.stderr.strip()}"
        return _parse_candid(r.stdout)
    except subprocess.TimeoutExpired:
        return "[error] canister call timed out (120s)"
    except FileNotFoundError:
        return "[error] dfx not found — install the DFINITY SDK"
