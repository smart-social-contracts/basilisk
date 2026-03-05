import os
import shutil
import subprocess
import sys

import basilisk
from basilisk.colors import red
from basilisk.timed import timed_inline
from basilisk.types import Paths


@timed_inline
def build_wasm_binary_or_exit(
    paths: Paths, canister_name: str, cargo_env: dict[str, str], verbose: bool = False
):
    python_backend = os.environ.get("BASILISK_PYTHON_BACKEND", "cpython")

    if python_backend == "cpython":
        build_with_template(paths, canister_name, cargo_env, verbose)
        return

    compile_or_download_rust_python_stdlib(paths, cargo_env, verbose)
    compile_generated_rust_code(paths, canister_name, cargo_env, verbose)
    copy_wasm_to_dev_location(paths, canister_name)
    run_wasi2ic_on_wasm(paths, canister_name, cargo_env, verbose)
    generate_and_create_candid_file(paths, canister_name, cargo_env, verbose)


def _get_frozen_stdlib_preamble() -> str:
    """Return pure-Python stdlib modules to prepend to user source for CPython template mode.

    On WASI there is no filesystem, so stdlib packages like `json` aren't importable.
    Reads the preamble from frozen_stdlib_preamble.py next to this file.
    """
    preamble_path = os.path.join(os.path.dirname(__file__), "frozen_stdlib_preamble.py")
    with open(preamble_path, "r") as f:
        return f.read() + "\n"


def build_with_template(
    paths: Paths, canister_name: str, cargo_env: dict[str, str], verbose: bool
):
    """Build canister using pre-compiled template wasm (azle-style pattern).

    Instead of generating Rust code and running cargo build (~5-10 min),
    this takes the pre-compiled template wasm and injects the Python source
    + method metadata as passive data segments (~seconds).
    """
    from basilisk.wasm_manipulator import (
        manipulate_wasm,
        extract_methods_from_python,
        generate_candid_from_methods,
    )

    # 1. Locate the pre-built template wasm
    template_wasm_path = find_template_wasm(paths)
    if template_wasm_path is None:
        print(red("Template wasm not found. Building from source..."))
        template_wasm_path = build_template_from_source(paths, cargo_env, verbose)

    # 2. Read the user's Python source
    python_source = read_python_source(paths)

    # Note: frozen stdlib preamble (json, etc.) is now embedded in the Rust template
    # and runs before the basilisk shim during canister_init. No need to prepend here.

    # 3. Extract method metadata from the Python source
    # For multi-file projects, the bundled python_source wraps imported modules
    # as lazy-loaded string literals, so we need to extract methods from the raw
    # individual .py files instead. Walk the ORIGINAL user source directory
    # (derived from py_entry_file) to avoid picking up basilisk internal modules
    # that are copied into the python_source bundle directory.
    py_entry_file = paths.get("py_entry_file", "")
    user_src_dir = ""
    if py_entry_file:
        # Find the top-level 'src/' directory from the entry file path
        # e.g. "src/main.py" -> "src/", "src/canister1/index.py" -> "src/"
        entry_parts = os.path.normpath(py_entry_file).split(os.sep)
        if "src" in entry_parts:
            src_idx = entry_parts.index("src")
            user_src_dir = os.sep.join(entry_parts[: src_idx + 1])
    if user_src_dir and os.path.isdir(user_src_dir):
        raw_sources = []
        for root, _dirs, files in os.walk(user_src_dir):
            for fname in sorted(files):
                if fname.endswith(".py"):
                    with open(os.path.join(root, fname), "r") as f:
                        raw_sources.append(f.read())
        combined_raw = "\n".join(raw_sources)
        methods, type_defs, lifecycle = extract_methods_from_python(combined_raw)
    else:
        methods, type_defs, lifecycle = extract_methods_from_python(python_source)
    if verbose:
        print(f"Extracted {len(methods)} canister methods from Python source")
        for m in methods:
            print(f"  @{m['method_type']} {m['name']}")
        if type_defs:
            print(f"  Type definitions: {len(type_defs)}")
            for name, defn in type_defs.items():
                print(f"    {name} = {defn}")
        if lifecycle:
            print(f"  Lifecycle hooks: {', '.join(lifecycle.keys())}")

    # 4. Inject Python source + method metadata into template wasm
    output_wasm = f"{paths['canister']}/{canister_name}.wasm"
    os.makedirs(os.path.dirname(output_wasm), exist_ok=True)
    manipulate_wasm(template_wasm_path, output_wasm, python_source, methods, type_defs, lifecycle)

    # 5. Skip wasi2ic and wasm-opt: the downloaded template is already post-processed.
    # Running wasm-opt again would strip the passive data segments we just injected.
    # Running wasi2ic again on an already-converted binary would corrupt it.

    # 6. Generate .did file from method metadata
    candid_content = generate_candid_from_methods(methods, type_defs, lifecycle)
    create_file(paths["did"], candid_content)
    if verbose:
        print(f"Generated Candid file: {paths['did']}")
        print(candid_content)


