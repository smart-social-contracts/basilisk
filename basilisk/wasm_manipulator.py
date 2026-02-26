"""
Wasm binary manipulator for the CPython canister template pattern.

Injects Python source code and method metadata as passive data segments
into a pre-compiled canister template wasm, and adds canister_query/update
export stubs that call the generic execute_query_method/execute_update_method
functions in the template.

This is the basilisk equivalent of azle's manipulate.ts, but written in
Python for consistency with the rest of the basilisk build toolchain.

Architecture:
  1. Read the pre-compiled template wasm binary
  2. Parse enough of the wasm structure to locate sections
  3. Add two passive data segments (Python source + method metadata JSON)
  4. For each method, add a tiny function that calls execute_query/update_method(index)
  5. Add canister_query/canister_update exports for each method
  6. Write the modified wasm binary

Wasm binary format reference: https://webassembly.github.io/spec/core/binary/
"""

import json
import struct
import os
from typing import List, Dict, Tuple, Optional


# ─── Wasm section IDs ───────────────────────────────────────────────────────

SECTION_TYPE = 1
SECTION_IMPORT = 2
SECTION_FUNCTION = 3
SECTION_TABLE = 4
SECTION_MEMORY = 5
SECTION_GLOBAL = 6
SECTION_EXPORT = 7
SECTION_START = 8
SECTION_ELEMENT = 9
SECTION_DATACOUNT = 12
SECTION_CODE = 10
SECTION_DATA = 11


# ─── LEB128 encoding/decoding ───────────────────────────────────────────────

def encode_unsigned_leb128(value: int) -> bytes:
    """Encode an unsigned integer as LEB128."""
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value != 0:
            byte |= 0x80
        result.append(byte)
        if value == 0:
            break
    return bytes(result)


def encode_signed_leb128(value: int) -> bytes:
    """Encode a signed integer as LEB128."""
    result = bytearray()
    more = True
    while more:
        byte = value & 0x7F
        value >>= 7
        if (value == 0 and (byte & 0x40) == 0) or (value == -1 and (byte & 0x40) != 0):
            more = False
        else:
            byte |= 0x80
        result.append(byte)
    return bytes(result)


def decode_unsigned_leb128(data: bytes, offset: int) -> Tuple[int, int]:
    """Decode an unsigned LEB128 integer. Returns (value, new_offset)."""
    result = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            break
        shift += 7
    return result, offset


def encode_name(name: str) -> bytes:
    """Encode a wasm name (length-prefixed UTF-8)."""
    encoded = name.encode("utf-8")
    return encode_unsigned_leb128(len(encoded)) + encoded


# ─── Wasm section parsing ───────────────────────────────────────────────────

class WasmSection:
    """A parsed wasm section."""
    def __init__(self, section_id: int, offset: int, size: int, content_offset: int):
        self.section_id = section_id
        self.offset = offset  # offset of section ID byte
        self.size = size      # size of section content
        self.content_offset = content_offset  # offset of section content


def parse_sections(wasm: bytes) -> List[WasmSection]:
    """Parse all sections from a wasm binary."""
    assert wasm[:4] == b'\x00asm', "Not a valid wasm binary"
    assert struct.unpack('<I', wasm[4:8])[0] == 1, "Unsupported wasm version"

    sections = []
    offset = 8

    while offset < len(wasm):
        section_id = wasm[offset]
        section_start = offset
        offset += 1
        section_size, offset = decode_unsigned_leb128(wasm, offset)
        content_offset = offset
        sections.append(WasmSection(section_id, section_start, section_size, content_offset))
        offset += section_size

    return sections


def find_section(sections: List[WasmSection], section_id: int) -> Optional[WasmSection]:
    """Find a section by ID."""
    for s in sections:
        if s.section_id == section_id:
            return s
    return None


# ─── Wasm export parsing ────────────────────────────────────────────────────

def parse_exports(wasm: bytes, export_section: WasmSection) -> List[Dict]:
    """Parse the export section to find function exports."""
    offset = export_section.content_offset
    count, offset = decode_unsigned_leb128(wasm, offset)
    exports = []
    for _ in range(count):
        name_len, offset = decode_unsigned_leb128(wasm, offset)
        name = wasm[offset:offset + name_len].decode("utf-8")
        offset += name_len
        kind = wasm[offset]
        offset += 1
        index, offset = decode_unsigned_leb128(wasm, offset)
        exports.append({"name": name, "kind": kind, "index": index})
    return exports


