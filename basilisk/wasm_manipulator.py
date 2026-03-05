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
    type_defs: Optional[Dict[str, str]] = None,
    lifecycle: Optional[Dict[str, Dict]] = None,
) -> None:
    """
    Inject Python source and method metadata into the template wasm.

    Args:
        template_wasm_path: Path to the pre-compiled template wasm
        output_wasm_path: Path to write the modified wasm
        python_source: The user's Python source code (UTF-8)
        methods: List of method dicts with keys: name, method_type, params, returns
            e.g. [{"name": "greet", "method_type": "query", "params": [{"name": "name", "candid_type": "text"}], "returns": "text"}]
        type_defs: Optional dict mapping type name -> Candid type definition string
            e.g. {"User": "record { id : text; username : text }"}
        lifecycle: Optional dict mapping lifecycle hook name -> method metadata
            e.g. {"init": {"name": "init_", "params": [...]}, "post_upgrade": {...}}
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

    # Encode the data to inject: wrap methods + type_defs + lifecycle in a single JSON object
    python_bytes = python_source.encode("utf-8")
    metadata = {
        "methods": methods,
        "type_defs": type_defs or {},
        "lifecycle": lifecycle or {},
    }
    method_meta_json = json.dumps(metadata).encode("utf-8")

    # Find placeholder function indices for patching
    placeholder_funcs = {}
    for name in [
        "python_source_passive_data_size",
        "method_meta_passive_data_size",
        "init_python_source_passive_data",
        "init_method_meta_passive_data",
    ]:
        idx = find_function_index(exports, name)
        if idx is None:
            raise ValueError(f"Template wasm missing placeholder export: {name}")
        placeholder_funcs[name] = idx

    modified_wasm = build_modified_wasm(
        wasm, sections, exports,
        python_bytes, method_meta_json,
        methods,
        query_dispatcher_idx,
        update_dispatcher_idx,
        placeholder_funcs,
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


def _resolve_wrapper_inner_func(
    wasm: bytes,
    code_section: WasmSection,
    wrapper_code_idx: int,
    import_func_count: int,
) -> int:
    """
    Resolve wasm-ld wrapper indirection to find the actual inner function.

    wasm-ld wraps exported C functions with a prologue/epilogue pattern:
        call <prologue>; call <real_body>; call <epilogue>; end

    This function extracts the 2nd call target (the real body) and returns
    its code section index. If the function doesn't match the wrapper pattern
    (e.g. it's already a simple body), returns the original index.
    """
    # Navigate to the wrapper function body
    offset = code_section.content_offset
    func_count, offset = decode_unsigned_leb128(wasm, offset)
    for i in range(wrapper_code_idx):
        body_size, offset = decode_unsigned_leb128(wasm, offset)
        offset += body_size
    body_size, offset = decode_unsigned_leb128(wasm, offset)
    body = wasm[offset:offset + body_size]

    # Check for wrapper patterns added by wasm-ld:
    #   Size funcs: call <prologue>; call <body>; call <epilogue>; end
    #   Init funcs: call <prologue>; local.get 0; call <body>; call <epilogue>; end
    # The inner body is always the second-to-last call instruction.
    pos = 0
    if body[pos] != 0x00:
        return wrapper_code_idx  # has locals, not a simple wrapper
    pos += 1

    call_targets = []
    while pos < len(body):
        opcode = body[pos]
        if opcode == 0x10:  # call
            pos += 1
            target, pos = decode_unsigned_leb128(body, pos)
            call_targets.append(target)
        elif opcode == 0x20:  # local.get (parameter passing)
            pos += 1
            _, pos = decode_unsigned_leb128(body, pos)  # skip local index
        elif opcode == 0x0b:  # end
            break
        else:
            return wrapper_code_idx  # unexpected opcode, not a wrapper

    if len(call_targets) == 3:
        # Wrapper pattern: prologue, real_body, epilogue
        inner_func_idx = call_targets[1]  # 2nd call = real body
        inner_code_idx = inner_func_idx - import_func_count
        return inner_code_idx

    # Not a wrapper — return original index (direct patch)
    return wrapper_code_idx


def build_modified_wasm(
    wasm: bytes,
    sections: List[WasmSection],
    exports: List[Dict],
    python_bytes: bytes,
    method_meta_bytes: bytes,
    methods: List[Dict],
    query_dispatcher_idx: int,
    update_dispatcher_idx: int,
    placeholder_funcs: Dict[str, int],
) -> bytes:
    """
    Build the modified wasm binary with injected data and method exports.

    This function:
    1. Adds passive data segments containing Python source + method metadata
    2. Patches 4 placeholder function bodies to read from those segments
    3. Adds method stub functions that call execute_query/update_method(index)
    4. Adds canister_query/canister_update exports for each method
    """

    # ─── Step 1: Parse existing section data ─────────────────────────────

    type_section = find_section(sections, SECTION_TYPE)
    func_section = find_section(sections, SECTION_FUNCTION)
    code_section = find_section(sections, SECTION_CODE)
    data_section = find_section(sections, SECTION_DATA)
    datacount_section = find_section(sections, SECTION_DATACOUNT)
    import_section = find_section(sections, SECTION_IMPORT)

    existing_type_count = 0
    if type_section:
        existing_type_count, _ = decode_unsigned_leb128(wasm, type_section.content_offset)

    existing_func_count = 0
    if func_section:
        existing_func_count, _ = decode_unsigned_leb128(wasm, func_section.content_offset)

    existing_import_func_count = count_import_functions(wasm, import_section)
    total_existing_funcs = existing_import_func_count + existing_func_count

    # Read existing data segment count from data section (not datacount section,
    # which may not exist in the original wasm)
    existing_data_count = 0
    if data_section:
        existing_data_count, _ = decode_unsigned_leb128(wasm, data_section.content_offset)
    elif datacount_section:
        existing_data_count, _ = decode_unsigned_leb128(wasm, datacount_section.content_offset)

    # ─── Step 2: Determine new entries ───────────────────────────────────

    void_to_void_type = b'\x60\x00\x00'  # func type: () -> ()
    new_data_segment_count = 2
    python_data_segment_idx = existing_data_count
    meta_data_segment_idx = existing_data_count + 1
    new_func_count = len(methods)

    # Map placeholder export func indices to code section body indices.
    # The linker (wasm-ld) may wrap exported C functions with a prologue/epilogue
    # pattern: call <prologue>; call <real_body>; call <epilogue>; end
    # In that case, we need to patch the INNER function (the 2nd call target),
    # not the wrapper itself.
    placeholder_code_indices = {}
    for name, func_idx in placeholder_funcs.items():
        wrapper_code_idx = func_idx - existing_import_func_count
        inner_code_idx = _resolve_wrapper_inner_func(
            wasm, code_section, wrapper_code_idx, existing_import_func_count
        )
        placeholder_code_indices[name] = inner_code_idx

    # ─── Step 3: Build replacement function bodies ───────────────────────

    def build_size_func_body(size: int) -> bytes:
        """Build function body for: () -> i32 { return <size>; }"""
        body = bytearray()
        body.extend(b'\x00')          # 0 local declarations
        body.extend(b'\x41')          # i32.const
        body.extend(encode_signed_leb128(size))
        body.extend(b'\x0b')          # end
        return bytes(body)

    def build_init_func_body(segment_idx: int, size: int) -> bytes:
        """Build function body for: (dest: i32) { memory.init seg dest 0 size; data.drop seg; }"""
        body = bytearray()
        body.extend(b'\x00')          # 0 local declarations
        body.extend(b'\x20\x00')      # local.get 0 (dest pointer)
        body.extend(b'\x41\x00')      # i32.const 0 (source offset in segment)
        body.extend(b'\x41')          # i32.const
        body.extend(encode_signed_leb128(size))  # size to copy
        body.extend(b'\xfc')          # prefix byte
        body.extend(encode_unsigned_leb128(8))   # memory.init opcode
        body.extend(encode_unsigned_leb128(segment_idx))  # data segment index
        body.extend(b'\x00')          # memory index (always 0)
        body.extend(b'\xfc')          # prefix byte
        body.extend(encode_unsigned_leb128(9))   # data.drop opcode
        body.extend(encode_unsigned_leb128(segment_idx))  # data segment index
        body.extend(b'\x0b')          # end
        return bytes(body)

    replacement_bodies = {
        placeholder_code_indices["python_source_passive_data_size"]:
            build_size_func_body(len(python_bytes)),
        placeholder_code_indices["method_meta_passive_data_size"]:
            build_size_func_body(len(method_meta_bytes)),
        placeholder_code_indices["init_python_source_passive_data"]:
            build_init_func_body(python_data_segment_idx, len(python_bytes)),
        placeholder_code_indices["init_method_meta_passive_data"]:
            build_init_func_body(meta_data_segment_idx, len(method_meta_bytes)),
    }

    # ─── Step 4: Rebuild wasm binary ─────────────────────────────────────
    # Section order: type(1), import(2), func(3), table(4), memory(5),
    # global(6), export(7), start(8), element(9), datacount(12), code(10), data(11)
    # The datacount section is REQUIRED for memory.init/data.drop (bulk memory).
    # If the original wasm doesn't have one, we must inject it before the code section.

    total_data_count = existing_data_count + new_data_segment_count
    has_datacount = datacount_section is not None
    datacount_injected = False

    output = bytearray()
    output.extend(b'\x00asm')
    output.extend(struct.pack('<I', 1))

    for section in sections:
        section_content = wasm[section.content_offset:section.content_offset + section.size]

        if section.section_id == SECTION_TYPE:
            new_count = existing_type_count + 1
            _, first_entry_offset = decode_unsigned_leb128(wasm, section.content_offset)
            rest = wasm[first_entry_offset:section.content_offset + section.size]
            new_content = encode_unsigned_leb128(new_count) + rest + void_to_void_type
            write_section(output, SECTION_TYPE, new_content)

        elif section.section_id == SECTION_FUNCTION:
            new_count = existing_func_count + new_func_count
            _, first_entry_offset = decode_unsigned_leb128(wasm, section.content_offset)
            rest = wasm[first_entry_offset:section.content_offset + section.size]
            new_type_idx = existing_type_count
            new_entries = b''.join(
                encode_unsigned_leb128(new_type_idx) for _ in range(new_func_count)
            )
            new_content = encode_unsigned_leb128(new_count) + rest + new_entries
            write_section(output, SECTION_FUNCTION, new_content)

        elif section.section_id == SECTION_EXPORT:
            export_count = len(exports)
            new_export_count = export_count + len(methods)
            _, first_entry_offset = decode_unsigned_leb128(wasm, section.content_offset)
            rest = wasm[first_entry_offset:section.content_offset + section.size]
            new_entries = bytearray()
            for i, method in enumerate(methods):
                func_idx = total_existing_funcs + i
                export_name = f"canister_{method['method_type']} {method['name']}"
                new_entries.extend(encode_name(export_name))
                new_entries.extend(b'\x00')  # kind = function
                new_entries.extend(encode_unsigned_leb128(func_idx))
            new_content = encode_unsigned_leb128(new_export_count) + rest + bytes(new_entries)
            write_section(output, SECTION_EXPORT, new_content)

        elif section.section_id == SECTION_DATACOUNT:
            # Update existing datacount section
            write_section(output, SECTION_DATACOUNT, encode_unsigned_leb128(total_data_count))
            datacount_injected = True

        elif section.section_id == SECTION_CODE:
            # If no datacount section existed, inject one now (before code section)
            if not datacount_injected:
                write_section(output, SECTION_DATACOUNT, encode_unsigned_leb128(total_data_count))
                datacount_injected = True

            new_content = rebuild_code_section(
                wasm, section,
                existing_func_count, new_func_count,
                replacement_bodies,
                methods, query_dispatcher_idx, update_dispatcher_idx,
            )
            write_section(output, SECTION_CODE, new_content)

        elif section.section_id == SECTION_DATA:
            _, first_entry_offset = decode_unsigned_leb128(wasm, section.content_offset)
            rest = wasm[first_entry_offset:section.content_offset + section.size]

            new_data_entries = bytearray()
            # Passive data segment for Python source (flag=1 = passive)
            new_data_entries.extend(b'\x01')
            new_data_entries.extend(encode_unsigned_leb128(len(python_bytes)))
            new_data_entries.extend(python_bytes)
            # Passive data segment for method metadata
            new_data_entries.extend(b'\x01')
            new_data_entries.extend(encode_unsigned_leb128(len(method_meta_bytes)))
            new_data_entries.extend(method_meta_bytes)

            new_content = encode_unsigned_leb128(total_data_count) + rest + bytes(new_data_entries)
            write_section(output, SECTION_DATA, new_content)

        else:
            write_section(output, section.section_id, section_content)

    return bytes(output)


def count_import_functions(wasm: bytes, import_section: Optional[WasmSection]) -> int:
    """Count the number of function imports in the import section."""
    if import_section is None:
        return 0

    count = 0
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
            count += 1
        elif kind == 1:  # table
            offset += 1  # elemtype
            flags, offset = decode_unsigned_leb128(wasm, offset)
            _, offset = decode_unsigned_leb128(wasm, offset)  # min
            if flags & 1:
                _, offset = decode_unsigned_leb128(wasm, offset)  # max
        elif kind == 2:  # memory
            flags, offset = decode_unsigned_leb128(wasm, offset)
            _, offset = decode_unsigned_leb128(wasm, offset)  # min
            if flags & 1:
                _, offset = decode_unsigned_leb128(wasm, offset)  # max
        elif kind == 3:  # global
            offset += 1  # valtype
            offset += 1  # mutability
            while wasm[offset] != 0x0B:
                offset += 1
            offset += 1  # skip end byte

    return count


def rebuild_code_section(
    wasm: bytes,
    code_section: WasmSection,
    existing_func_count: int,
    new_func_count: int,
    replacement_bodies: Dict[int, bytes],
    methods: List[Dict],
    query_dispatcher_idx: int,
    update_dispatcher_idx: int,
) -> bytes:
    """
    Rebuild the code section with patched placeholder functions and new method stubs.

    Parses each existing function body individually. For functions whose code-section
    index is in replacement_bodies, substitutes the new body. Then appends the new
    method stub function bodies.
    """
    offset = code_section.content_offset
    func_count, offset = decode_unsigned_leb128(wasm, offset)
    assert func_count == existing_func_count

    # Parse and optionally replace each existing function body
    rebuilt_bodies = bytearray()
    for i in range(existing_func_count):
        body_size, offset = decode_unsigned_leb128(wasm, offset)
        body_start = offset
        offset += body_size

        if i in replacement_bodies:
            # Replace this function body
            new_body = replacement_bodies[i]
            rebuilt_bodies.extend(encode_unsigned_leb128(len(new_body)))
            rebuilt_bodies.extend(new_body)
        else:
            # Copy original function body as-is
            original_body = wasm[body_start:body_start + body_size]
            rebuilt_bodies.extend(encode_unsigned_leb128(body_size))
            rebuilt_bodies.extend(original_body)

    # Append new method stub function bodies
    for i, method in enumerate(methods):
        if method["method_type"] == "query":
            dispatcher_idx = query_dispatcher_idx
        else:
            dispatcher_idx = update_dispatcher_idx

        body = bytearray()
        body.extend(b'\x00')      # 0 local declarations
        body.extend(b'\x41')      # i32.const
        body.extend(encode_signed_leb128(i))
        body.extend(b'\x10')      # call
        body.extend(encode_unsigned_leb128(dispatcher_idx))
        body.extend(b'\x0b')      # end

        rebuilt_bodies.extend(encode_unsigned_leb128(len(body)))
        rebuilt_bodies.extend(body)

    new_count = existing_func_count + new_func_count
    return encode_unsigned_leb128(new_count) + bytes(rebuilt_bodies)


def write_section(output: bytearray, section_id: int, content: bytes) -> None:
    """Write a wasm section to the output buffer."""
    output.append(section_id)
    output.extend(encode_unsigned_leb128(len(content)))
    output.extend(content)


# ─── Python source extraction ───────────────────────────────────────────────

# Map Python type annotations to Candid types
_PRIMITIVE_TYPE_MAP = {
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
    "null": "null",
    "void": "null",
    "empty": "empty",
    "reserved": "reserved",
}

# Candid reserved words — field names matching these must be quoted
_CANDID_RESERVED = {
    "bool", "nat", "nat8", "nat16", "nat32", "nat64",
    "int", "int8", "int16", "int32", "int64",
    "float32", "float64", "text", "null", "reserved", "empty",
    "blob", "principal", "opt", "vec", "record", "variant",
    "func", "service", "oneway", "query", "composite_query",
    "type", "import",
}


def _quote_field(name: str) -> str:
    """Quote a record/variant field name if it is a Candid reserved word."""
    return f'"{name}"' if name in _CANDID_RESERVED else name


def _build_type_registry(tree) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Walk the AST to find Record, Variant, and Tuple type definitions.
    Returns a tuple of:
      - type_names: dict mapping class/alias name -> Candid type name (same name, used for references)
      - type_defs:  dict mapping class/alias name -> Candid type definition string
                    e.g. "record { name : text; age : nat32 }"

    Handles:
      - class Foo(Record): name: str; age: nat32
      - class Bar(Variant, total=False): A: null; B: text
      - MyTuple = Tuple[str, nat64]
    """
    import ast

    # type_defs maps name -> full Candid type definition
    type_defs: Dict[str, str] = {}
    # Track which names are user-defined types (for reference resolution)
    known_types: set = set()
    # Track resolution in progress (to detect cycles)
    resolving: set = set()

    # Pass 1: collect raw class/alias definitions
    raw_records: Dict[str, list] = {}     # name -> [(field_name, annotation_node), ...]
    raw_variants: Dict[str, list] = {}    # name -> [(case_name, annotation_node), ...]
    raw_tuples: Dict[str, list] = {}      # name -> [annotation_node, ...]
    raw_funcs: Dict[str, tuple] = {}      # name -> (mode, param_nodes, return_node)
    raw_services: Dict[str, list] = {}    # name -> [(method_name, mode, param_nodes, return_node), ...]
    raw_aliases: Dict[str, object] = {}   # name -> annotation_node (for Alias[X])

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            base_names = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    base_names.append(base.id)
                elif isinstance(base, ast.Attribute):
                    base_names.append(base.attr)

            if "Record" in base_names:
                fields = []
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        fields.append((item.target.id, item.annotation))
                raw_records[node.name] = fields
                known_types.add(node.name)
            elif "Variant" in base_names:
                cases = []
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        cases.append((item.target.id, item.annotation))
                raw_variants[node.name] = cases
                known_types.add(node.name)
            elif "Service" in base_names:
                # Service class: extract @service_query / @service_update methods
                svc_methods = []
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        svc_mode = None
                        for dec in item.decorator_list:
                            dec_id = None
                            if isinstance(dec, ast.Name):
                                dec_id = dec.id
                            elif isinstance(dec, ast.Attribute):
                                dec_id = dec.attr
                            if dec_id == "service_query":
                                svc_mode = "query"
                            elif dec_id == "service_update":
                                svc_mode = "update"
                        if svc_mode:
                            # Extract params (skip self)
                            param_anns = []
                            for arg in item.args.args:
                                if arg.arg == "self":
                                    continue
                                param_anns.append(arg.annotation)
                            svc_methods.append((item.name, svc_mode, param_anns, item.returns))
                if svc_methods:
                    raw_services[node.name] = svc_methods
                    known_types.add(node.name)

        elif isinstance(node, ast.Assign):
            # Tuple alias: MyTuple = Tuple[str, nat64]
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                alias_name = node.targets[0].id
                value = node.value
                if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name):
                    if value.value.id == "Tuple":
                        elements = _extract_subscript_elements(value.slice)
                        raw_tuples[alias_name] = elements
                        known_types.add(alias_name)
                    # Alias type: SuperheroId = Alias[nat32]
                    if value.value.id == "Alias":
                        raw_tuples.pop(alias_name, None)  # not a tuple
                        raw_aliases[alias_name] = value.slice
                        known_types.add(alias_name)
                # Func type: BasicFunc = Func(Query[[str], str])
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                    if value.func.id == "Func" and len(value.args) == 1:
                        func_arg = value.args[0]
                        # func_arg should be Query[[params], ret] or Update[[params], ret]
                        if isinstance(func_arg, ast.Subscript) and isinstance(func_arg.value, ast.Name):
                            mode = "query" if func_arg.value.id == "Query" else "update" if func_arg.value.id == "Update" else None
                            if mode and isinstance(func_arg.slice, ast.Tuple) and len(func_arg.slice.elts) == 2:
                                params_node = func_arg.slice.elts[0]  # should be a List
                                ret_node = func_arg.slice.elts[1]
                                param_anns = []
                                if isinstance(params_node, ast.List):
                                    param_anns = params_node.elts
                                raw_funcs[alias_name] = (mode, param_anns, ret_node)
                                known_types.add(alias_name)

        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            # TypeAlias annotated form: BoolAlias: TypeAlias = Alias[bool]
            alias_name = node.target.id
            value = node.value
            if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name):
                if value.value.id == "Tuple":
                    elements = _extract_subscript_elements(value.slice)
                    raw_tuples[alias_name] = elements
                    known_types.add(alias_name)
                if value.value.id == "Alias":
                    raw_tuples.pop(alias_name, None)
                    raw_aliases[alias_name] = value.slice
                    known_types.add(alias_name)
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                if value.func.id == "Func" and len(value.args) == 1:
                    func_arg = value.args[0]
                    if isinstance(func_arg, ast.Subscript) and isinstance(func_arg.value, ast.Name):
                        mode = "query" if func_arg.value.id == "Query" else "update" if func_arg.value.id == "Update" else None
                        if mode and isinstance(func_arg.slice, ast.Tuple) and len(func_arg.slice.elts) == 2:
                            params_node = func_arg.slice.elts[0]
                            ret_node = func_arg.slice.elts[1]
                            param_anns = []
                            if isinstance(params_node, ast.List):
                                param_anns = params_node.elts
                            raw_funcs[alias_name] = (mode, param_anns, ret_node)
                            known_types.add(alias_name)

    # Pass 2: resolve all types into Candid definitions
    def resolve_annotation(annotation) -> str:
        """Convert a Python type annotation AST node to a Candid type string."""
        if annotation is None:
            return "null"
        if isinstance(annotation, ast.Constant):
            if annotation.value is None:
                return "null"
            if isinstance(annotation.value, str):
                # Forward reference as string: "User"
                return resolve_name(annotation.value)
            return "null"
        if isinstance(annotation, ast.Name):
            return resolve_name(annotation.id)
        if isinstance(annotation, ast.Attribute):
            name = annotation.attr
            if name in _PRIMITIVE_TYPE_MAP:
                return _PRIMITIVE_TYPE_MAP[name]
            return resolve_name(name)
        if isinstance(annotation, ast.Subscript):
            if isinstance(annotation.value, ast.Name):
                outer = annotation.value.id
                if outer in ("list", "Vec"):
                    inner = resolve_annotation(annotation.slice)
                    return f"vec {inner}"
                if outer in ("Optional", "Opt"):
                    inner = resolve_annotation(annotation.slice)
                    return f"opt {inner}"
                if outer == "Manual":
                    return resolve_annotation(annotation.slice)
                if outer == "Async":
                    return resolve_annotation(annotation.slice)
                if outer == "Tuple":
                    elements = _extract_subscript_elements(annotation.slice)
                    field_strs = []
                    for i, elem in enumerate(elements):
                        ct = resolve_annotation(elem)
                        field_strs.append(f"{i} : {ct}")
                    return "record { " + "; ".join(field_strs) + " }"
        return "text"  # fallback

    def resolve_name(name: str) -> str:
        """Resolve a type name to a Candid type string.
        For user-defined types, returns the type name itself (will be a named type in .did).
        """
        if name in _PRIMITIVE_TYPE_MAP:
            return _PRIMITIVE_TYPE_MAP[name]
        if name in known_types:
            # Ensure the type definition is resolved
            ensure_type_resolved(name)
            return name  # Reference by name
        return "text"  # unknown type fallback

    def ensure_type_resolved(name: str):
        """Resolve a user-defined type and store its definition."""
        if name in type_defs:
            return
        if name in resolving:
            return  # Cycle detected — already being resolved, will use name reference
        resolving.add(name)

        if name in raw_records:
            fields = raw_records[name]
            field_strs = []
            for field_name, ann in fields:
                ct = resolve_annotation(ann)
                field_strs.append(f"{_quote_field(field_name)} : {ct}")
            type_defs[name] = "record { " + "; ".join(field_strs) + " }"
        elif name in raw_variants:
            cases = raw_variants[name]
            case_strs = []
            for case_name, ann in cases:
                ct = resolve_annotation(ann)
                case_strs.append(f"{_quote_field(case_name)} : {ct}")
            type_defs[name] = "variant { " + "; ".join(case_strs) + " }"
        elif name in raw_tuples:
            elements = raw_tuples[name]
            field_strs = []
            for i, elem in enumerate(elements):
                ct = resolve_annotation(elem)
                field_strs.append(f"{i} : {ct}")
            type_defs[name] = "record { " + "; ".join(field_strs) + " }"
        elif name in raw_funcs:
            mode, param_anns, ret_node = raw_funcs[name]
            param_strs = [resolve_annotation(p) for p in param_anns]
            ret_str = resolve_annotation(ret_node)
            mode_suffix = " query" if mode == "query" else ""
            ret_part = f" ({ret_str})" if ret_str not in ("null", "") else " ()"
            type_defs[name] = f"func ({', '.join(param_strs)}) ->{ret_part}{mode_suffix}"
        elif name in raw_services:
            svc_methods = raw_services[name]
            method_strs = []
            for mname, mmode, mparam_anns, mret in svc_methods:
                mparams = ", ".join(resolve_annotation(p) for p in mparam_anns)
                mret_str = resolve_annotation(mret)
                mret_part = f" ({mret_str})" if mret_str not in ("null", "") else " ()"
                mmode_suffix = " query" if mmode == "query" else ""
                method_strs.append(f"{mname} : ({mparams}) ->{mret_part}{mmode_suffix}")
            type_defs[name] = "service { " + "; ".join(method_strs) + " }"
        elif name in raw_aliases:
            # Alias[X] — resolve the inner type
            type_defs[name] = resolve_annotation(raw_aliases[name])

        resolving.discard(name)

    # Resolve all types
    for name in list(raw_records.keys()) + list(raw_variants.keys()) + list(raw_tuples.keys()) + list(raw_funcs.keys()) + list(raw_services.keys()) + list(raw_aliases.keys()):
        ensure_type_resolved(name)

    return dict.fromkeys(known_types, ""), type_defs


