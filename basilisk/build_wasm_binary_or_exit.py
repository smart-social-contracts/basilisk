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
    python_backend = os.environ.get("BASILISK_PYTHON_BACKEND", "rustpython")
    if python_backend == "cpython":
        install_cpython_wasm(paths, cargo_env, verbose)
        copy_cpython_to_canister_staging(paths)
    else:
        compile_or_download_rust_python_stdlib(paths, cargo_env, verbose)
    compile_generated_rust_code(paths, canister_name, cargo_env, verbose)
    copy_wasm_to_dev_location(paths, canister_name)
    run_wasi2ic_on_wasm(paths, canister_name, cargo_env, verbose)
    if python_backend == "cpython":
        generate_candid_file_from_source(paths, verbose)
    else:
        generate_and_create_candid_file(paths, canister_name, cargo_env, verbose)


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


def copy_cpython_to_canister_staging(paths: Paths):
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
            f"https://github.com/demergent-labs/kybra/releases/download/{basilisk.__version__}/rust_python_stdlib.tar.gz",  # Keep kybra URL - external dependency
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
        rust_type = rust_type.strip().strip("()")
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

        methods.append(f'  "{name}" : ({params_candid}) -> ({returns_candid}) {method_type};')

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