def find_function_index(exports: List[Dict], name: str) -> Optional[int]:
    """Find a function export index by name."""
    for exp in exports:
        if exp["name"] == name and exp["kind"] == 0:  # 0 = function
            return exp["index"]
    return None


# ─── Main manipulation function ─────────────────────────────────────────────

def manipulate_wasm(
    template_wasm_path: str,
    output_wasm_path: str,
    python_source: str,
    methods: List[Dict],
) -> None:
    """
    Inject Python source and method metadata into the template wasm.

    Args:
        template_wasm_path: Path to the pre-compiled template wasm
        output_wasm_path: Path to write the modified wasm
        python_source: The user's Python source code (UTF-8)
        methods: List of method dicts with keys: name, method_type, params, returns
            e.g. [{"name": "greet", "method_type": "query", "params": [{"name": "name", "candid_type": "text"}], "returns": "text"}]
    """
    with open(template_wasm_path, "rb") as f:
        wasm = f.read()

    sections = parse_sections(wasm)
    exports_section = find_section(sections, SECTION_EXPORT)
    if exports_section is None:
        raise ValueError("Template wasm has no export section")

    exports = parse_exports(wasm, exports_section)

    # Find the execute_query_method and execute_update_method function indices
    query_dispatcher_idx = find_function_index(exports, "execute_query_method")
    update_dispatcher_idx = find_function_index(exports, "execute_update_method")
    if query_dispatcher_idx is None or update_dispatcher_idx is None:
        raise ValueError(
            "Template wasm missing execute_query_method or execute_update_method exports"
        )

    # Encode the data to inject
    python_bytes = python_source.encode("utf-8")
    method_meta_json = json.dumps(methods).encode("utf-8")

    # Build the new wasm with:
    # 1. Additional function types (for method stubs)
    # 2. Additional functions (method stubs that call dispatcher)
    # 3. Additional exports (canister_query/canister_update)
    # 4. Additional data segments (Python source + method metadata)
    #
    # For simplicity, we use a two-pass approach:
    # Pass 1: Count existing functions, types, etc.
    # Pass 2: Append new sections/entries

    # For now, we use a simpler approach: embed the Python source and metadata
    # as global byte arrays that the template reads at init time, and add
    # wrapper functions + exports for each canister method.

    # Strategy: Instead of passive data segments (which require memory.init
    # instructions that are hard to inject), we embed the data in the
    # existing data section as active segments at a known offset, and
    # patch the size-returning functions.
    #
    # Even simpler: We create a new wasm that wraps the template by
    # appending to sections. The key insight is that we can add new
    # exports that reference new functions which are thin wrappers
    # calling the existing dispatcher functions.

    # For the MVP, we'll use a different approach: write the Python source
    # and metadata to files that the init code reads via WASI.
    # But WASI file access isn't available after wasi2ic...
    #
    # So let's use the custom section approach: add custom sections that
    # the Rust code reads. Actually, custom sections aren't accessible
    # at runtime either.
    #
    # The correct approach: active data segments. We'll add active data
    # segments that write the Python source and metadata to known memory
    # locations, and patch the placeholder functions to return the correct
    # sizes and read from those locations.
    #
    # Actually, the simplest correct approach for MVP:
    # Just reconstruct the entire wasm binary, copying all existing sections
    # and modifying/adding the ones we need.

    modified_wasm = build_modified_wasm(
        wasm, sections, exports,
        python_bytes, method_meta_json,
        methods,
        query_dispatcher_idx,
        update_dispatcher_idx,
    )

    with open(output_wasm_path, "wb") as f:
        f.write(modified_wasm)

    print(f"Modified wasm written to {output_wasm_path}")
    print(f"  Python source: {len(python_bytes)} bytes")
    print(f"  Method metadata: {len(method_meta_json)} bytes")
    print(f"  Methods: {len(methods)}")
    original_size = len(wasm)
    new_size = len(modified_wasm)
    print(f"  Size: {original_size} -> {new_size} (+{new_size - original_size} bytes)")


