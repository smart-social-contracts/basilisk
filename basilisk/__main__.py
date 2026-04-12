import modulefinder
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import site
from typing import Any, Callable

import basilisk
from basilisk.build_wasm_binary_or_exit import build_wasm_binary_or_exit
from basilisk.colors import red, yellow, green, dim
from basilisk.timed import timed, timed_inline
from basilisk.types import Args, Paths


@timed
def main():
    # TODO this way of installing the extension is just temporary
    # TODO we should use the official dfx extension install command
    # TODO are the dfx extensions repository once those mature
    if sys.argv[1] == "install-dfx-extension":
        subprocess.run(
            ["./install.sh"],
            cwd=os.path.join(
                os.path.dirname(basilisk.__file__), "compiler", "dfx_extension"
            ),
        )
        return

    args = parse_args_or_exit(sys.argv)
    paths = create_paths(args)
    is_verbose = args["flags"]["verbose"] or os.environ.get("BASILISK_VERBOSE") == "true"

    subprocess.run(
        [
            f"{paths['compiler']}/install_rust_dependencies.sh",
            basilisk.__version__,
            basilisk.__rust_version__,
        ]
    )

    # This is the name of the canister passed into python -m basilisk from the dfx.json build command
    canister_name = args["canister_name"]

    verbose_mode_qualifier = " in verbose mode" if is_verbose else ""

    print(f"\nBuilding canister {green(canister_name)}{verbose_mode_qualifier}\n")

    os.makedirs(paths["canister"], exist_ok=True)

    cargo_env = {
        **os.environ.copy(),
        "CARGO_TARGET_DIR": paths["global_basilisk_target_dir"],
        "CARGO_HOME": paths["global_basilisk_rust_dir"],
        "RUSTUP_HOME": paths["global_basilisk_rust_dir"],
    }

    bundle_python_code(paths)

    build_wasm_binary_or_exit(
        paths,
        canister_name,
        cargo_env,
        verbose=is_verbose,
        label=f"[1/1] ⚡ Building Wasm from template...",
    )

    print(f"\n🎉 Built canister {green(canister_name)} at {dim(paths['wasm'])}")


def parse_args_or_exit(args: list[str]) -> Args:
    args = args[1:]  # Discard the path to basilisk

    flags = [arg for arg in args if (arg.startswith("-") or arg.startswith("--"))]
    args = [arg for arg in args if not (arg.startswith("-") or arg.startswith("--"))]

    if len(args) == 0:
        print(f"\nbasilisk {basilisk.__version__}")
        print("\nUsage: basilisk [-v|--verbose] <canister_name> <entry_point>")
        sys.exit(0)

    if len(args) != 2:
        print(red("\n💣 Basilisk error: wrong number of arguments\n"))
        print("Usage: basilisk [-v|--verbose] <canister_name> <entry_point>")
        print("\n💀 Build failed!")
        sys.exit(1)

    return {
        "empty": False,
        "flags": {"verbose": "--verbose" in flags or "-v" in flags},
        "canister_name": args[0],
        "entry_point": args[1],
    }


def create_paths(args: Args) -> Paths:
    canister_name = args["canister_name"]

    # This is the path to the developer's entry point Python file passed into python -m basilisk from the dfx.json build command
    py_entry_file_path = args["entry_point"]

    # This is the Python module name of the developer's Python project, derived from the entry point Python file passed into python -m basilisk from the dfx.json build command
    py_entry_module_name = Path(py_entry_file_path).stem

    # This is the location of all code used to generate the final canister Rust code
    canister_path = f".basilisk/{canister_name}"

    python_source_path = f"{canister_path}/python_source"

    py_file_names_file_path = f"{canister_path}/py_file_names.csv"

    # This is the path to the developer's Candid file as resolved by dfx
    did_path = os.environ.get("CANISTER_CANDID_PATH")

    if did_path is None:
        raise Exception("Basilisk: CANISTER_CANDID_PATH is not defined")

    # This is the path to the Basilisk compiler Rust code delivered with the Python package
    compiler_path = os.path.dirname(basilisk.__file__) + "/compiler"

    # This is the final generated Rust file that is the canister
    lib_path = f"{canister_path}/src/lib.rs"

    # This is the location of the Candid file generated from the final generated Rust file
    generated_did_path = f"{canister_path}/index.did"

    # This is the unzipped generated Wasm that is the canister
    wasm_path = f"{canister_path}/{canister_name}.wasm"

    # This is where we store custom Python modules, such as stripped-down versions of stdlib modules
    custom_modules_path = f"{compiler_path}/custom_modules"

    home_dir = os.path.expanduser("~")
    global_basilisk_config_dir = f"{home_dir}/.config/basilisk"
    global_basilisk_version_dir = f"{global_basilisk_config_dir}/{basilisk.__version__}"
    global_basilisk_rust_dir = f"{global_basilisk_config_dir}/rust/{basilisk.__rust_version__}"
    global_basilisk_rust_bin_dir = f"{global_basilisk_rust_dir}/bin"
    global_basilisk_target_dir = f"{global_basilisk_config_dir}/rust/target"
    global_basilisk_bin_dir = f"{global_basilisk_config_dir}/{basilisk.__version__}/bin"

    return {
        "py_entry_file": py_entry_file_path,
        "py_entry_module_name": py_entry_module_name,
        "canister": canister_path,
        "python_source": python_source_path,
        "py_file_names_file": py_file_names_file_path,
        "did": did_path,
        "compiler": compiler_path,
        "lib": lib_path,
        "generated_did": generated_did_path,
        "wasm": wasm_path,
        "custom_modules": custom_modules_path,
        "global_basilisk_config_dir": global_basilisk_config_dir,
        "global_basilisk_version_dir": global_basilisk_version_dir,
        "global_basilisk_rust_dir": global_basilisk_rust_dir,
        "global_basilisk_rust_bin_dir": global_basilisk_rust_bin_dir,
        "global_basilisk_target_dir": global_basilisk_target_dir,
        "global_basilisk_bin_dir": global_basilisk_bin_dir,
    }


