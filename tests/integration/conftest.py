"""
Shared pytest fixtures for Basilisk integration tests.

These tests build and deploy example canisters to a local PocketIC replica,
then call canister methods via `icp canister call` to verify behavior.

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
EXAMPLES_DIR = os.path.join(REPO_ROOT, "tests", "fixtures")


# ---------------------------------------------------------------------------
# Session-scoped replica
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def replica(tmp_path_factory):
    """Start a shared local network for the entire test session.

    icp-cli networks are project-local: each directory with an icp.yaml
    gets its own network.  For integration tests we start the network
    from a temporary directory that acts as our "project root".
    """
    project_dir = str(tmp_path_factory.mktemp("icp_project"))

    # Write a minimal icp.yaml so icp-cli recognizes this as a project
    with open(os.path.join(project_dir, "icp.yaml"), "w") as f:
        f.write("canisters: []\n")

    result = subprocess.run(
        ["icp", "network", "start", "-d"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"icp network start failed (exit code {result.returncode}): {result.stderr[-500:]}"
        )

    # Get the network URL from icp network status
    network_url = _get_network_url(project_dir)

    yield {
        "project_dir": project_dir,
        "network_url": network_url or "http://127.0.0.1:4943",
    }

    subprocess.run(
        ["icp", "network", "stop"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )


def _get_network_url(project_dir):
    """Extract the network URL from icp network status."""
    try:
        result = subprocess.run(
            ["icp", "network", "status"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "http" in line.lower():
                    m = re.search(r'(https?://[\w.:]+)', line)
                    if m:
                        return m.group(1)
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


# ---------------------------------------------------------------------------
# Example deployment
# ---------------------------------------------------------------------------

# When BASILISK_PREBUILT_WASMS=1, skip build and deploy pre-built WASMs directly.
_USE_PREBUILT = os.environ.get("BASILISK_PREBUILT_WASMS", "") == "1"

# Global mapping: canister_id -> {"name": str, "example_dir": str}
_CANDID_MAP: dict = {}


def deploy_example(example_name, replica_fixture=None):
    """Build and deploy an example canister, returning a dict of {name: canister_id}.

    For single-canister examples, returns e.g. {"counter": "bkyz2-..."}.
    For multi-canister examples, returns all canisters.

    If BASILISK_PREBUILT_WASMS=1 is set, deploys pre-built WASMs from
    .basilisk/<name>/<name>.wasm instead of running the full build.
    """
    example_dir = os.path.join(EXAMPLES_DIR, example_name)
    if not os.path.isdir(example_dir):
        raise FileNotFoundError(f"Example directory not found: {example_dir}")

    # Read canister config — prefer icp.yaml, fall back to dfx.json
    canister_configs = _read_canister_config(example_dir)
    canister_names = list(canister_configs.keys())
    if not canister_names:
        raise ValueError(f"No canisters defined in {example_dir}")

    network_url = None
    if replica_fixture:
        network_url = replica_fixture.get("network_url")

    if _USE_PREBUILT:
        _deploy_prebuilt(example_dir, example_name, canister_names, canister_configs, network_url)
    else:
        _deploy_with_build(example_dir, example_name, canister_names, network_url)

    # Read canister IDs
    canister_ids = {}
    for name in canister_names:
        cid = _get_canister_id(example_dir, name, network_url)
        if cid:
            canister_ids[name] = cid
            _CANDID_MAP[cid] = {"name": name, "example_dir": example_dir}

    if not canister_ids:
        raise RuntimeError(f"Failed to deploy {example_name}: no canister IDs found")

    return canister_ids


def _read_canister_config(example_dir):
    """Read canister configuration from icp.yaml or dfx.json.

    Returns a dict of {canister_name: {"main": str}} regardless of source format.
    """
    icp_yaml_path = os.path.join(example_dir, "icp.yaml")
    dfx_json_path = os.path.join(example_dir, "dfx.json")

    if os.path.exists(icp_yaml_path):
        import yaml
        with open(icp_yaml_path) as f:
            config = yaml.safe_load(f)
        result = {}
        for canister in config.get("canisters", []):
            name = canister["name"]
            # Extract main from build commands
            main_file = _extract_main_from_icp_yaml(canister)
            result[name] = {"main": main_file}
        return result

    if os.path.exists(dfx_json_path):
        with open(dfx_json_path) as f:
            config = json.load(f)
        result = {}
        for name, cfg in config.get("canisters", {}).items():
            result[name] = {"main": cfg.get("main", "")}
        return result

    raise FileNotFoundError(f"No icp.yaml or dfx.json in {example_dir}")


def _extract_main_from_icp_yaml(canister_config):
    """Extract the Python entry point from icp.yaml build commands."""
    for step in canister_config.get("build", {}).get("steps", []):
        for cmd in step.get("commands", []):
            if "python" in cmd and "basilisk" in cmd:
                parts = cmd.split()
                # Pattern: ... python3 -m basilisk <name> <main>
                for i, part in enumerate(parts):
                    if part == "basilisk" and i + 2 < len(parts):
                        return parts[i + 2]
    return ""


def _deploy_with_build(example_dir, example_name, canister_names, network_url=None):
    """Full build + deploy via icp deploy."""
    cmd = ["icp", "deploy"]
    if network_url:
        cmd.extend(["-n", network_url])

    result = subprocess.run(
        cmd,
        cwd=example_dir,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode != 0:
        _wait_for_canisters(example_dir, canister_names, network_url, timeout=3600)


def _deploy_prebuilt(example_dir, example_name, canister_names, canister_configs, network_url=None):
    """Deploy pre-built WASMs without running the build step.

    Uses icp canister create + icp canister install --wasm for each canister.
    """
    network_args = ["-n", network_url] if network_url else []

    # Create all canisters
    for name in canister_names:
        result = subprocess.run(
            ["icp", "canister", "create", name, *network_args],
            cwd=example_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"icp canister create {name} failed for {example_name}: {result.stderr[-300:]}"
            )

    # Install each canister from pre-built WASM
    installed = set()
    remaining = list(canister_names)

    for _pass in range(2):
        still_remaining = []
        for name in remaining:
            wasm_path = os.path.join(example_dir, ".basilisk", name, f"{name}.wasm")
            if not os.path.exists(wasm_path):
                raise FileNotFoundError(
                    f"Pre-built WASM not found: {wasm_path}. "
                    f"Run 'python scripts/build_all_wasms.py' first."
                )

            init_arg = _get_init_arg(example_dir, name, installed)
            if init_arg is _DEFER:
                still_remaining.append(name)
                continue

            cmd = ["icp", "canister", "install", name, "--wasm", wasm_path, "-y", *network_args]
            if init_arg:
                cmd.extend(["--args", init_arg])

            result = subprocess.run(
                cmd,
                cwd=example_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"icp canister install {name} failed: {result.stderr[-300:]}"
                )
            installed.add(name)

        remaining = still_remaining
        if not remaining:
            break

    if remaining:
        raise RuntimeError(f"Could not resolve init args for: {remaining}")


_DEFER = object()

_KNOWN_INIT_ARGS = {
    "complex_init": '(record { "Hello"; record { id = "user1" } })',
    "init": '(record { id = "user1" }, variant { Fire }, principal "aaaaa-aa")',
    "whoami": '(principal "aaaaa-aa")',
    "init_and_post_upgrade_recovery": "(false)",
}


def _get_init_arg(example_dir, canister_name, installed):
    """Return the init argument string for a canister, or None if none needed.

    Returns _DEFER if the canister depends on another that hasn't been installed yet.
    """
    if canister_name in _KNOWN_INIT_ARGS:
        return _KNOWN_INIT_ARGS[canister_name]

    dep = _INIT_DEPS.get(canister_name)
    if dep:
        dep_name, arg_template = dep
        if dep_name not in installed:
            return _DEFER
        dep_id = _get_canister_id(example_dir, dep_name)
        if not dep_id:
            return _DEFER
        return arg_template.format(dep_id)

    return None


_INIT_DEPS = {
    "rejections": ("some_service", '(principal "{}")'),
    "intermediary": ("cycles", '(principal "{}")'),
    "canister1": ("canister2", '(principal "{}")'),
}


def _wait_for_canisters(example_dir, canister_names, network_url=None, timeout=3600):
    """Poll until all canisters have a module hash (= installed)."""
    network_args = ["-n", network_url] if network_url else []
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(15)
        all_ready = True
        for name in canister_names:
            try:
                status = subprocess.run(
                    ["icp", "canister", "status", name, *network_args],
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


def _get_canister_id(example_dir, canister_name, network_url=None):
    """Get canister ID via icp canister list or from .icp data files."""
    network_args = ["-n", network_url] if network_url else []

    # Try icp canister list --json
    try:
        result = subprocess.run(
            ["icp", "canister", "list", *network_args, "--json"],
            cwd=example_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                # icp canister list returns canister info - parse for our name
                if isinstance(data, list):
                    for entry in data:
                        if entry.get("name") == canister_name:
                            return entry.get("id") or entry.get("canister_id")
                elif isinstance(data, dict):
                    for key, val in data.items():
                        if key == canister_name:
                            if isinstance(val, str):
                                return val
                            elif isinstance(val, dict):
                                return val.get("id") or val.get("canister_id") or val.get("local")
            except (json.JSONDecodeError, KeyError):
                pass
    except (subprocess.TimeoutExpired, OSError):
        pass

    # Fallback: read from .icp/data/ or .dfx/local/canister_ids.json
    for ids_file in [
        os.path.join(example_dir, ".icp", "data", "canister_ids.json"),
        os.path.join(example_dir, ".dfx", "local", "canister_ids.json"),
    ]:
        if os.path.exists(ids_file):
            try:
                with open(ids_file) as f:
                    ids = json.load(f)
                entry = ids.get(canister_name, {})
                if isinstance(entry, str):
                    return entry
                return entry.get("local") or entry.get("id")
            except (json.JSONDecodeError, OSError):
                pass

    return None


# ---------------------------------------------------------------------------
# Canister call helpers
# ---------------------------------------------------------------------------

def call_canister(canister_id, method, args=None, *, example_dir=None, update=False):
    """Call a canister method via icp-cli and return the parsed result.

    Args:
        canister_id: The canister ID string.
        method: The method name to call.
        args: Optional Candid argument string, e.g. '("hello")'.
        example_dir: Working directory (needed for local network).
        update: If True, force update call (omit --query).

    Returns:
        The raw Candid response string from icp.
    """
    info = _CANDID_MAP.get(canister_id)
    target = info["name"] if info else canister_id
    cmd = ["icp", "canister", "call", target, method]
    if args:
        cmd.append(args)
    if not update:
        cmd.append("--query")

    cwd = (info["example_dir"] if info else None) or example_dir or EXAMPLES_DIR
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"icp canister call failed: {result.stderr.strip()}"
        )

    return result.stdout.strip()


def call_canister_expect_trap(canister_id, method, args=None, *, example_dir=None):
    """Call a canister method expecting it to trap. Returns the error message."""
    info = _CANDID_MAP.get(canister_id)
    target = info["name"] if info else canister_id
    cmd = ["icp", "canister", "call", target, method]
    if args:
        cmd.append(args)

    cwd = (info["example_dir"] if info else None) or example_dir or EXAMPLES_DIR
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

    if response.startswith("(") and response.endswith(")"):
        inner = response[1:-1].strip()
    else:
        inner = response

    if inner.startswith('"') and inner.endswith('"'):
        return inner[1:-1]

    if inner == "true":
        return True
    if inner == "false":
        return False

    if inner == "null":
        return None

    m = re.match(r'^(-?\d[\d_]*)\s*:\s*\w+$', inner)
    if m:
        return int(m.group(1).replace("_", ""))

    m = re.match(r'^(-?\d[\d_]*)$', inner)
    if m:
        return int(m.group(1).replace("_", ""))

    return inner