def find_template_wasm(paths: Paths) -> str | None:
    """Locate the pre-built CPython canister template wasm.

    Searches in order:
    1. BASILISK_TEMPLATE_WASM env var (explicit path)
    2. ~/.config/basilisk/<version>/cpython_canister_template.wasm (downloaded artifact)
    3. <compiler_dir>/cpython_canister_template/target/wasm32-wasip1/release/cpython_canister_template.wasm (local build)
    """
    # 1. Explicit path
    explicit = os.environ.get("BASILISK_TEMPLATE_WASM")
    if explicit and os.path.exists(explicit):
        return explicit

    # 2. Downloaded artifact
    artifact_path = f"{paths['global_basilisk_version_dir']}/cpython_canister_template.wasm"
    if os.path.exists(artifact_path):
        return artifact_path

    # 3. Local build
    compiler_dir = os.path.dirname(basilisk.__file__) + "/compiler"
    local_path = f"{compiler_dir}/cpython_canister_template/target/wasm32-wasip1/release/cpython_canister_template.wasm"
    if os.path.exists(local_path):
        return local_path

    return None


def build_template_from_source(
    paths: Paths, cargo_env: dict[str, str], verbose: bool
) -> str:
    """Build the CPython canister template WASM from source and cache it.

    This is the fallback when no pre-built template is found. It compiles the
    template from its own Cargo.toml, runs wasi2ic, and caches the result at
    ~/.config/basilisk/<version>/cpython_canister_template.wasm.

    wasi2ic is needed to convert WASI entry points to IC canister format.
    wasm-opt is NOT run here as it can corrupt the binary.
    """
    compiler_dir = os.path.dirname(basilisk.__file__) + "/compiler"
    template_cargo_toml = f"{compiler_dir}/cpython_canister_template/Cargo.toml"

    if not os.path.exists(template_cargo_toml):
        print(red(f"Template Cargo.toml not found at {template_cargo_toml}"))
        sys.exit(1)

    # 1. Install CPython WASM (needed by basilisk_cpython's build.rs)
    install_cpython_wasm(paths, cargo_env, verbose)
    cpython_wasm_dir = f"{paths['global_basilisk_version_dir']}/cpython_wasm"
    cargo_env["CPYTHON_WASM_DIR"] = cpython_wasm_dir
    os.environ["CPYTHON_WASM_DIR"] = cpython_wasm_dir

    # 2. Build the template
    print("Building CPython canister template from source (this may take several minutes)...")
    run_subprocess(
        [
            f"{paths['global_basilisk_rust_bin_dir']}/cargo",
            "build",
            f"--manifest-path={template_cargo_toml}",
            "--target=wasm32-wasip1",
            "--package=cpython_canister_template",
            "--release",
        ],
        cargo_env,
        verbose,
    )

    # 3. Post-process: copy raw wasm and run wasi2ic
    # wasi2ic converts WASI entry points (_start, etc.) to IC canister format.
    # Do NOT run wasm-opt — it corrupts the binary for IC deployment.
    raw_wasm = f"{paths['global_basilisk_target_dir']}/wasm32-wasip1/release/cpython_canister_template.wasm"
    cached_path = f"{paths['global_basilisk_version_dir']}/cpython_canister_template.wasm"
    os.makedirs(os.path.dirname(cached_path), exist_ok=True)
    shutil.copy(raw_wasm, cached_path)

    # wasi2ic
    run_subprocess(
        [
            f"{paths['global_basilisk_rust_bin_dir']}/wasi2ic",
            cached_path,
            cached_path,
        ],
        cargo_env,
        verbose,
    )

    print(f"Template WASM built and cached at {cached_path}")
    return cached_path


