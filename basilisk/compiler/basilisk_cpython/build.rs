//! Build script for basilisk_cpython.
//!
//! Locates the CPython static library (libpython3.13.a) and headers,
//! and configures the linker to include them when building for wasm32-wasip1.
//!
//! The CPYTHON_WASM_DIR environment variable must point to the directory
//! containing lib/libpython3.13.a and include/ (CPython headers).

use std::env;
use std::path::PathBuf;

fn main() {
    let target = env::var("TARGET").unwrap_or_default();

    // Only link CPython when targeting wasm32-wasip1 (canister runtime)
    // For host builds (basilisk_generate), we don't need the actual CPython library
    if !target.contains("wasm32") {
        println!("cargo:warning=basilisk_cpython: skipping CPython linking for non-wasm target ({target})");
        return;
    }

    let cpython_dir = env::var("CPYTHON_WASM_DIR").unwrap_or_else(|_| {
        // Default to ~/.config/basilisk/cpython/wasm32-wasip1
        let home = env::var("HOME").unwrap_or_else(|_| "/root".to_string());
        format!("{home}/.config/basilisk/cpython/wasm32-wasip1")
    });

    let cpython_path = PathBuf::from(&cpython_dir);

    let lib_dir = cpython_path.join("lib");
    let include_dir = cpython_path.join("include");

    if !lib_dir.exists() {
        println!(
            "cargo:warning=basilisk_cpython: CPython lib dir not found at {}. \
             Run build_cpython_wasm.sh first.",
            lib_dir.display()
        );
        println!("cargo:warning=basilisk_cpython: Building without CPython linkage (FFI stubs only)");
        // Set a cfg flag so we can conditionally compile stubs
        println!("cargo:rustc-cfg=cpython_stub");
        return;
    }

    if !include_dir.exists() {
        println!(
            "cargo:warning=basilisk_cpython: CPython include dir not found at {}",
            include_dir.display()
        );
        println!("cargo:rustc-cfg=cpython_stub");
        return;
    }

    // Link against the static CPython library
    println!("cargo:rustc-link-search=native={}", lib_dir.display());
    println!("cargo:rustc-link-lib=static=python3.13");

    // WASI emulated libraries that CPython needs
    println!("cargo:rustc-link-lib=wasi-emulated-signal");
    println!("cargo:rustc-link-lib=wasi-emulated-process-clocks");
    println!("cargo:rustc-link-lib=wasi-emulated-mman");
    println!("cargo:rustc-link-lib=wasi-emulated-getpid");

    // Set include path for bindgen or manual FFI
    println!("cargo:include={}", include_dir.display());

    // Re-run if the library changes
    println!("cargo:rerun-if-changed={}", lib_dir.join("libpython3.13.a").display());
    println!("cargo:rerun-if-env-changed=CPYTHON_WASM_DIR");
}
