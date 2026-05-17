import os
import shutil
import subprocess
import sys
import urllib.request

import basilisk
from basilisk.colors import red
from basilisk.timed import timed_inline
from basilisk.types import Paths

TEMPLATE_DOWNLOAD_URL = (
    "https://github.com/smart-social-contracts/basilisk/releases/download"
    "/v{version}/cpython_canister_template.wasm"
)

# Fallback: CI uploads the template to the cpython-wasm release (not versioned)
TEMPLATE_DOWNLOAD_URL_FALLBACK = (
    "https://github.com/smart-social-contracts/basilisk/releases/download"
    "/cpython-wasm-3.13.0/cpython_canister_template.wasm"
)


@timed_inline
def build_wasm_binary_or_exit(
    paths: Paths, canister_name: str, cargo_env: dict[str, str], verbose: bool = False
):
    build_with_template(paths, canister_name, cargo_env, verbose)


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
        extract_features_from_python,
        extract_stable_structures_from_python,
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
    # For multi-file / multi-canister projects:
    #   - Extract from the full src/ tree so cross-canister types (e.g. AccountArgs
    #     from canister2/types.py) are in the registry when resolving method params.
    #   - Then filter methods to only keep those defined in the entry file's directory
    #     (avoids picking up methods from other canisters that cause .did collisions).
    py_entry_file = paths.get("py_entry_file", "")
    user_src_dir = os.path.dirname(py_entry_file) if py_entry_file else ""
    if user_src_dir and os.path.isdir(user_src_dir):
        # Determine entry dir method names (for filtering)
        entry_dir_sources = []
        for root, _dirs, files in os.walk(user_src_dir):
            for fname in sorted(files):
                if fname.endswith(".py"):
                    with open(os.path.join(root, fname), "r") as f:
                        entry_dir_sources.append(f.read())
        entry_raw = "\n".join(entry_dir_sources)
        entry_methods, entry_type_defs, entry_lifecycle = extract_methods_from_python(entry_raw)
        entry_method_names = {m["name"] for m in entry_methods}
        entry_lifecycle_keys = set(entry_lifecycle.keys())

        # Find the src/ root for the full tree extraction
        entry_parts = os.path.normpath(py_entry_file).split(os.sep)
        src_root = user_src_dir  # default: just use entry dir
        if "src" in entry_parts:
            src_idx = entry_parts.index("src")
            candidate = os.sep.join(entry_parts[: src_idx + 1])
            if os.path.isdir(candidate):
                src_root = candidate

        # Extract from full src/ tree (types + methods with correct type resolution)
        # Put entry dir sources FIRST so entry dir methods appear first in the AST
        # and win deduplication (e.g. heartbeat_async vs heartbeat_sync both have
        # get_initialized with different return types)
        norm_entry_dir = os.path.normpath(user_src_dir)
        all_sources = list(entry_dir_sources)  # entry dir first
        for root, _dirs, files in os.walk(src_root):
            if os.path.normpath(root).startswith(norm_entry_dir):
                continue  # already included from entry dir
            for fname in sorted(files):
                if fname.endswith(".py"):
                    with open(os.path.join(root, fname), "r") as f:
                        all_sources.append(f.read())
        all_raw = "\n".join(all_sources)
        all_methods, type_defs, all_lifecycle = extract_methods_from_python(all_raw)

        # Filter: keep only methods/lifecycle from the entry directory
        # Deduplicate by name (other canisters may define methods with the same name)
        methods = []
        seen_names = set()
        for m in all_methods:
            if m["name"] in entry_method_names and m["name"] not in seen_names:
                methods.append(m)
                seen_names.add(m["name"])
        lifecycle = {k: entry_lifecycle[k] for k in entry_lifecycle_keys}
        # Override type_defs with entry-dir types to avoid name collisions
        # (e.g. StatusRecord defined differently in multiple canisters)
        type_defs.update(entry_type_defs)
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

    # 3b. Inject __shell__ and __browse__ if opted in via __basilisk_features__.
    features = extract_features_from_python(python_source)
    user_method_names = {m["name"] for m in methods}

    if features and verbose:
        print(f"  __basilisk_features__: {features}")

    if "shell" in features and "__shell__" not in user_method_names:
        python_source += _generate_default_shell_code()
        methods.append({
            "name": "__basilisk_controller_guard__",
            "method_type": "_guard",  # internal, not a canister method
        })
        methods.append({
            "name": "__shell__",
            "method_type": "update",
            "params": [{"name": "code", "candid_type": "text"}],
            "returns": "text",
            "guard": "__basilisk_controller_guard__",
        })
        if verbose:
            print("  Injected built-in __shell__ (update, controller-only)")

    if "browse" in features and "__browse__" not in user_method_names:
        stable_structures = extract_stable_structures_from_python(python_source)
        python_source += _generate_default_browse_code(stable_structures)
        methods.append({
            "name": "__browse__",
            "method_type": "query",
            "params": [{"name": "query", "candid_type": "text"}],
            "returns": "text",
        })
        if verbose:
            print(f"  Injected built-in __browse__ (query, {len(stable_structures)} stable structure(s))")

    # 3c. Inject automatic schema upgrade check into post_upgrade.
    # If ic_python_db is present, check_upgrade_compatibility() runs after the
    # user's post_upgrade (if any).  If the check fails, the IC rolls back.
    if "post_upgrade" in lifecycle:
        user_fn_name = lifecycle["post_upgrade"]["name"]
        python_source += _generate_post_upgrade_wrapper(user_fn_name)
        lifecycle["post_upgrade"]["name"] = "_basilisk_post_upgrade_wrapper"
        if verbose:
            print(f"  Wrapped {user_fn_name}() with schema upgrade check")
    else:
        python_source += _generate_post_upgrade_wrapper(None)
        lifecycle["post_upgrade"] = {
            "name": "_basilisk_post_upgrade_wrapper",
            "method_type": "post_upgrade",
            "params": [],
            "returns": "void",
        }
        if verbose:
            print("  Injected post_upgrade with schema upgrade check")

    # Filter out internal-only entries (guards) before generating .did
    methods = [m for m in methods if m["method_type"] != "_guard"]

    # 3d. Add __get_candid_interface_tmp_hack built-in query method.
    # The Candid UI calls this to fetch the .did interface at runtime.
    hack_method = {
        "name": "__get_candid_interface_tmp_hack",
        "method_type": "query",
        "params": [],
        "returns": "text",
    }
    methods.append(hack_method)

    # Generate .did content (including the hack method) so we can embed it
    candid_content = generate_candid_from_methods(methods, type_defs, lifecycle)

    # Append a Python function that returns the .did content
    python_source += (
        "\ndef __get_candid_interface_tmp_hack() -> str:\n"
        "    return " + repr(candid_content) + "\n"
    )

    # 4. Inject Python source + method metadata into template wasm
    output_wasm = f"{paths['canister']}/{canister_name}.wasm"
    os.makedirs(os.path.dirname(output_wasm), exist_ok=True)
    manipulate_wasm(template_wasm_path, output_wasm, python_source, methods, type_defs, lifecycle)

    # 5. Skip wasi2ic and wasm-opt: the downloaded template is already post-processed.
    # Running wasm-opt again would strip the passive data segments we just injected.
    # Running wasi2ic again on an already-converted binary would corrupt it.

    # 6. Write .did file (already generated above with the hack method included)
    create_file(paths["did"], candid_content)
    if verbose:
        print(f"Generated Candid file: {paths['did']}")
        print(candid_content)


