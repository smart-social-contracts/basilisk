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

_CURRENT_NETWORK_DIR: str = ""


@pytest.fixture(scope="session")
def replica():
    """Marker fixture that integration tests depend on.

    icp-cli networks are project-local and bind to the same port (8000),
    so only one can run at a time.  _ensure_network stops any previous
    fixture's network before starting the next one.
    """
    yield

    if _CURRENT_NETWORK_DIR:
        subprocess.run(
            ["icp", "network", "stop"],
            cwd=_CURRENT_NETWORK_DIR,
            capture_output=True,
            text=True,
        )


def _ensure_network(example_dir):
    """Start the local network for a fixture directory.

    Stops the previous fixture's network first since icp-cli binds to
    a fixed port.
    """
    global _CURRENT_NETWORK_DIR

    if _CURRENT_NETWORK_DIR == example_dir:
        return

    if _CURRENT_NETWORK_DIR:
        subprocess.run(
            ["icp", "network", "stop"],
            cwd=_CURRENT_NETWORK_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        _CURRENT_NETWORK_DIR = ""

    result = subprocess.run(
        ["icp", "network", "start", "-d"],
        cwd=example_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        err = result.stderr[-500:] if result.stderr else ""
        raise RuntimeError(
            f"icp network start failed in {example_dir}: {err}"
        )
    _CURRENT_NETWORK_DIR = example_dir


# ---------------------------------------------------------------------------
# Example deployment
# ---------------------------------------------------------------------------

# When BASILISK_PREBUILT_WASMS=1, skip build and deploy pre-built WASMs directly.
_USE_PREBUILT = os.environ.get("BASILISK_PREBUILT_WASMS", "") == "1"

# Global mapping: canister_id -> {"name": str, "example_dir": str}
_CANDID_MAP: dict = {}


def deploy_example(example_name, replica_fixture=None):
    """Build and deploy an example canister, returning a dict of {name: canister_id}.

    Starts a project-local network in the fixture directory if needed.
    """
    example_dir = os.path.join(EXAMPLES_DIR, example_name)
    if not os.path.isdir(example_dir):
        raise FileNotFoundError(f"Example directory not found: {example_dir}")

    canister_configs = _read_canister_config(example_dir)
    canister_names = list(canister_configs.keys())
    if not canister_names:
        raise ValueError(f"No canisters defined in {example_dir}")

    _ensure_network(example_dir)

    if _USE_PREBUILT:
        _deploy_prebuilt(example_dir, example_name, canister_names, canister_configs)
    else:
        _deploy_with_build(example_dir, example_name, canister_names)

    canister_ids = {}
    for name in canister_names:
        cid = _get_canister_id(example_dir, name)
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


def _deploy_with_build(example_dir, example_name, canister_names):
    """Full build + deploy via icp deploy."""
    result = subprocess.run(
        ["icp", "deploy"],
        cwd=example_dir,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode != 0:
        _wait_for_canisters(example_dir, canister_names, timeout=3600)


def _deploy_prebuilt(example_dir, example_name, canister_names, canister_configs):
    """Deploy pre-built WASMs without running the build step.

    Uses icp canister create + icp canister install --wasm for each canister.
    """
    for name in canister_names:
        result = subprocess.run(
            ["icp", "canister", "create", name],
            cwd=example_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"icp canister create {name} failed for {example_name}: {result.stderr[-300:]}"
            )

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

            cmd = ["icp", "canister", "install", name, "--wasm", wasm_path, "-y"]
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


def _wait_for_canisters(example_dir, canister_names, timeout=3600):
    """Poll until all canisters have a module hash (= installed)."""
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(15)
        all_ready = True
        for name in canister_names:
            try:
                status = subprocess.run(
                    ["icp", "canister", "status", name],
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
    """Get canister ID from .icp/cache/mappings/local.ids.json."""
    ids_file = os.path.join(example_dir, ".icp", "cache", "mappings", "local.ids.json")
    if os.path.exists(ids_file):
        try:
            with open(ids_file) as f:
                ids = json.load(f)
            cid = ids.get(canister_name)
            if isinstance(cid, str):
                return cid
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: parse icp canister status output
    try:
        result = subprocess.run(
            ["icp", "canister", "status", canister_name],
            cwd=example_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            m = re.search(r'Canister Id:\s*(\S+)', result.stdout)
            if m:
                return m.group(1)
    except (subprocess.TimeoutExpired, OSError):
        pass

    return None


# ---------------------------------------------------------------------------
# Canister call helpers
# ---------------------------------------------------------------------------

def call_canister(canister_id, method, args=None, *, example_dir=None, update=False):
    """Call a canister method via icp-cli and return the parsed result.

    Runs from the fixture directory so the project-local network is used.
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