def read_python_source(paths: Paths) -> str:
    """Read all bundled Python source files into a single string.

    For the CPython template mode, ALL bundled modules must be included in a single
    string since there's no filesystem. This function:
    1. Walks the bundled python_source directory
    2. Collects all .py files with their module paths
    3. Generates a custom import hook that serves modules from an in-memory dict
    4. Appends the main entry point code at the end
    """
    python_source_dir = paths.get("python_source", "")
    entry_file = paths.get("py_entry_file", "")
    entry_module = paths.get("py_entry_module_name", "main")

    # If python_source dir exists (bundled by bundle_python_code), read ALL modules
    if python_source_dir and os.path.isdir(python_source_dir):
        main_py = os.path.join(python_source_dir, f"{entry_module}.py")
        if os.path.exists(main_py):
            return _bundle_all_modules(python_source_dir, entry_module)

    # Fall back to reading the original entry point file (no dependencies)
    if entry_file and os.path.exists(entry_file):
        with open(entry_file, "r") as f:
            return f.read()

    raise FileNotFoundError(
        f"Could not find Python source. Checked: {python_source_dir}, {entry_file}"
    )


def _bundle_all_modules(source_dir: str, entry_module: str) -> str:
    """Bundle all Python modules from source_dir into a single string.

    Directly populates sys.modules with pre-compiled module objects instead of
    using sys.meta_path (which requires _Py_InitializeMain, skipped in WASI CPython).
    Modules are loaded in dependency order: packages first, then submodules.
    """
    modules = {}  # module_name -> (source_code, is_package)

    for root, dirs, files in os.walk(source_dir):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            filepath = os.path.join(root, fname)
            relpath = os.path.relpath(filepath, source_dir)
            # Convert file path to module name
            parts = relpath.replace(os.sep, "/").split("/")
            is_package = parts[-1] == "__init__.py"
            if is_package:
                mod_name = ".".join(parts[:-1])
            else:
                parts[-1] = parts[-1][:-3]  # strip .py
                mod_name = ".".join(parts)

            if not mod_name:
                continue

            # Skip the entry module - it will be appended at the end
            if mod_name == entry_module:
                continue

            # Skip the basilisk package - provided by the Rust BASILISK_PYTHON_SHIM
            if mod_name == "basilisk" or mod_name.startswith("basilisk."):
                continue

            with open(filepath, "r") as f:
                modules[mod_name] = (f.read(), is_package)

    # Sort for registration: packages before submodules (so parent exists in sys.modules first)
    sorted_modules = sorted(modules.keys(), key=lambda m: (m.count('.'), not modules[m][1], m))

    # Build the loader preamble using lazy modules.
    # Modules are registered as _LazyMod instances in sys.modules.  Their source
    # is only exec'd on the first attribute access, avoiding import-time errors
    # from unavailable stdlib modules (time, datetime, etc. on WASI).
    lines = []
    lines.append("# ── Basilisk in-memory module loader ──")
    lines.append("import sys as _bsys")
    lines.append("_bMT = type(_bsys)  # ModuleType without importing types")

    # Define the lazy module class
    lines.append("""
class _LazyMod(_bMT):
    def __init__(self, name, source, is_pkg=False):
        super().__init__(name)
        self.__dict__['_bsrc'] = source
        self.__dict__['_bloaded'] = False
        self.__dict__['_bloading'] = False
        if is_pkg:
            self.__path__ = [name.replace('.', '/')]
            self.__package__ = name
        else:
            self.__package__ = name.rpartition('.')[0]
    def _bload(self):
        if self._bloading or self._bloaded:
            return
        self.__dict__['_bloading'] = True
        try:
            if self._bsrc:
                exec(compile(self._bsrc, self.__name__.replace('.', '/') + '.py', 'exec'), self.__dict__)
            self.__dict__['_bloaded'] = True
        except Exception as _be:
            import sys as _es
            _tb = _es.exc_info()[2]
            _frames = []
            while _tb:
                _f = _tb.tb_frame
                _frames.append(f'  File "{_f.f_code.co_filename}", line {_tb.tb_lineno}, in {_f.f_code.co_name}')
                _tb = _tb.tb_next
            raise type(_be)(f"{_be}\\nModule: {self.__name__}\\nTraceback:\\n" + "\\n".join(_frames)) from None
        finally:
            self.__dict__['_bloading'] = False
    def __getattr__(self, name):
        self._bload()
        try:
            return self.__dict__[name]
        except KeyError:
            # Check if name is a registered submodule in sys.modules
            _sub = self.__name__ + '.' + name
            if _sub in _bsys.modules:
                _mod = _bsys.modules[_sub]
                self.__dict__[name] = _mod
                return _mod
            raise AttributeError(f"module '{self.__name__}' has no attribute '{name}'")
""")

    # Register each module as a lazy module in sys.modules
    for mod_name in sorted_modules:
        source, is_package = modules[mod_name]
        lines.append(f"_bsys.modules[{mod_name!r}] = _LazyMod({mod_name!r}, {source!r}, {is_package!r})")

    # Read and append the entry module source at the end
    entry_path = os.path.join(source_dir, f"{entry_module}.py")
    with open(entry_path, "r") as f:
        entry_source = f.read()

    lines.append("# ── Entry point ──")
    lines.append(entry_source)

    return "\n".join(lines)


