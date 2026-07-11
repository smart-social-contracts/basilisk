#!/usr/bin/env python3
"""Build all example canister WASMs in a single pass.

Reads each example's icp.yaml, runs
`python -m basilisk <name> <main>` for every canister, and collects
the output WASMs + .did files.

Usage:
    python scripts/build_all_wasms.py [example_dir ...]

If no arguments given, builds ALL examples listed in the CI matrix.
"""

import os
import subprocess
import sys
import time

try:
    import yaml
except ImportError:
    yaml = None

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXAMPLES_DIR = os.path.join(REPO_ROOT, "tests", "fixtures")

# All examples in the CI matrix
ALL_EXAMPLES = [
    "all_stable_structures",
    "annotated_tests",
    "blob_array",
    "bytes",
    "call_raw",
    "complex_init",
    "complex_types",
    "counter",
    "cycles",
    "date",
    "file_store_limits",
    "filesystem",
    "generators",
    "guard_functions",
    "heartbeat",
    "ic_api",
    "imports",
    "init_and_post_upgrade_recovery",
    "init",
    "inspect_message",
    "key_value_store",
    "keywords",
    "list_of_lists",
    "management_canister",
    "manual_reply",
    "motoko_examples/calc",
    "motoko_examples/counter",
    "motoko_examples/echo",
    "motoko_examples/factorial",
    "motoko_examples/hello",
    "motoko_examples/hello-world",
    "motoko_examples/persistent-storage",
    "motoko_examples/phone-book",
    "motoko_examples/quicksort",
    "motoko_examples/simple-to-do",
    "motoko_examples/superheroes",
    "motoko_examples/whoami",
    "notify_raw",
    "null_example",
    "optional_types",
    "outgoing_http_requests",
    "primitive_types",
    "principal",
    "query",
    "randomness",
    "rejections",
    "service",
    "simple_erc20",
    "simple_user_accounts",
    "stable_memory",
    "stable_structures",
    "stdlib",
    "subinterpreter",
    "timers",
    "tuple_types",
    "update",
]


def _read_canister_config(example_dir):
    """Read canister config from icp.yaml, returning {name: {"main": str}}."""
    icp_yaml_path = os.path.join(example_dir, "icp.yaml")

    if os.path.exists(icp_yaml_path):
        if yaml is None:
            raise ImportError("PyYAML is required to read icp.yaml — pip install pyyaml")
        with open(icp_yaml_path) as f:
            config = yaml.safe_load(f)
        result = {}
        for canister in config.get("canisters", []):
            name = canister["name"]
            main_file = _extract_main_from_build(canister)
            result[name] = {"main": main_file}
        return result

    return {}


def _extract_main_from_build(canister_config):
    """Extract Python entry point from icp.yaml build commands."""
    for step in canister_config.get("build", {}).get("steps", []):
        for cmd in step.get("commands", []):
            if "python" in cmd and "basilisk" in cmd:
                parts = cmd.split()
                for i, part in enumerate(parts):
                    if part == "basilisk" and i + 2 < len(parts):
                        return parts[i + 2]
    return ""


def build_example(example_name: str) -> bool:
    """Build all canisters in a single example directory. Returns True on success."""
    example_dir = os.path.join(EXAMPLES_DIR, example_name)

    canisters = _read_canister_config(example_dir)
    if not canisters:
        print(f"  SKIP {example_name}: no icp.yaml")
        return False

    all_ok = True
    for canister_name, canister_config in canisters.items():
        main_file = canister_config.get("main", "")
        if not main_file:
            print(f"  SKIP {example_name}/{canister_name}: no main entry")
            continue

        candid_path = f".basilisk/{canister_name}/{canister_name}.did"

        env = os.environ.copy()
        env["CANISTER_CANDID_PATH"] = candid_path

        print(f"  BUILD {example_name}/{canister_name} ({main_file})")
        t0 = time.time()
        result = subprocess.run(
            ["python", "-m", "basilisk", canister_name, main_file],
            cwd=example_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        elapsed = time.time() - t0

        if result.returncode != 0:
            print(f"  FAIL {example_name}/{canister_name} ({elapsed:.1f}s)")
            print(f"    stderr: {result.stderr[-500:]}")
            all_ok = False
        else:
            wasm_path = os.path.join(example_dir, ".basilisk", canister_name, f"{canister_name}.wasm")
            did_path = os.path.join(example_dir, candid_path)
            if os.path.exists(wasm_path):
                if os.path.exists(did_path):
                    subprocess.run(
                        ["ic-wasm", wasm_path, "-o", wasm_path,
                         "metadata", "candid:service", "-f", did_path,
                         "-v", "public", "--keep-name-section"],
                        cwd=example_dir,
                        capture_output=True,
                        timeout=30,
                    )
                size_mb = os.path.getsize(wasm_path) / (1024 * 1024)
                print(f"    OK {size_mb:.1f} MB ({elapsed:.1f}s)")
            else:
                print(f"    WARN: WASM not found at {wasm_path} ({elapsed:.1f}s)")

    return all_ok


def main():
    examples = sys.argv[1:] if len(sys.argv) > 1 else ALL_EXAMPLES

    print(f"Building {len(examples)} examples...")
    t_start = time.time()

    results = {}
    for i, example in enumerate(examples, 1):
        print(f"\n[{i}/{len(examples)}] {example}")
        results[example] = build_example(example)

    elapsed = time.time() - t_start
    ok = sum(1 for v in results.values() if v)
    fail = sum(1 for v in results.values() if not v)
    print(f"\n{'='*60}")
    print(f"Built {ok}/{len(examples)} examples in {elapsed:.0f}s ({fail} failed)")

    if fail:
        print("\nFailed examples:")
        for name, success in results.items():
            if not success:
                print(f"  - {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
