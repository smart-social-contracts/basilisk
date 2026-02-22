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

    let cpython_path = if let Ok(dir) = env::var("CPYTHON_WASM_DIR") {
        PathBuf::from(dir)
    } else {
        let home = env::var("HOME").unwrap_or_else(|_| "/root".to_string());
        // Check multiple candidate paths
        let candidates = [
            format!("{home}/.config/basilisk/cpython_wasm"),
            format!("{home}/.config/basilisk/cpython/wasm32-wasip1"),
        ];
        candidates
            .iter()
            .map(PathBuf::from)
            .find(|p| p.join("lib/libpython3.13.a").exists())
            .unwrap_or_else(|| PathBuf::from(&candidates[0]))
    };

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

    // Compile C init helper using WASI SDK (correct struct layout for PyConfig)
    let init_helper_src = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap())
        .join("src/cpython_init_helper.c");
    if init_helper_src.exists() {
        compile_c_init_helper(&init_helper_src, &include_dir);
        println!("cargo:rerun-if-changed={}", init_helper_src.display());
    }

    // Link against the static CPython library with whole-archive to ensure
    // ALL object files are included (especially frozen.o with frozen encodings).
    // Without this, lld only pulls in objects that resolve undefined symbols,
    // which may miss frozen module data that's referenced via global tables.
    println!("cargo:rustc-link-search=native={}", lib_dir.display());
    println!("cargo:rustc-link-lib=static:+whole-archive=python3.13");

    // WASI sysroot library path for emulated libraries
    let wasi_sysroot_lib = find_wasi_sysroot_lib();
    if let Some(sysroot_lib) = wasi_sysroot_lib {
        println!("cargo:rustc-link-search=native={}", sysroot_lib.display());
    }

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
    println!("cargo:rerun-if-env-changed=WASI_SDK_PATH");
}

fn compile_c_init_helper(src: &std::path::Path, include_dir: &std::path::Path) {
    let home = env::var("HOME").unwrap_or_else(|_| "/root".to_string());
    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());

    // Find WASI SDK clang
    let clang_candidates = if let Ok(sdk) = env::var("WASI_SDK_PATH") {
        vec![PathBuf::from(&sdk).join("bin/clang")]
    } else {
        vec![
            PathBuf::from(format!("{home}/.local/share/wasi-sdk/bin/clang")),
            PathBuf::from("/opt/wasi-sdk/bin/clang"),
        ]
    };
    let clang = clang_candidates.iter().find(|p| p.exists())
        .expect("WASI SDK clang not found. Set WASI_SDK_PATH.");

    let obj_path = out_dir.join("cpython_init_helper.o");
    let lib_path = out_dir.join("libcpython_init_helper.a");

    // Compile .c → .o
    let status = std::process::Command::new(clang)
        .args([
            "-c", &src.to_string_lossy(),
            "-o", &obj_path.to_string_lossy(),
            "-I", &include_dir.to_string_lossy(),
            "-O2",
            "--target=wasm32-wasip1",
            "-D_WASI_EMULATED_SIGNAL",
            "-D_WASI_EMULATED_PROCESS_CLOCKS",
            "-D_WASI_EMULATED_MMAN",
            "-D_WASI_EMULATED_GETPID",
        ])
        .status()
        .expect("Failed to run WASI SDK clang");
    assert!(status.success(), "Failed to compile cpython_init_helper.c");

    // Find llvm-ar
    let ar = clang.with_file_name("llvm-ar");
    let status = std::process::Command::new(&ar)
        .args(["rcs", &lib_path.to_string_lossy(), &obj_path.to_string_lossy()])
        .status()
        .expect("Failed to run llvm-ar");
    assert!(status.success(), "Failed to create libcpython_init_helper.a");

    println!("cargo:rustc-link-search=native={}", out_dir.display());
    println!("cargo:rustc-link-lib=static=cpython_init_helper");
}

fn find_wasi_sysroot_lib() -> Option<PathBuf> {
    let home = env::var("HOME").unwrap_or_else(|_| "/root".to_string());
    let candidates: Vec<PathBuf> = if let Ok(sdk) = env::var("WASI_SDK_PATH") {
        vec![
            PathBuf::from(&sdk).join("share/wasi-sysroot/lib/wasm32-wasip1"),
            PathBuf::from(&sdk).join("share/wasi-sysroot/lib/wasm32-wasi"),
        ]
    } else {
        vec![
            PathBuf::from(format!("{home}/.local/share/wasi-sdk/share/wasi-sysroot/lib/wasm32-wasip1")),
            PathBuf::from(format!("{home}/.local/share/wasi-sdk/share/wasi-sysroot/lib/wasm32-wasi")),
            PathBuf::from("/opt/wasi-sdk/share/wasi-sysroot/lib/wasm32-wasip1"),
            PathBuf::from("/opt/wasi-sdk/share/wasi-sysroot/lib/wasm32-wasi"),
        ]
    };
    candidates.into_iter().find(|p| p.join("libwasi-emulated-signal.a").exists())
}