def install_cpython_wasm(paths: Paths, cargo_env: dict[str, str], verbose: bool):
    """Install CPython wasm32-wasip1 build if not already present."""
    install_script = os.path.join(
        os.path.dirname(basilisk.__file__),
        "compiler", "cpython", "install_cpython_wasm.sh",
    )
    run_subprocess(
        ["bash", install_script, paths["global_basilisk_version_dir"]],
        cargo_env,
        verbose,
    )


def copy_cpython_to_canister_staging(paths: Paths, cargo_env: dict[str, str]):
    """Copy CPython wasm artifacts and basilisk_cpython crate to canister staging dir."""
    cpython_wasm_dir = f"{paths['global_basilisk_version_dir']}/cpython_wasm"
    canister_cpython_dir = f"{paths['canister']}/basilisk_cpython"

    # Copy the basilisk_cpython crate source to the canister staging directory
    basilisk_cpython_src = os.path.join(
        os.path.dirname(basilisk.__file__),
        "compiler", "basilisk_cpython",
    )
    if os.path.exists(canister_cpython_dir):
        shutil.rmtree(canister_cpython_dir)
    shutil.copytree(basilisk_cpython_src, canister_cpython_dir)

    # Set CPYTHON_WASM_DIR so the build.rs in basilisk_cpython can find libpython
    os.environ["CPYTHON_WASM_DIR"] = cpython_wasm_dir
    cargo_env["CPYTHON_WASM_DIR"] = cpython_wasm_dir


def compile_or_download_rust_python_stdlib(
    paths: Paths, cargo_env: dict[str, str], verbose: bool
):
    if os.environ.get("BASILISK_COMPILE_RUST_PYTHON_STDLIB") == "true":
        compile_rust_python_stdlib(paths, cargo_env, verbose)
    else:
        rust_python_stdlib_global_path = (
            f"{paths['global_basilisk_version_dir']}/rust_python_stdlib"
        )
        download_rust_python_stdlib(
            rust_python_stdlib_global_path, paths, cargo_env, verbose
        )
        copy_rust_python_stdlib_global_to_staging(rust_python_stdlib_global_path, paths)


def compile_rust_python_stdlib(paths: Paths, cargo_env: dict[str, str], verbose: bool):
    rust_python_global_path = f"{paths['global_basilisk_version_dir']}/RustPython"

    if not os.path.exists(rust_python_global_path):
        clone_and_checkout_rust_python(paths, cargo_env, verbose)

    copy_rust_python_lib_global_to_staging(rust_python_global_path, paths)

    rust_python_stdlib_staging_path = f"{paths['canister']}/rust_python_stdlib"

    create_rust_python_stdlib_staging_directory(rust_python_stdlib_staging_path)
    compile_and_write_rust_python_stdlib_to_staging(
        rust_python_stdlib_staging_path, paths, cargo_env, verbose
    )


def clone_and_checkout_rust_python(
    paths: Paths, cargo_env: dict[str, str], verbose: bool
):
    run_subprocess(
        ["git", "clone", "https://github.com/RustPython/RustPython.git"],
        cargo_env,
        verbose,
        cwd=paths["global_basilisk_version_dir"],
    )

    run_subprocess(
        ["git", "checkout", "f12875027ce425297c07cbccb9be77514ed46157"],
        cargo_env,
        verbose,
        cwd=f"{paths['global_basilisk_version_dir']}/RustPython",
    )


def copy_rust_python_lib_global_to_staging(rust_python_global_path: str, paths: Paths):
    shutil.copytree(
        f"{rust_python_global_path}/Lib",
        f"{paths['canister']}/Lib",
    )


def create_rust_python_stdlib_staging_directory(rust_python_stdlib_staging_path: str):
    os.makedirs(rust_python_stdlib_staging_path)

    shutil.copy(
        os.path.dirname(basilisk.__file__) + "/compiler/LICENSE-RustPython",
        f"{rust_python_stdlib_staging_path}/LICENSE-RustPython",
    )

    shutil.copy(
        os.path.dirname(basilisk.__file__) + "/compiler/python_3_10_13_licenses.pdf",
        f"{rust_python_stdlib_staging_path}/python_3_10_13_licenses.pdf",
    )


