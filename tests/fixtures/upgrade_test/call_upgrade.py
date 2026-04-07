#!/usr/bin/env python3
"""
Upload WASM in chunks using IC's chunked code API and trigger upgrade
"""

import hashlib
import subprocess
import sys

CHUNK_SIZE = 900_000  # ~900KB per chunk


def call_canister(method: str, arg: str) -> tuple[int, str, str]:
    """Call controller canister method with argument from file"""
    with open("/tmp/canister_arg.txt", "w") as f:
        f.write(arg)
    
    result = subprocess.run(
        ["dfx", "canister", "call", "controller", method, "--argument-file", "/tmp/canister_arg.txt"],
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr


def main():
    if len(sys.argv) != 3:
        print("Usage: python call_upgrade.py <target_canister_id> <wasm_path>")
        sys.exit(1)
    
    target_id = sys.argv[1]
    wasm_path = sys.argv[2]
    
    # Read WASM file
    with open(wasm_path, "rb") as f:
        wasm_bytes = f.read()
    
    total_size = len(wasm_bytes)
    print(f"WASM size: {total_size} bytes")
    
    # Compute SHA-256 hash of entire WASM
    wasm_hash = hashlib.sha256(wasm_bytes).digest()
    print(f"WASM SHA-256: {wasm_hash.hex()}")
    
    # Split into chunks
    chunks = []
    for i in range(0, total_size, CHUNK_SIZE):
        chunks.append(wasm_bytes[i:i + CHUNK_SIZE])
    
    print(f"Uploading {len(chunks)} chunks to IC chunk store...")
    
    # Upload each chunk (new API: no chunk index, just target and chunk)
    for i, chunk in enumerate(chunks):
        # Candid blob format: \xx escape sequences for each byte
        chunk_escaped = "".join(f"\\{b:02x}" for b in chunk)
        arg = f'(principal "{target_id}", blob "{chunk_escaped}")'
        
        code, stdout, stderr = call_canister("upload_wasm_chunk", arg)
        if code != 0:
            print(f"Error uploading chunk {i}: {stderr}")
            return 1
        
        print(f"  Chunk {i + 1}/{len(chunks)}: {len(chunk)} bytes - {stdout.strip()}")
    
    # Execute chunked upgrade with WASM hash
    print(f"\nExecuting chunked upgrade...")
    wasm_hash_escaped = "".join(f"\\{b:02x}" for b in wasm_hash)
    arg = f'(principal "{target_id}", blob "{wasm_hash_escaped}")'
    code, stdout, stderr = call_canister("execute_chunked_upgrade", arg)
    
    print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    
    return code


if __name__ == "__main__":
    sys.exit(main())