def build_modified_wasm(
    wasm: bytes,
    sections: List[WasmSection],
    exports: List[Dict],
    python_bytes: bytes,
    method_meta_bytes: bytes,
    methods: List[Dict],
    query_dispatcher_idx: int,
    update_dispatcher_idx: int,
) -> bytes:
    """
    Build the modified wasm binary with injected data and method exports.

    For each canister method, we need to:
    1. Add a function type: () -> () (void to void, since we use reply_raw)
    2. Add a function that calls execute_query/update_method(index)
    3. Add an export with the canister_query/canister_update name

    For the data, we need to:
    1. Add passive data segments containing the Python source and metadata
    2. Make the placeholder size functions return the correct sizes
    3. Make the placeholder init functions execute memory.init

    Since modifying existing function bodies is complex, we use a simpler
    approach for the data: add a custom "basilisk_data" section that the
    Rust code reads, or add global variables.

    MVP approach: We store the data in globals (as byte arrays encoded
    in data segments) and patch the placeholder functions.

    Actually, the cleanest MVP approach:
    - Add the data as new active data segments
    - The Rust code declares mutable globals for the data pointers/sizes
    - The data segments initialize memory at __heap_base + offset
    - The placeholder functions read from those known offsets

    But this requires knowing __heap_base and coordinating memory layout.

    Simplest possible approach that works:
    - Embed data as DATA section entries (active segments at offset 0
      in a secondary memory would work, but wasm MVP has only 1 memory)
    - Use global variables to communicate sizes

    Let me use the approach azle uses: passive data segments + memory.init.
    This requires adding:
    1. New data segments in the data section (passive = no memory target)
    2. New functions that call memory.init to copy data to a buffer
    3. Patch the size functions to return correct values

    For the method stubs:
    1. Find or add the function type for (i32) -> ()
    2. Add new functions: each one does (i32.const INDEX, call DISPATCHER)
    3. Add new exports: canister_query "name" -> new_func_idx

    Let's build this step by step.
    """

    # ─── Step 1: Parse existing section data ─────────────────────────────

    type_section = find_section(sections, SECTION_TYPE)
    func_section = find_section(sections, SECTION_FUNCTION)
    code_section = find_section(sections, SECTION_CODE)
    data_section = find_section(sections, SECTION_DATA)
    datacount_section = find_section(sections, SECTION_DATACOUNT)
    import_section = find_section(sections, SECTION_IMPORT)

    # Count existing entries
    existing_type_count = 0
    if type_section:
        existing_type_count, _ = decode_unsigned_leb128(wasm, type_section.content_offset)

    existing_func_count = 0
    if func_section:
        existing_func_count, _ = decode_unsigned_leb128(wasm, func_section.content_offset)

    existing_import_func_count = 0
    if import_section:
        offset = import_section.content_offset
        import_count, offset = decode_unsigned_leb128(wasm, offset)
        for _ in range(import_count):
            # module name
            name_len, offset = decode_unsigned_leb128(wasm, offset)
            offset += name_len
            # field name
            name_len, offset = decode_unsigned_leb128(wasm, offset)
            offset += name_len
            # kind
            kind = wasm[offset]
            offset += 1
            if kind == 0:  # function import
                _, offset = decode_unsigned_leb128(wasm, offset)
                existing_import_func_count += 1
            elif kind == 1:  # table
                offset += 1  # elemtype
                _, offset = decode_unsigned_leb128(wasm, offset)  # limits flag
                # This is simplified; real parsing would check limits flag
                if wasm[offset - 1] & 1:
                    _, offset = decode_unsigned_leb128(wasm, offset)
            elif kind == 2:  # memory
                flag = wasm[offset]
                offset += 1
                _, offset = decode_unsigned_leb128(wasm, offset)
                if flag & 1:
                    _, offset = decode_unsigned_leb128(wasm, offset)
            elif kind == 3:  # global
                offset += 1  # valtype
                offset += 1  # mutability
                # init expr - skip until 0x0b (end)
                while wasm[offset] != 0x0B:
                    offset += 1
                offset += 1

    total_existing_funcs = existing_import_func_count + existing_func_count

    existing_data_count = 0
    if datacount_section:
        existing_data_count, _ = decode_unsigned_leb128(wasm, datacount_section.content_offset)

    # ─── Step 2: Determine new entries needed ────────────────────────────

    # We need a function type for the method stubs: () -> ()
    # The stubs will: i32.const <index>, call <dispatcher>, return
    # Actually dispatcher is execute_query_method(i32) or execute_update_method(i32)
    # which takes an i32 parameter. But canister methods take no explicit params
    # (they read from arg_data_raw). So stub type is () -> ().

    # New type: () -> ()
    void_to_void_type = b'\x60\x00\x00'  # func type, 0 params, 0 results

    # New data segments (passive)
    new_data_segment_count = 2  # python source + method metadata
    python_data_segment_idx = existing_data_count
    meta_data_segment_idx = existing_data_count + 1

    # New functions: one per method
    new_func_count = len(methods)

    # ─── Step 3: Rebuild wasm binary ─────────────────────────────────────

    # We rebuild by copying sections and modifying the ones we need.
    # Section order in wasm: type, import, func, table, memory, global,
    #                        export, start, element, datacount, code, data

    output = bytearray()
    output.extend(b'\x00asm')  # magic
    output.extend(struct.pack('<I', 1))  # version

    for section in sections:
        section_content = wasm[section.content_offset:section.content_offset + section.size]

        if section.section_id == SECTION_TYPE:
            # Append the void->void type
            new_count = existing_type_count + 1
            _, first_entry_offset = decode_unsigned_leb128(wasm, section.content_offset)
            rest = wasm[first_entry_offset:section.content_offset + section.size]
            new_content = encode_unsigned_leb128(new_count) + rest + void_to_void_type
            write_section(output, SECTION_TYPE, new_content)

        elif section.section_id == SECTION_FUNCTION:
            # Append new function type indices
            new_count = existing_func_count + new_func_count
            _, first_entry_offset = decode_unsigned_leb128(wasm, section.content_offset)
            rest = wasm[first_entry_offset:section.content_offset + section.size]
            new_type_idx = existing_type_count  # index of our new void->void type
            new_entries = b''.join(
                encode_unsigned_leb128(new_type_idx) for _ in range(new_func_count)
            )
            new_content = encode_unsigned_leb128(new_count) + rest + new_entries
            write_section(output, SECTION_FUNCTION, new_content)

        elif section.section_id == SECTION_EXPORT:
            # Append new canister method exports
            export_count = len(exports)
            new_export_count = export_count + len(methods)
            _, first_entry_offset = decode_unsigned_leb128(wasm, section.content_offset)
            rest = wasm[first_entry_offset:section.content_offset + section.size]
            new_entries = bytearray()
            for i, method in enumerate(methods):
                func_idx = total_existing_funcs + i
                # Export name is "canister_query <name>" or "canister_update <name>"
                export_name = f"canister_{method['method_type']} {method['name']}"
                new_entries.extend(encode_name(export_name))
                new_entries.extend(b'\x00')  # kind = function
                new_entries.extend(encode_unsigned_leb128(func_idx))
            new_content = encode_unsigned_leb128(new_export_count) + rest + bytes(new_entries)
            write_section(output, SECTION_EXPORT, new_content)

        elif section.section_id == SECTION_DATACOUNT:
            # Update data segment count
            new_count = existing_data_count + new_data_segment_count
            new_content = encode_unsigned_leb128(new_count)
            write_section(output, SECTION_DATACOUNT, new_content)

        elif section.section_id == SECTION_CODE:
            # Append new function bodies (method stubs)
            code_count = existing_func_count
            new_code_count = code_count + new_func_count
            _, first_entry_offset = decode_unsigned_leb128(wasm, section.content_offset)
            rest = wasm[first_entry_offset:section.content_offset + section.size]

            new_code_entries = bytearray()
            for i, method in enumerate(methods):
                # Function body: i32.const <index>, call <dispatcher>, end
                if method["method_type"] == "query":
                    dispatcher_idx = query_dispatcher_idx
                else:
                    dispatcher_idx = update_dispatcher_idx

                body = bytearray()
                body.extend(b'\x00')  # 0 local declarations
                body.extend(b'\x41')  # i32.const
                body.extend(encode_signed_leb128(i))
                body.extend(b'\x10')  # call
                body.extend(encode_unsigned_leb128(dispatcher_idx))
                body.extend(b'\x0b')  # end

                # Function body is prefixed with its byte length
                new_code_entries.extend(encode_unsigned_leb128(len(body)))
                new_code_entries.extend(body)

            new_content = encode_unsigned_leb128(new_code_count) + rest + bytes(new_code_entries)
            write_section(output, SECTION_CODE, new_content)

        elif section.section_id == SECTION_DATA:
            # Append passive data segments for Python source and method metadata
            _, first_entry_offset = decode_unsigned_leb128(wasm, section.content_offset)
            rest = wasm[first_entry_offset:section.content_offset + section.size]
            new_count = existing_data_count + new_data_segment_count

            new_data_entries = bytearray()

            # Passive data segment for Python source
            # Passive segment: flag=1, then data bytes
            new_data_entries.extend(b'\x01')  # passive flag
            new_data_entries.extend(encode_unsigned_leb128(len(python_bytes)))
            new_data_entries.extend(python_bytes)

            # Passive data segment for method metadata
            new_data_entries.extend(b'\x01')  # passive flag
            new_data_entries.extend(encode_unsigned_leb128(len(method_meta_bytes)))
            new_data_entries.extend(method_meta_bytes)

            new_content = encode_unsigned_leb128(new_count) + rest + bytes(new_data_entries)
            write_section(output, SECTION_DATA, new_content)

        else:
            # Copy section as-is
            write_section(output, section.section_id, section_content)

    return bytes(output)