def bundle_python_code(paths: Paths):
    # Begin module bundling/gathering process
    path = (
        list(filter(lambda x: x.startswith(os.getcwd()), sys.path))
        + [p for p in sys.path if "site-packages" in p or "dist-packages" in p]
        + [
            os.path.dirname(paths["py_entry_file"]),
            os.path.dirname(os.path.dirname(basilisk.__file__)),
        ]
        + site.getsitepackages()
        + [site.getusersitepackages()]
    )

    finder = modulefinder.ModuleFinder(path=path)
    finder.run_script(paths["py_entry_file"])

    # ── Reject pip packages that contain native (C) extensions ──
    _check_native_extensions(finder)

    # ── Warn about unresolved imports ──
    _warn_unresolved_imports(finder)

    python_source_path = paths["python_source"]

    if os.path.exists(python_source_path):
        shutil.rmtree(python_source_path)

    os.makedirs(python_source_path)

    # Copy our custom Python modules into the python_source directory
    shutil.copytree(paths["custom_modules"], python_source_path, dirs_exist_ok=True)

    # Copy the entry-point script itself
    shutil.copy(
        paths["py_entry_file"],
        f"{python_source_path}/{os.path.basename(paths['py_entry_file'])}",
    )

    bundled_packages: dict[str, int] = {}  # top-level package -> module count

    for name, mod in finder.modules.items():
        if mod.__file__ is None:
            continue  # built-in module, skip

        if mod.__path__:
            # Package — copy the directory tree
            if should_skip_package(name, mod.__path__[0]):
                continue
            dest_dir = name.replace(".", os.sep)
            shutil.copytree(
                mod.__path__[0],
                f"{python_source_path}/{dest_dir}",
                dirs_exist_ok=True,
                ignore=ignore_specific_dir,
            )
            _ensure_parent_inits(python_source_path, dest_dir)
            if _is_from_site_packages(mod.__path__[0]):
                _track_bundled_package(bundled_packages, name)
        else:
            # Source module — copy the single file
            # Use dotted identifier to build path so modules with the same
            # basename (e.g. _pytest.main vs the entry-point main) don't
            # overwrite each other.
            dest_name = name.replace(".", os.sep) + ".py"
            dest_path = f"{python_source_path}/{dest_name}"
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if mod.__file__.endswith(".py"):
                shutil.copy(mod.__file__, dest_path)
                if _is_from_site_packages(mod.__file__):
                    _track_bundled_package(bundled_packages, name)

    # ── Print bundled packages summary ──
    _print_bundle_summary(bundled_packages)

    py_file_names = [
        mod.__file__
        for mod in finder.modules.values()
        if mod.__file__ is not None and mod.__file__.endswith(".py")
    ]

    create_file(paths["py_file_names_file"], ",".join(py_file_names))


def ignore_specific_dir(dirname: str, filenames: list[str]) -> list[str]:
    if "basilisk_post_install/src/Lib" in dirname:
        return filenames
    # Exclude build output, caches, and template scaffolding from copytree
    ignored = []
    for f in filenames:
        if f in (".basilisk", "__pycache__", ".dfx"):
            ignored.append(f)
    return ignored


def _is_from_site_packages(filepath: str) -> bool:
    """Return True if the file lives inside a site-packages or dist-packages directory."""
    return "site-packages" in filepath or "dist-packages" in filepath


def _track_bundled_package(bundled_packages: dict[str, int], module_name: str):
    """Increment the module count for the top-level package of *module_name*."""
    top_level = module_name.split(".")[0]
    bundled_packages[top_level] = bundled_packages.get(top_level, 0) + 1


