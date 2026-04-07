#!/usr/bin/env python3
"""Build all example canister WASMs in a single pass.

Reads each example's dfx.json, runs `python -m basilisk <name> <main>` for
every canister, and collects the output WASMs + .did files.

Usage:
    python scripts/build_all_wasms.py [example_dir ...]

If no arguments given, builds ALL examples listed in the CI matrix.
"""

import json
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXAMPLES_DIR = os.path.join(REPO_ROOT, "tests", "fixtures")

# All examples in the CI matrix
ALL_EXAMPLES = [
    "annotated_tests",
    "audio_recorder",
    "blob_array",
    "bytes",
    "call_raw",
    "complex_init",
    "complex_types",
    "counter",
    "cycles",
    "date",
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
    "timers",
    "tuple_types",
    "update",
]


def build_example(example_name: str) -> bool:
    """Build all canisters in a single example directory. Returns True on success."""
    example_dir = os.path.join(EXAMPLES_DIR, example_name)
    dfx_json_path = os.path.join(example_dir, "dfx.json")

    if not os.path.exists(dfx_json_path):
        print(f"  SKIP {example_name}: no dfx.json")
        return False

    with open(dfx_json_path) as f:
        dfx_config = json.load(f)

    canisters = dfx_config.get("canisters", {})
    if not canisters:
        print(f"  SKIP {example_name}: no canisters in dfx.json")
        return False

    all_ok = True
    for canister_name, canister_config in canisters.items():
        main_file = canister_config.get("main", "")
        if not main_file:
            print(f"  SKIP {example_name}/{canister_name}: no main entry")
            continue

        # basilisk requires CANISTER_CANDID_PATH (normally set by dfx).
        # Compute the .did output path the same way dfx would.
        candid_path = canister_config.get("candid", "")
        if not candid_path:
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
            # Check output WASM exists
            wasm_path = os.path.join(example_dir, ".basilisk", canister_name, f"{canister_name}.wasm")
            if os.path.exists(wasm_path):
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
