#!/usr/bin/env python3
"""
Upload a WASM file to the deployer canister.

Usage:
    python3 scripts/upload_wasm.py <version> <wasm_file> [--network <network>] [--canister-id <id>] [--description <desc>]

Example:
    python3 scripts/upload_wasm.py 0.11.22 ~/.config/basilisk/0.11.22/cpython_canister_template.wasm --network local
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys

CHUNK_SIZE = 200_000  # 200 KB per chunk (base64 decode + file write must fit in instruction budget)


def dfx_call(canister, method, arg, network="local"):
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(arg)
        arg_file = f.name
    try:
        cmd = ["dfx", "canister", "call", canister, method, "--argument-file", arg_file, "--network", network]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: {' '.join(cmd)}")
            print(result.stderr)
            sys.exit(1)
        return result.stdout.strip()
    finally:
        os.remove(arg_file)


def main():
    parser = argparse.ArgumentParser(description="Upload WASM to deployer canister")
    parser.add_argument("version", help="Version string (e.g., 0.11.22)")
    parser.add_argument("wasm_file", help="Path to .wasm file")
    parser.add_argument("--network", default="local", help="DFX network (default: local)")
    parser.add_argument("--canister-id", default="deployer", help="Deployer canister name or ID")
    parser.add_argument("--description", default="", help="Version description")
    args = parser.parse_args()

    with open(args.wasm_file, "rb") as f:
        wasm_data = f.read()

    wasm_hash = hashlib.sha256(wasm_data).hexdigest()
    total_size = len(wasm_data)
    num_chunks = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE

    print(f"Uploading {args.wasm_file}")
    print(f"  Version:    {args.version}")
    print(f"  Size:       {total_size:,} bytes")
    print(f"  SHA-256:    {wasm_hash}")
    print(f"  Chunks:     {num_chunks}")
    print(f"  Network:    {args.network}")
    print(f"  Canister:   {args.canister_id}")
    print()

    for i in range(num_chunks):
        offset = i * CHUNK_SIZE
        chunk = wasm_data[offset:offset + CHUNK_SIZE]
        chunk_b64 = base64.b64encode(chunk).decode("ascii")

        payload = json.dumps({
            "version": args.version,
            "chunk_index": i,
            "data": chunk_b64,
        })

        print(f"  Uploading chunk {i + 1}/{num_chunks} ({len(chunk):,} bytes)...", end=" ", flush=True)
        output = dfx_call(args.canister_id, "upload_wasm_chunk", f'({json.dumps(payload)})', args.network)
        print("OK")

    print()
    print("Finalizing version...")
    payload = json.dumps({
        "version": args.version,
        "description": args.description,
        "expected_hash": wasm_hash,
    })
    output = dfx_call(args.canister_id, "finalize_version", f'({json.dumps(payload)})', args.network)
    print(f"  Result: {output}")
    print()
    print("Done!")


if __name__ == "__main__":
    main()