def find_template_wasm(paths: Paths) -> str | None:
    """Locate the pre-built CPython canister template wasm.

    Searches in order:
    1. BASILISK_TEMPLATE_WASM env var (explicit path)
    2. ~/.config/basilisk/<version>/cpython_canister_template.wasm (cached artifact)
    3. Download from GitHub release and cache at (2)
    4. <compiler_dir>/cpython_canister_template/target/wasm32-wasip1/release/cpython_canister_template.wasm (local build)
    """
    # 1. Explicit path
    explicit = os.environ.get("BASILISK_TEMPLATE_WASM")
    if explicit and os.path.exists(explicit):
        return explicit

    # 2. Cached artifact
    artifact_path = f"{paths['global_basilisk_version_dir']}/cpython_canister_template.wasm"
    if os.path.exists(artifact_path):
        return artifact_path

    # 3. Download from GitHub release
    downloaded = _download_template(artifact_path)
    if downloaded:
        return artifact_path

    # 4. Local build
    compiler_dir = os.path.dirname(basilisk.__file__) + "/compiler"
    local_path = f"{compiler_dir}/cpython_canister_template/target/wasm32-wasip1/release/cpython_canister_template.wasm"
    if os.path.exists(local_path):
        return local_path

    return None


def _download_template(dest_path: str) -> bool:
    """Download the pre-built template WASM from the GitHub release.

    Tries the versioned release first (v{version}), then falls back to the
    cpython-wasm release where CI uploads the latest template.
    Returns True if the download succeeded, False otherwise.
    """
    urls = [
        TEMPLATE_DOWNLOAD_URL.format(version=basilisk.__version__),
        TEMPLATE_DOWNLOAD_URL_FALLBACK,
    ]
    for url in urls:
        print(f"Downloading CPython canister template from {url} ...")
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            urllib.request.urlretrieve(url, dest_path)
            size_mb = os.path.getsize(dest_path) / (1024 * 1024)
            print(f"Template downloaded ({size_mb:.1f} MB) -> {dest_path}")

            # Verify integrity: try to download .sha256 checksum and validate
            _verify_template_checksum(url, dest_path)

            return True
        except Exception as e:
            print(f"Download failed: {e}")
            if os.path.exists(dest_path):
                os.remove(dest_path)
    return False