def write_section(output: bytearray, section_id: int, content: bytes) -> None:
    """Write a wasm section to the output buffer."""
    output.append(section_id)
    output.extend(encode_unsigned_leb128(len(content)))
    output.extend(content)


# ─── Python source extraction ───────────────────────────────────────────────

def extract_methods_from_python(python_source: str) -> List[Dict]:
    """
    Extract method declarations from Python source code.

    Looks for @query and @update decorators and extracts function signatures.
    Returns a list of method metadata dicts.

    Example:
        @query
        def greet(name: str) -> str:
            return f"Hello, {name}!"

    Produces:
        [{"name": "greet", "method_type": "query",
          "params": [{"name": "name", "candid_type": "text"}],
          "returns": "text"}]
    """
    import ast

    tree = ast.parse(python_source)
    methods = []

    # Map Python type annotations to Candid types
    type_map = {
        "str": "text",
        "int": "int",
        "float": "float64",
        "bool": "bool",
        "bytes": "blob",
        "None": "null",
        "nat": "nat",
        "nat8": "nat8",
        "nat16": "nat16",
        "nat32": "nat32",
        "nat64": "nat64",
        "int8": "int8",
        "int16": "int16",
        "int32": "int32",
        "int64": "int64",
        "float32": "float32",
        "float64": "float64",
        "text": "text",
        "blob": "blob",
        "Principal": "principal",
    }

    def get_candid_type(annotation) -> str:
        """Convert a Python type annotation to a Candid type string."""
        if annotation is None:
            return "null"
        if isinstance(annotation, ast.Constant) and annotation.value is None:
            return "null"
        if isinstance(annotation, ast.Name):
            return type_map.get(annotation.id, "text")
        if isinstance(annotation, ast.Attribute):
            # e.g., basilisk.nat64
            return type_map.get(annotation.attr, "text")
        if isinstance(annotation, ast.Subscript):
            # e.g., list[int], Optional[str]
            if isinstance(annotation.value, ast.Name):
                if annotation.value.id == "list":
                    inner = get_candid_type(annotation.slice)
                    return f"vec {inner}"
                if annotation.value.id in ("Optional", "Opt"):
                    inner = get_candid_type(annotation.slice)
                    return f"opt {inner}"
        return "text"  # fallback

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        method_type = None
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                if decorator.id == "query":
                    method_type = "query"
                elif decorator.id == "update":
                    method_type = "update"
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    if decorator.func.id == "query":
                        method_type = "query"
                    elif decorator.func.id == "update":
                        method_type = "update"
            elif isinstance(decorator, ast.Attribute):
                if decorator.attr == "query":
                    method_type = "query"
                elif decorator.attr == "update":
                    method_type = "update"

        if method_type is None:
            continue

        params = []
        for arg in node.args.args:
            param_name = arg.arg
            if param_name == "self":
                continue
            candid_type = get_candid_type(arg.annotation)
            params.append({"name": param_name, "candid_type": candid_type})

        return_type = get_candid_type(node.returns)

        methods.append({
            "name": node.name,
            "method_type": method_type,
            "params": params,
            "returns": return_type,
        })

    return methods


