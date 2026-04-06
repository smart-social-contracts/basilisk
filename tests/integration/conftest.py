"""
Shared pytest fixtures for Basilisk integration tests.

These tests build and deploy example canisters to a local PocketIC replica,
then call canister methods via `dfx canister call` to verify behavior.

Usage:
    pytest tests/integration/ -v
    pytest tests/integration/test_counter.py -v
"""

import json
import os
import re
import subprocess
import time

import pytest


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXAMPLES_DIR = os.path.join(REPO_ROOT, "examples")


# ---------------------------------------------------------------------------
# Session-scoped replica
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def replica(tmp_path_factory):
    """Start a shared PocketIC replica for the entire test session.

    Uses a *persistent* local network so the replica state is stored
    globally (~/.local/share/dfx/) rather than per-project.  This lets
    dfx commands run from any example directory and still find the
    running PocketIC instance.
    """
    dfx_config_dir = os.path.expanduser("~/.config/dfx")
    os.makedirs(dfx_config_dir, exist_ok=True)
    networks_json = os.path.join(dfx_config_dir, "networks.json")
    wrote_networks = False
    if not os.path.exists(networks_json):
        with open(networks_json, "w") as f:
            json.dump({"local": {"type": "persistent", "replica": {"subnet_type": "system"}}}, f)
        wrote_networks = True

    dfx_home = str(tmp_path_factory.mktemp("dfx_home"))
    # DEVNULL for both stdout AND stderr: PocketIC inherits pipe FDs from
    # its parent (dfx), keeping them open indefinitely.  With DEVNULL there
    # are no pipes, so subprocess.run() returns as soon as dfx CLI exits.
    result = subprocess.run(
        ["dfx", "start", "--clean", "--background", "--pocketic"],
        cwd=dfx_home,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"dfx start --pocketic failed (exit code {result.returncode})")

    yield "local"

    subprocess.run(
        ["dfx", "stop"],
        cwd=dfx_home,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if wrote_networks:
        try:
            os.remove(networks_json)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Example deployment
# ---------------------------------------------------------------------------

# When BASILISK_PREBUILT_WASMS=1, skip build and deploy pre-built WASMs directly.
_USE_PREBUILT = os.environ.get("BASILISK_PREBUILT_WASMS", "") == "1"

# Global mapping: canister_id -> {"did": abs_path, "queries": set_of_query_method_names}
# Populated by deploy_example() so call_canister() can pass --query/--candid.
_CANDID_MAP: dict = {}


def _parse_query_methods(did_path):
    """Parse a .did file and return the set of method names annotated as query."""
    queries = set()
    try:
        with open(did_path) as f:
            for line in f:
                # Match lines like:  "method_name" : (...) -> (...) query;
                m = re.search(r'"(\w+)"\s*:.*\)\s*(query|composite_query)\s*;', line)
                if m:
                    queries.add(m.group(1))
    except OSError:
        pass
    return queries


def deploy_example(example_name, replica_host="127.0.0.1:8000"):
    """Build and deploy an example canister, returning a dict of {name: canister_id}.

    For single-canister examples, returns e.g. {"counter": "bkyz2-..."}.
    For multi-canister examples, returns all canisters.

    If BASILISK_PREBUILT_WASMS=1 is set, deploys pre-built WASMs from
    .basilisk/<name>/<name>.wasm instead of running the full build.
    """
    example_dir = os.path.join(EXAMPLES_DIR, example_name)
    if not os.path.isdir(example_dir):
        raise FileNotFoundError(f"Example directory not found: {example_dir}")

    dfx_json_path = os.path.join(example_dir, "dfx.json")
    with open(dfx_json_path) as f:
        dfx_config = json.load(f)

    canister_names = list(dfx_config.get("canisters", {}).keys())
    if not canister_names:
        raise ValueError(f"No canisters defined in {dfx_json_path}")

    if _USE_PREBUILT:
        _deploy_prebuilt(example_dir, example_name, canister_names, dfx_config)
    else:
        _deploy_with_build(example_dir, example_name, canister_names)

    # Read canister IDs and register candid/query info
    canister_ids = {}
    for name in canister_names:
        cid = _get_canister_id(example_dir, name)
        if cid:
            canister_ids[name] = cid
            did_path = os.path.join(example_dir, ".basilisk", name, f"{name}.did")
            if os.path.exists(did_path):
                abs_did = os.path.abspath(did_path)
                _CANDID_MAP[cid] = {
                    "did": abs_did,
                    "queries": _parse_query_methods(abs_did),
                }

    if not canister_ids:
        raise RuntimeError(f"Failed to deploy {example_name}: no canister IDs found")

    return canister_ids


def _deploy_with_build(example_dir, example_name, canister_names):
    """Full build + deploy via dfx deploy (slow — compiles WASM from source)."""
    result = subprocess.run(
        ["dfx", "deploy"],
        cwd=example_dir,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode != 0:
        _wait_for_canisters(example_dir, canister_names, timeout=3600)


def _deploy_prebuilt(example_dir, example_name, canister_names, dfx_config):
    """Deploy pre-built WASMs without running the build step.

    Uses dfx canister create + dfx canister install --wasm for each canister.
    Expects a persistent-network PocketIC already running (started by the
    replica fixture).  The WASMs must exist at .basilisk/<name>/<name>.wasm.
    """
    # Create all canisters (allocates IDs)
    result = subprocess.run(
        ["dfx", "canister", "create", "--all"],
        cwd=example_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"dfx canister create --all failed for {example_name}: {result.stderr[-300:]}"
        )
    # Install each canister from pre-built WASM and set up candid interface
    for name in canister_names:
        wasm_path = os.path.join(example_dir, ".basilisk", name, f"{name}.wasm")
        if not os.path.exists(wasm_path):
            raise FileNotFoundError(
                f"Pre-built WASM not found: {wasm_path}. "
                f"Run 'python scripts/build_all_wasms.py' first."
            )

        cmd = ["dfx", "canister", "install", name, "--wasm", wasm_path]

        result = subprocess.run(
            cmd,
            cwd=example_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"dfx canister install {name} failed: {result.stderr[-300:]}"
            )



def _wait_for_canisters(example_dir, canister_names, timeout=3600):
    """Poll until all canisters have a module hash (= installed)."""
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(15)
        all_ready = True
        for name in canister_names:
            try:
                status = subprocess.run(
                    ["dfx", "canister", "status", name],
                    cwd=example_dir,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if "Module hash: 0x" not in status.stdout:
                    all_ready = False
                    break
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                all_ready = False
                break
        if all_ready:
            return
    raise TimeoutError(f"Canisters did not install within {timeout}s")


def _get_canister_id(example_dir, canister_name):
    """Get canister ID, trying `dfx canister id` first then the JSON file."""
    # Prefer dfx canister id — works regardless of where IDs are stored
    try:
        result = subprocess.run(
            ["dfx", "canister", "id", canister_name],
            cwd=example_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass

    # Fallback: read from .dfx/local/canister_ids.json
    ids_file = os.path.join(example_dir, ".dfx", "local", "canister_ids.json")
    if not os.path.exists(ids_file):
        return None
    with open(ids_file) as f:
        ids = json.load(f)
    entry = ids.get(canister_name, {})
    return entry.get("local")


# ---------------------------------------------------------------------------
# Canister call helpers
# ---------------------------------------------------------------------------

def call_canister(canister_id, method, args=None, *, example_dir=None, update=False):
    """Call a canister method via dfx and return the parsed result.

    Args:
        canister_id: The canister ID string.
        method: The method name to call.
        args: Optional Candid argument string, e.g. '("hello")'.
        example_dir: Working directory for dfx (needed for local replica).
        update: If True, force update call. By default dfx auto-detects.

    Returns:
        The raw Candid response string from dfx.
    """
    # Build command with options BEFORE positional args so dfx parses them.
    cmd = ["dfx", "canister", "call"]
    # With persistent network dfx can't auto-detect query vs update.
    # Parse the .did file to determine the method type explicitly.
    info = _CANDID_MAP.get(canister_id)
    if info:
        cmd.extend(["--candid", info["did"]])
        if not update and method in info["queries"]:
            cmd.append("--query")
    if update:
        cmd.append("--update")
    cmd.extend([canister_id, method])
    if args:
        cmd.append(args)

    cwd = example_dir or EXAMPLES_DIR
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"dfx canister call failed: {result.stderr.strip()}"
        )

    return result.stdout.strip()


def call_canister_expect_trap(canister_id, method, args=None, *, example_dir=None):
    """Call a canister method expecting it to trap. Returns the error message."""
    cmd = ["dfx", "canister", "call"]
    info = _CANDID_MAP.get(canister_id)
    if info:
        cmd.extend(["--candid", info["did"]])
        if method in info["queries"]:
            cmd.append("--query")
    cmd.extend([canister_id, method])
    if args:
        cmd.append(args)

    cwd = example_dir or EXAMPLES_DIR
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode == 0:
        raise AssertionError(
            f"Expected trap but call succeeded: {result.stdout.strip()}"
        )

    return result.stderr.strip()


# ---------------------------------------------------------------------------
# Candid response parsing helpers
# ---------------------------------------------------------------------------

def parse_candid_text(response):
    """Extract the inner value from a Candid text response like '("hello")'.

    Handles common patterns:
        '("text value")'  -> "text value"
        '(42 : nat)'      -> 42
        '(true)'          -> True
        '(null)'          -> None
        '(vec { ... })'   -> list (as raw string, caller parses further)
        '(variant { Ok = ... })' -> {"Ok": ...}
    """
    response = response.strip()
    if not response:
        return None

    # Remove outer parens
    if response.startswith("(") and response.endswith(")"):
        inner = response[1:-1].strip()
    else:
        inner = response

    # Text
    if inner.startswith('"') and inner.endswith('"'):
        return inner[1:-1]

    # Boolean
    if inner == "true":
        return True
    if inner == "false":
        return False

    # Null
    if inner == "null":
        return None

    # Nat/Int with type annotation
    m = re.match(r'^(-?\d[\d_]*)\s*:\s*\w+$', inner)
    if m:
        return int(m.group(1).replace("_", ""))

    # Plain integer
    m = re.match(r'^(-?\d[\d_]*)$', inner)
    if m:
        return int(m.group(1).replace("_", ""))

    # Return raw for complex types (vec, record, variant)
    return inner