def _verify_template_checksum(wasm_url: str, wasm_path: str) -> None:
    """Verify downloaded WASM against a .sha256 checksum file (if available).

    Downloads <wasm_url>.sha256 and compares the hash. If the checksum file
    is not found (404), prints a warning but does not fail — this allows
    older releases without checksums to still work.
    """
    import hashlib

    checksum_url = wasm_url + ".sha256"
    try:
        response = urllib.request.urlopen(checksum_url)
        expected_hash = response.read().decode("utf-8").strip().split()[0].lower()
    except Exception:
        print("Warning: No .sha256 checksum file found for template WASM — skipping verification")
        return

    with open(wasm_path, "rb") as f:
        actual_hash = hashlib.sha256(f.read()).hexdigest().lower()

    if actual_hash != expected_hash:
        os.remove(wasm_path)
        raise RuntimeError(
            f"Template WASM checksum mismatch!\n"
            f"  Expected: {expected_hash}\n"
            f"  Actual:   {actual_hash}\n"
            f"This could indicate a corrupted download or supply-chain attack.\n"
            f"The file has been removed. Try again or build from source."
        )


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

            # Skip the top-level basilisk __init__ - provided by the Rust
            # BASILISK_PYTHON_SHIM.  Subpackages like basilisk.canisters are pure-Python
            # and must be bundled so canister code can import them.
            if mod_name == "basilisk":
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


def _generate_default_shell_code() -> str:
    """Return Python source for the default __shell__ and its controller guard."""
    return '''
_basilisk_shell_ns = {}

def __basilisk_controller_guard__():
    if _basilisk_ic.is_controller(_basilisk_ic.caller()):
        return {"Ok": None}
    return {"Err": "only controllers may use __shell__"}

def __shell__(code: str) -> str:
    import io as _io
    import sys as _sys
    import traceback as _tb
    caller = str(_basilisk_ic.caller())
    if caller not in _basilisk_shell_ns:
        _basilisk_shell_ns[caller] = {"__builtins__": __builtins__}
        _basilisk_shell_ns[caller]["ic"] = ic
        _basilisk_shell_ns[caller]["basilisk"] = __import__("basilisk")
    ns = _basilisk_shell_ns[caller]
    stdout, stderr = _io.StringIO(), _io.StringIO()
    _sys.stdout, _sys.stderr = stdout, stderr
    try:
        exec(code, ns, ns)
    except Exception:
        _tb.print_exc()
    _sys.stdout, _sys.stderr = _sys.__stdout__, _sys.__stderr__
    return stdout.getvalue() + stderr.getvalue()
'''


def _generate_post_upgrade_wrapper(user_fn_name: str | None) -> str:
    """Return Python source that wraps post_upgrade with a schema compatibility check.

    If ``user_fn_name`` is given, the wrapper calls the user's original function
    first, then runs the check.  If ``None``, the wrapper only runs the check.
    The check is guarded by try/except so canisters without ic_python_db are
    unaffected.
    """
    call_user = f"    {user_fn_name}()\n" if user_fn_name else ""
    return f'''
def _basilisk_post_upgrade_wrapper():
{call_user}    try:
        from ic_python_db import Database as _DB
        _db = _DB.get_instance()
        _db.check_upgrade_compatibility()
    except ImportError:
        pass
    except Exception as _e:
        _basilisk_ic.trap(f"Upgrade rejected: {{_e}}")
'''


