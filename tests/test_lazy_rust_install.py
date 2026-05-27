"""Rust toolchain install runs only on template-from-source fallback."""

import os
from unittest.mock import MagicMock, patch

import basilisk
import pytest

from basilisk.build_wasm_binary_or_exit import (
    build_template_from_source,
    ensure_rust_dependencies,
)


def _minimal_paths(tmp_path, compiler_dir):
    version_dir = tmp_path / "0.0.0-test"
    version_dir.mkdir(parents=True)
    rust_dir = tmp_path / "rust" / "1.88.0"
    rust_dir.mkdir(parents=True)
    return {
        "py_entry_file": str(tmp_path / "main.py"),
        "py_entry_module_name": "main",
        "canister": str(tmp_path / "canister"),
        "python_source": str(tmp_path / "python_source"),
        "py_file_names_file": str(tmp_path / "py_file_names.csv"),
        "did": str(tmp_path / "out.did"),
        "compiler": str(compiler_dir),
        "lib": str(tmp_path / "lib.rs"),
        "generated_did": str(tmp_path / "index.did"),
        "wasm": str(tmp_path / "canister" / "test.wasm"),
        "custom_modules": str(compiler_dir / "custom_modules"),
        "global_basilisk_config_dir": str(tmp_path),
        "global_basilisk_version_dir": str(version_dir),
        "global_basilisk_rust_dir": str(rust_dir),
        "global_basilisk_rust_bin_dir": str(rust_dir / "bin"),
        "global_basilisk_target_dir": str(tmp_path / "rust" / "target"),
        "global_basilisk_bin_dir": str(version_dir / "bin"),
    }


@pytest.fixture
def paths(tmp_path):
    compiler = tmp_path / "compiler"
    compiler.mkdir()
    (compiler / "install_rust_dependencies.sh").write_text("#!/bin/bash\nexit 0\n")
    (compiler / "custom_modules").mkdir()
    template_dir = compiler / "cpython_canister_template"
    template_dir.mkdir()
    (template_dir / "Cargo.toml").write_text("[package]\nname = \"cpython_canister_template\"\n")
    return _minimal_paths(tmp_path, compiler)


def test_ensure_rust_dependencies_invokes_install_script(paths):
    with patch("basilisk.build_wasm_binary_or_exit.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        ensure_rust_dependencies(paths)

    install_script = os.path.join(paths["compiler"], "install_rust_dependencies.sh")
    run.assert_called_once_with(
        [install_script, basilisk.__version__, basilisk.__rust_version__],
        check=False,
    )


def test_build_template_from_source_calls_ensure_rust_first(paths):
    with (
        patch(
            "basilisk.build_wasm_binary_or_exit.ensure_rust_dependencies"
        ) as ensure_rust,
        patch("basilisk.build_wasm_binary_or_exit.install_cpython_wasm"),
        patch("basilisk.build_wasm_binary_or_exit.run_subprocess"),
        patch("basilisk.build_wasm_binary_or_exit.shutil.copy"),
        patch("basilisk.build_wasm_binary_or_exit.os.path.exists", return_value=True),
    ):
        build_template_from_source(paths, {}, verbose=False)

    ensure_rust.assert_called_once_with(paths)
