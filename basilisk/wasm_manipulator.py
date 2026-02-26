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