def _extract_subscript_elements(slice_node) -> list:
    """Extract elements from a Subscript slice (handles Tuple[a, b, c])."""
    import ast
    if isinstance(slice_node, ast.Tuple):
        return list(slice_node.elts)
    # Single element: Tuple[str]
    return [slice_node]


def extract_methods_from_python(python_source: str) -> List[Dict]:
    """
    Extract method declarations from Python source code.

    Looks for @query and @update decorators and extracts function signatures.
    Parses Record, Variant, and Tuple class definitions to resolve complex types.
    Returns a list of method metadata dicts.

    Example:
        class User(Record):
            name: str
            age: nat32

        @query
        def get_user() -> User:
            return {"name": "Alice", "age": 30}

    Produces:
        [{"name": "get_user", "method_type": "query",
          "params": [],
          "returns": "record { name : text; age : nat32 }"}]
    """
    import ast

    tree = ast.parse(python_source)
    methods = []
    lifecycle = {}

    # Build type registry from class definitions
    known_types, type_defs = _build_type_registry(tree)

    # Inject basilisk built-in types that users import but don't redefine
    _BUILTIN_BASILISK_TYPES = {
        "StableMemoryError": "variant { OutOfMemory : null; OutOfBounds : null }",
        "StableGrowResult": "variant { Ok : nat32; Err : variant { OutOfMemory : null; OutOfBounds : null } }",
        "Stable64GrowResult": "variant { Ok : nat64; Err : variant { OutOfMemory : null; OutOfBounds : null } }",
        "RejectionCode": "variant { NoError : null; SysFatal : null; SysTransient : null; DestinationInvalid : null; CanisterReject : null; CanisterError : null }",
        "NotifyResult": "variant { Ok : null; Err : variant { NoError : null; SysFatal : null; SysTransient : null; DestinationInvalid : null; CanisterReject : null; CanisterError : null } }",
        "GuardResult": "variant { Ok : null; Err : text }",
        "KeyTooLarge": "record { given : nat32; max : nat32 }",
        "ValueTooLarge": "record { given : nat32; max : nat32 }",
        "InsertError": "variant { KeyTooLarge : record { given : nat32; max : nat32 }; ValueTooLarge : record { given : nat32; max : nat32 } }",
    }
    for name, definition in _BUILTIN_BASILISK_TYPES.items():
        if name not in type_defs:
            type_defs[name] = definition
            known_types[name] = ""

    def get_candid_type(annotation) -> str:
        """Convert a Python type annotation to a Candid type string."""
        if annotation is None:
            return "null"
        if isinstance(annotation, ast.Constant):
            if annotation.value is None:
                return "null"
            if isinstance(annotation.value, str):
                # Forward reference as string: "User"
                name = annotation.value
                if name in _PRIMITIVE_TYPE_MAP:
                    return _PRIMITIVE_TYPE_MAP[name]
                if name in known_types:
                    return name
                return "text"
            return "null"
        if isinstance(annotation, ast.Name):
            name = annotation.id
            if name in _PRIMITIVE_TYPE_MAP:
                return _PRIMITIVE_TYPE_MAP[name]
            if name in known_types:
                return name
            return "text"
        if isinstance(annotation, ast.Attribute):
            return _PRIMITIVE_TYPE_MAP.get(annotation.attr, "text")
        if isinstance(annotation, ast.Subscript):
            if isinstance(annotation.value, ast.Name):
                outer = annotation.value.id
                if outer in ("list", "Vec"):
                    inner = get_candid_type(annotation.slice)
                    return f"vec {inner}"
                if outer in ("Optional", "Opt"):
                    inner = get_candid_type(annotation.slice)
                    return f"opt {inner}"
                if outer == "Manual":
                    return get_candid_type(annotation.slice)
                if outer == "Async":
                    return get_candid_type(annotation.slice)
                if outer == "Alias":
                    return get_candid_type(annotation.slice)
                if outer == "CallResult":
                    inner = get_candid_type(annotation.slice)
                    return f"variant {{ Ok : {inner}; Err : text }}"
                if outer == "Tuple":
                    elements = _extract_subscript_elements(annotation.slice)
                    field_strs = []
                    for i, elem in enumerate(elements):
                        ct = get_candid_type(elem)
                        field_strs.append(f"{i} : {ct}")
                    return "record { " + "; ".join(field_strs) + " }"
        return "text"  # fallback

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        method_type = None
        guard_name = None
        for decorator in node.decorator_list:
            dec_name = None
            dec_kwargs = {}
            if isinstance(decorator, ast.Name):
                dec_name = decorator.id
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    dec_name = decorator.func.id
                elif isinstance(decorator.func, ast.Attribute):
                    dec_name = decorator.func.attr
                # Extract keyword arguments (e.g. guard=my_guard)
                for kw in decorator.keywords:
                    if kw.arg == "guard" and isinstance(kw.value, ast.Name):
                        dec_kwargs["guard"] = kw.value.id
            elif isinstance(decorator, ast.Attribute):
                dec_name = decorator.attr

            if dec_name in ("query", "update", "init", "pre_upgrade",
                            "post_upgrade", "heartbeat", "inspect_message",
                            "composite_query"):
                method_type = dec_name
                if dec_name == "composite_query":
                    method_type = "query"  # composite_query is a query variant
                if "guard" in dec_kwargs:
                    guard_name = dec_kwargs["guard"]

        if method_type is None:
            continue

        params = []
        for arg in node.args.args:
            param_name = arg.arg
            if param_name == "self":
                continue
            candid_type = get_candid_type(arg.annotation)
            params.append({"name": param_name, "candid_type": candid_type})

        # Check for Manual[T], Async[T] return types, and yield in body
        manual_reply = False
        is_async = False
        ret_annotation = node.returns
        # Unwrap Async[T] -> T (or Async[Manual[T]] -> Manual[T])
        if isinstance(ret_annotation, ast.Subscript):
            if isinstance(ret_annotation.value, ast.Name) and ret_annotation.value.id == "Async":
                is_async = True
                ret_annotation = ret_annotation.slice
        # Also detect yield in function body (generator without Async annotation)
        if not is_async:
            for child in ast.walk(node):
                if isinstance(child, (ast.Yield, ast.YieldFrom)):
                    is_async = True
                    break
        # Check for Manual[T]
        if isinstance(ret_annotation, ast.Subscript):
            if isinstance(ret_annotation.value, ast.Name) and ret_annotation.value.id == "Manual":
                manual_reply = True

        return_type = get_candid_type(ret_annotation)

        entry = {
            "name": node.name,
            "method_type": method_type,
            "params": params,
            "returns": return_type,
        }
        if guard_name:
            entry["guard"] = guard_name
        if manual_reply:
            entry["manual_reply"] = True
        if is_async:
            entry["is_async"] = True

        if method_type in ("query", "update"):
            methods.append(entry)
        else:
            lifecycle[method_type] = entry

    # Store type_defs in the return for .did generation
    return methods, type_defs, lifecycle