def generate_candid_from_methods(methods: List[Dict]) -> str:
    """Generate a .did file from method metadata."""
    lines = []
    for method in methods:
        params = ", ".join(
            p["candid_type"] for p in method["params"]
        )
        returns = method["returns"] if method["returns"] != "null" else ""
        mode = " query" if method["method_type"] == "query" else ""
        lines.append(f'  "{method["name"]}" : ({params}) -> ({returns}){mode};')

    return "service : {\n" + "\n".join(lines) + "\n}\n"


# ─── CLI entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python wasm_manipulator.py <template.wasm> <output.wasm> <source.py> [methods.json]")
        sys.exit(1)

    template_path = sys.argv[1]
    output_path = sys.argv[2]
    source_path = sys.argv[3]

    with open(source_path, "r") as f:
        python_source = f.read()

    if len(sys.argv) > 4:
        with open(sys.argv[4], "r") as f:
            methods = json.load(f)
    else:
        methods = extract_methods_from_python(python_source)

    print(f"Extracted {len(methods)} canister methods:")
    for m in methods:
        print(f"  @{m['method_type']} {m['name']}({', '.join(p['name'] + ': ' + p['candid_type'] for p in m['params'])}) -> {m['returns']}")

    manipulate_wasm(template_path, output_path, python_source, methods)
