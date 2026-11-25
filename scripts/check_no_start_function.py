"""Fail if a canister template wasm has a start function.

A wasm start function runs when the module is instantiated, before
canister_init, in the IC's "start" mode, where calls such as ic0.time trap.
Rust 1.100.0 gave the template one (_initialize), and every install of a
canister built on it failed with "ic0_time cannot be executed in start mode".

Usage: python3 scripts/check_no_start_function.py TEMPLATE.wasm [...]
"""

import sys

START_SECTION = 8


def read_leb128(data, pos):
    value = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value, pos


def has_start_section(data):
    if data[:4] != b"\0asm":
        raise ValueError("not a wasm module")
    pos = 8  # magic and version
    while pos < len(data):
        section_id = data[pos]
        size, pos = read_leb128(data, pos + 1)
        if section_id == START_SECTION:
            return True
        pos += size
    return False


def main(paths):
    found = [path for path in paths if has_start_section(open(path, "rb").read())]
    for path in found:
        print(f"::error::{path} has a wasm start function: every canister built on it "
              "traps at install. Check the Rust toolchain (RUST_VERSION).")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