def _generate_default_browse_code(stable_structures: list[dict]) -> str:
    """Return Python source for the default __browse__ endpoint."""
    import json

    schema = {
        "stable_maps": {},
        "stable_sets": {},
        "stable_vecs": {},
    }
    registry_lines = ["_basilisk_browse_registry = {}"]

    for ss in stable_structures:
        name = ss["name"]
        st = ss["structure_type"]
        entry = {"memory_id": ss["memory_id"]}

        if st == "StableBTreeMap":
            entry["key_type"] = ss.get("key_type", "unknown")
            entry["value_type"] = ss.get("value_type", "unknown")
            schema["stable_maps"][name] = entry
            registry_lines.append(
                f'_basilisk_browse_registry[{name!r}] = {{"ref": {name}, "type": "map"}}'
            )
        elif st == "StableBTreeSet":
            entry["key_type"] = ss.get("key_type", "unknown")
            schema["stable_sets"][name] = entry
            registry_lines.append(
                f'_basilisk_browse_registry[{name!r}] = {{"ref": {name}, "type": "set"}}'
            )
        elif st == "StableVec":
            entry["value_type"] = ss.get("value_type", "unknown")
            schema["stable_vecs"][name] = entry
            registry_lines.append(
                f'_basilisk_browse_registry[{name!r}] = {{"ref": {name}, "type": "vec"}}'
            )

    # Remove empty categories from schema
    schema = {k: v for k, v in schema.items() if v}

    schema_json = json.dumps(schema)
    registry_block = "\n".join(registry_lines)

    return f'''
{registry_block}

_BASILISK_BROWSE_DEFAULT_LIMIT = 100

def __browse__(query: str) -> str:
    import json as _json
    try:
        q = _json.loads(query)
    except Exception:
        return _json.dumps({{"error": "invalid JSON"}})
    action = q.get("action", "")
    limit = min(int(q.get("limit", _BASILISK_BROWSE_DEFAULT_LIMIT)), 10000)
    offset = int(q.get("offset", 0))

    if action == "schema":
        _schema = _json.loads({schema_json!r})
        try:
            from ic_python_db import Database as _DB
            _db = _DB.get_instance()
            _schema["entities"] = _db.build_schema_from_entities()
            _schema["schema_hash"] = _db.get_schema_hash()
        except Exception:
            pass
        return _json.dumps(_schema)

    target_name = q.get("map") or q.get("set") or q.get("vec")
    if not target_name:
        return _json.dumps({{"error": "missing target name (map, set, or vec)", "available": list(_basilisk_browse_registry.keys())}})
    if target_name not in _basilisk_browse_registry:
        return _json.dumps({{"error": f"unknown target: {{target_name}}", "available": list(_basilisk_browse_registry.keys())}})

    entry = _basilisk_browse_registry[target_name]
    ref = entry["ref"]
    stype = entry["type"]

    if action == "len":
        return _json.dumps({{"result": ref.len()}})

    if action == "keys":
        if stype == "map":
            all_keys = ref.keys()
            return _json.dumps({{"result": all_keys[offset:offset + limit], "total": len(all_keys)}})
        elif stype == "set":
            all_items = ref.items()
            return _json.dumps({{"result": all_items[offset:offset + limit], "total": len(all_items)}})
        return _json.dumps({{"error": "keys not supported for this type"}})

    if action == "get":
        key = q.get("key")
        if key is None:
            return _json.dumps({{"error": "missing key"}})
        if stype == "map":
            return _json.dumps({{"result": ref.get(key)}})
        elif stype == "vec":
            try:
                return _json.dumps({{"result": ref.get(int(key))}})
            except (ValueError, TypeError):
                return _json.dumps({{"error": "vec index must be an integer"}})
        return _json.dumps({{"error": "get not supported for this type"}})

    if action == "items":
        if stype == "map":
            all_items = ref.items()
            return _json.dumps({{"result": all_items[offset:offset + limit], "total": len(all_items)}})
        elif stype == "set":
            all_items = ref.items()
            return _json.dumps({{"result": all_items[offset:offset + limit], "total": len(all_items)}})
        elif stype == "vec":
            total = ref.len()
            end = min(offset + limit, total)
            return _json.dumps({{"result": [ref.get(i) for i in range(offset, end)], "total": total}})
        return _json.dumps({{"error": "items not supported for this type"}})

    return _json.dumps({{"error": f"unknown action: {{action}}", "actions": ["schema", "len", "keys", "get", "items"]}})
'''


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