def generate_candid_from_methods(
    methods: List[Dict],
    type_defs: Optional[Dict[str, str]] = None,
    lifecycle: Optional[Dict[str, Dict]] = None,
) -> str:
    """Generate a .did file from method metadata.

    Handles complex types like record { ... }, variant { ... } with named type definitions.
    If an @init hook with parameters is present, emits init args in the service declaration.
    """
    parts = []

    # Emit named type definitions
    if type_defs:
        for name, definition in type_defs.items():
            parts.append(f"type {name} = {definition};")
        if type_defs:
            parts.append("")

    # Build init args string if @init has parameters
    init_args = ""
    if lifecycle and "init" in lifecycle:
        init_info = lifecycle["init"]
        if init_info.get("params"):
            init_params = ", ".join(
                p["candid_type"] for p in init_info["params"]
            )
            init_args = f"({init_params})"

    # Emit service definition
    svc_lines = []
    for method in methods:
        params = ", ".join(
            p["candid_type"] for p in method["params"]
        )
        returns = method["returns"] if method["returns"] not in ("null", "") else ""
        mode = " query" if method["method_type"] == "query" else ""
        svc_lines.append(f'  "{method["name"]}" : ({params}) -> ({returns}){mode};')

    if init_args:
        parts.append(f"service : {init_args} -> {{")
    else:
        parts.append("service : {")
    parts.extend(svc_lines)
    parts.append("}")

    return "\n".join(parts) + "\n"


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
        type_defs = {}
        lifecycle = {}
    else:
        methods, type_defs, lifecycle = extract_methods_from_python(python_source)

    print(f"Extracted {len(methods)} canister methods:")
    for m in methods:
        print(f"  @{m['method_type']} {m['name']}({', '.join(p['name'] + ': ' + p['candid_type'] for p in m['params'])}) -> {m['returns']}")

    manipulate_wasm(template_path, output_path, python_source, methods, type_defs, lifecycle)