def _check_native_extensions(finder: modulefinder.ModuleFinder):
    """Error out if any pip-installed package contains native (C) extensions.

    Stdlib native extensions (e.g. _json.so in lib-dynload) are ignored —
    the WASI canister template provides its own stubs for those.
    Only third-party packages in site-packages/dist-packages are checked.
    """
    import importlib.machinery
    native_suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)  # e.g. ('.so',)

    # Collect native modules grouped by top-level pip package
    native_packages: dict[str, list[str]] = {}  # top_pkg -> [module_names]
    for name, mod in finder.modules.items():
        if mod.__file__ is None:
            continue
        if not mod.__file__.endswith(native_suffixes):
            continue
        if not _is_from_site_packages(mod.__file__):
            continue  # stdlib / lib-dynload — handled by WASI stubs
        top_pkg = name.split(".")[0]
        native_packages.setdefault(top_pkg, []).append(name)

    if native_packages:
        lines = []
        for pkg, modules in sorted(native_packages.items()):
            ext = os.path.splitext(finder.modules[modules[0]].__file__)[1]
            lines.append(
                f"  - {pkg} contains native code ({ext}), not supported on IC"
            )
        msg = (
            red("\n\U0001f4a3 Basilisk error: native extensions detected\n\n")
            + "\n".join(lines)
            + "\n\nOnly pure Python packages can run inside an IC canister.\n"
            "Remove these packages or replace them with pure Python alternatives.\n"
        )
        print(msg)
        sys.exit(1)


def _warn_unresolved_imports(finder: modulefinder.ModuleFinder):
    """Print warnings for imports that modulefinder could not resolve.

    Excludes known false positives from stdlib and basilisk internals.
    """
    IGNORE_PREFIXES = (
        "_",          # private C accelerators (_pickle, _io, etc.)
        "win32",      # Windows-only modules
        "org.python", # Jython
        "java",       # Jython
    )
    IGNORE_EXACT = {
        "nt", "posix", "msvcrt", "winreg", "_winapi",
        "vms_lib", "EasyDialogs", "Carbon",
        "org", "java",
        "test", "tests",
    }

    unresolved = []
    for name in sorted(finder.badmodules):
        if name in IGNORE_EXACT:
            continue
        if any(name.startswith(p) for p in IGNORE_PREFIXES):
            continue
        unresolved.append(name)

    if unresolved:
        print(yellow(f"\n\u26a0\ufe0f  {len(unresolved)} unresolved import(s) (may be fine if unused at runtime):"))
        for name in unresolved[:10]:
            print(f"  - {name}")
        if len(unresolved) > 10:
            print(f"  ... and {len(unresolved) - 10} more")
        print()


def _print_bundle_summary(bundled_packages: dict[str, int]):
    """Print a summary of pip packages that were bundled into the canister."""
    if not bundled_packages:
        return
    print(f"\n\U0001f4e6 Bundled {len(bundled_packages)} pip package(s):")
    for pkg in sorted(bundled_packages):
        count = bundled_packages[pkg]
        suffix = "module" if count == 1 else "modules"
        print(f"  - {pkg} ({count} {suffix})")
    print()


def should_skip_package(node_identifier: str, node_packagepath: str) -> bool:
    """Skip the top-level basilisk package (compiler, shell, templates, etc.)
    but allow canister-side subpackages through.
    Works for both pip-installed and editable (pip install -e) installs."""
    # Skip the top-level basilisk package but not its subpackages
    if node_identifier == "basilisk":
        return True
    return False


def _ensure_parent_inits(python_source_path: str, dest_dir: str):
    """Create empty __init__.py in parent directories for nested packages.

    E.g. for dest_dir='basilisk/canisters', ensures basilisk/__init__.py exists
    so that nested imports work at runtime.
    """
    parts = dest_dir.split(os.sep)
    for i in range(1, len(parts)):
        parent = os.path.join(python_source_path, *parts[:i])
        init_file = os.path.join(parent, "__init__.py")
        if not os.path.exists(init_file):
            os.makedirs(parent, exist_ok=True)
            with open(init_file, "w") as f:
                f.write("")


def parse_basilisk_generate_error(stdout: bytes) -> str:
    err = stdout.decode("utf-8")
    std_err_lines = err.splitlines()
    try:
        line_where_error_message_starts = next(
            i
            for i, v in enumerate(std_err_lines)
            if v.startswith("thread 'main' panicked at '")
        )
        line_where_error_message_ends = next(
            i for i, v in enumerate(std_err_lines) if "', src/" in v
        )
    except:
        return err

    err_lines = std_err_lines[
        line_where_error_message_starts : line_where_error_message_ends + 1
    ]
    err_lines[0] = err_lines[0].replace("thread 'main' panicked at '", "")
    err_lines[-1] = re.sub("', src/.*", "", err_lines[-1])

    return red("\n".join(err_lines))


def create_file(file_path: str, contents: str):
    file = open(file_path, "w")
    file.write(contents)
    file.close()


def inline_timed(
    label: str,
    body: Callable[..., Any],
    *args: Any,
    verbose: bool = False,
    **kwargs: Any,
) -> float:
    print(label)
    start_time = time.time()
    body(*args, verbose=verbose, **kwargs)
    end_time = time.time()
    duration = end_time - start_time

    if verbose:
        print(f"{label} finished in {round(duration, 2)}s")
    else:
        move_cursor_up_one_line = "\x1b[1A"
        print(f'{move_cursor_up_one_line}{label} {dim(f"{round(duration, 2)}s")}')

    return end_time - start_time


if __name__ == "__main__":
    main()