def compile_and_write_rust_python_stdlib_to_staging(
    rust_python_stdlib_staging_path: str,
    paths: Paths,
    cargo_env: dict[str, str],
    verbose: bool,
):
    run_subprocess(
        [
            f"{paths['global_basilisk_rust_bin_dir']}/cargo",
            "run",
            f"--manifest-path={paths['canister']}/basilisk_compile_python_stdlib/Cargo.toml",
            f"--package=basilisk_compile_python_stdlib",
            f"{rust_python_stdlib_staging_path}/stdlib",
        ],
        cargo_env,
        verbose,
    )


def download_rust_python_stdlib(
    rust_python_stdlib_global_path: str,
    paths: Paths,
    cargo_env: dict[str, str],
    verbose: bool,
):
    if not os.path.exists(rust_python_stdlib_global_path):
        download_rust_python_stdlib_tar_gz(paths, cargo_env, verbose)
        extract_and_decompress_rust_python_stdlib_tar_gz(paths, cargo_env, verbose)


def download_rust_python_stdlib_tar_gz(
    paths: Paths, cargo_env: dict[str, str], verbose: bool
):
    run_subprocess(
        [
            "curl",
            "-Lf",
            "https://github.com/demergent-labs/kybra/releases/download/0.7.1/rust_python_stdlib.tar.gz",  # Pinned to kybra 0.7.1 (last available); RustPython backend is deprecated
            "-o",
            "rust_python_stdlib.tar.gz",
        ],
        cargo_env,
        verbose,
        cwd=paths["global_basilisk_version_dir"],
    )


def copy_rust_python_stdlib_global_to_staging(
    rust_python_stdlib_global_path: str, paths: Paths
):
    shutil.copytree(
        rust_python_stdlib_global_path,
        f"{paths['canister']}/rust_python_stdlib",
    )


def extract_and_decompress_rust_python_stdlib_tar_gz(
    paths: Paths, cargo_env: dict[str, str], verbose: bool
):
    run_subprocess(
        ["tar", "-xvf", "rust_python_stdlib.tar.gz"],
        cargo_env,
        verbose,
        cwd=paths["global_basilisk_version_dir"],
    )


def compile_generated_rust_code(
    paths: Paths, canister_name: str, cargo_env: dict[str, str], verbose: bool
):
    run_subprocess(
        [
            f"{paths['global_basilisk_rust_bin_dir']}/cargo",
            "build",
            f"--manifest-path={paths['canister']}/Cargo.toml",
            "--target=wasm32-wasip1",
            f"--package={canister_name}",
            "--release",
        ],
        cargo_env,
        verbose,
    )


def copy_wasm_to_dev_location(paths: Paths, canister_name: str):
    copy_file(
        f"{paths['global_basilisk_target_dir']}/wasm32-wasip1/release/{canister_name}.wasm",
        f"{paths['canister']}/{canister_name}.wasm",
    )


def run_wasi2ic_on_wasm(
    paths: Paths, canister_name: str, cargo_env: dict[str, str], verbose: bool
):
    run_subprocess(
        [
            f"{paths['global_basilisk_rust_bin_dir']}/wasi2ic",
            f"{paths['canister']}/{canister_name}.wasm",
            f"{paths['canister']}/{canister_name}.wasm",
        ],
        cargo_env,
        verbose,
    )


def optimize_wasm(
    paths: Paths, canister_name: str, cargo_env: dict[str, str], verbose: bool
):
    """Run wasm-opt -Oz on the wasm binary to reduce size for IC deployment."""
    wasm_path = f"{paths['canister']}/{canister_name}.wasm"
    wasm_opt = shutil.which("wasm-opt")
    if wasm_opt is None:
        # Try cargo bin directory
        wasm_opt = os.path.expanduser("~/.cargo/bin/wasm-opt")
        if not os.path.exists(wasm_opt):
            print("Warning: wasm-opt not found, skipping wasm optimization")
            return
    run_subprocess(
        [wasm_opt, "-Oz", "--closed-world", "--converge", wasm_path, "-o", wasm_path],
        cargo_env,
        verbose,
    )


def generate_candid_file_from_source(paths: Paths, verbose: bool):
    """Generate .did file by parsing the generated Rust source for candid annotations.

    This is used for CPython builds because candid-extractor cannot run the CPython
    wasm binary — CPython's WASI initialization calls IC system APIs (e.g. ic_cdk::api::time)
    that aren't available in wasmtime outside the IC runtime.

    We parse #[candid::candid_method(query/update, rename = "name")] annotations and
    the following function signature to reconstruct the Candid interface.
    """
    import re

    lib_path = paths["lib"]
    if not os.path.exists(lib_path):
        print("Warning: lib.rs not found, skipping candid generation")
        return

    with open(lib_path, "r") as f:
        content = f.read()

    # Map Rust types to Candid types
    type_map = {
        "String": "text",
        "bool": "bool",
        "u8": "nat8", "u16": "nat16", "u32": "nat32", "u64": "nat64", "u128": "nat",
        "i8": "int8", "i16": "int16", "i32": "int32", "i64": "int64", "i128": "int",
        "f32": "float32", "f64": "float64",
        "()": "",
        "candid::Nat": "nat",
        "candid::Int": "int",
        "candid::Principal": "principal",
        "candid::Empty": "empty",
        "candid::Reserved": "reserved",
    }

    def rust_type_to_candid(rust_type: str) -> str:
        rust_type = rust_type.strip()
        if not rust_type or rust_type == "()":
            return ""
        rust_type = rust_type.strip("()")
        if rust_type in type_map:
            return type_map[rust_type]
        if rust_type.startswith("Vec<") and rust_type.endswith(">"):
            inner = rust_type[4:-1]
            if inner == "u8":
                return "blob"
            return f"vec {rust_type_to_candid(inner)}"
        if rust_type.startswith("Option<") and rust_type.endswith(">"):
            inner = rust_type[7:-1]
            return f"opt {rust_type_to_candid(inner)}"
        # Fallback: use text for unknown types
        return "text"

    # Find all candid_method annotations followed by async fn signatures
    pattern = r'#\[candid::candid_method\((query|update),\s*rename\s*=\s*"([^"]+)"\)\]\s*async\s+fn\s+\w+\(([^)]*)\)\s*->\s*\(([^)]*)\)'
    methods = []
    for match in re.finditer(pattern, content):
        method_type = match.group(1)
        name = match.group(2)
        params_str = match.group(3).strip()
        return_type = match.group(4).strip()

        # Parse parameters (skip self, skip the ones that are just internal args)
        candid_params = []
        if params_str:
            for param in params_str.split(","):
                param = param.strip()
                if ":" in param:
                    parts = param.split(":", 1)
                    param_type = parts[1].strip()
                    candid_type = rust_type_to_candid(param_type)
                    if candid_type:
                        candid_params.append(candid_type)

        candid_return = rust_type_to_candid(return_type)
        params_candid = ", ".join(candid_params)
        returns_candid = candid_return if candid_return else ""

        mode_suffix = f" {method_type}" if method_type == "query" else ""
        methods.append(f'  "{name}" : ({params_candid}) -> ({returns_candid}){mode_suffix};')

    candid_string = "service : {\n" + "\n".join(methods) + "\n}\n"

    if verbose:
        print(candid_string)

    create_file(paths["did"], candid_string)


def generate_and_create_candid_file(
    paths: Paths, canister_name: str, cargo_env: dict[str, str], verbose: bool
):
    candid_bytes = run_subprocess(
        [
            f"{paths['global_basilisk_rust_bin_dir']}/candid-extractor",
            f"{paths['canister']}/{canister_name}.wasm",
        ],
        cargo_env,
        False,  # Passing verbose along as True messes with the std outputs
    )

    candid_string = candid_bytes.decode()

    if verbose == True:
        print(candid_string)

    create_file(paths["did"], candid_string)


def run_subprocess(
    args: list[str],
    env: dict[str, str],
    verbose: bool,
    throw: bool = True,
    cwd: str | None = None,
) -> bytes:
    result = subprocess.run(args, env=env, capture_output=not verbose, cwd=cwd)

    if result.returncode != 0:
        if throw == True:
            print_error_and_exit(result)
        else:
            return result.stderr

    return result.stdout


def copy_file(source: str, destination: str):
    shutil.copy(source, destination)


def create_file(path: str, content: str):
    with open(path, "w") as f:
        f.write(content)


def print_error_and_exit(result: subprocess.CompletedProcess[bytes]):
    print(red("\n💣 Basilisk error: building Wasm binary"))
    print(result.stderr.decode("utf-8"))
    print("💀 Build failed")
    sys.exit(1)
