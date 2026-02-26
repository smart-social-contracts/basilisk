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

        // Export placeholder functions defined in C so the wasm manipulator
        // can find them by name and patch their bodies at build time.
        for sym in &[
            "python_source_passive_data_size",
            "method_meta_passive_data_size",
            "init_python_source_passive_data",
            "init_method_meta_passive_data",
        ] {
            println!("cargo:rustc-link-arg=--export={sym}");
        }
    }

    // Build a trimmed copy of libpython3.13.a with a custom config.o that
    // only references essential modules. This prevents the linker from pulling
    // in heavy unused modules (_decimal, pyexpat, _elementtree, etc.) that
    // would bloat the wasm beyond the IC's install_code budget.
    // See CPYTHON_MIGRATION_NOTES.md section 7 for details.
    let trimmed_lib = build_trimmed_libpython(&lib_dir, &include_dir);
    println!("cargo:rustc-link-search=native={}", trimmed_lib.parent().unwrap().display());
    println!("cargo:rustc-link-lib=static:+whole-archive=python3.13-trimmed");

    // Link zlib if available (CPython's zlibmodule.o depends on external zlib symbols)
    if lib_dir.join("libz.a").exists() {
        println!("cargo:rustc-link-search=native={}", lib_dir.display());
        println!("cargo:rustc-link-lib=static=z");
    }

    // WASI sysroot library path for emulated libraries
    let wasi_sysroot_lib = find_wasi_sysroot_lib();
    if let Some(ref sysroot_lib) = wasi_sysroot_lib {
        println!("cargo:warning=basilisk_cpython: WASI sysroot lib found at {}", sysroot_lib.display());
        println!("cargo:rustc-link-search=native={}", sysroot_lib.display());
    } else {
        println!("cargo:warning=basilisk_cpython: WASI sysroot lib NOT found! POSIX stubs may be missing.");
        println!("cargo:warning=basilisk_cpython: Set WASI_SDK_PATH to fix this.");
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
    // -fno-lto prevents clang from embedding LLVM bitcode, which would let
    // Rust's cross-language LTO inline the placeholder functions.
    let status = std::process::Command::new(clang)
        .args([
            "-c", &src.to_string_lossy(),
            "-o", &obj_path.to_string_lossy(),
            "-I", &include_dir.to_string_lossy(),
            "-O2",
            "-fno-lto",
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

/// Build a trimmed copy of libpython3.13.a with a custom config.o that only
/// references essential modules, preventing the linker from pulling in unused
/// heavy modules (_decimal, pyexpat, _elementtree, CJK codecs, etc.).
fn build_trimmed_libpython(lib_dir: &std::path::Path, include_dir: &std::path::Path) -> PathBuf {
    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());
    let home = env::var("HOME").unwrap_or_else(|_| "/root".to_string());
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());

    let original_lib = lib_dir.join("libpython3.13.a");
    let trimmed_lib = out_dir.join("libpython3.13-trimmed.a");
    let config_src = manifest_dir.join("src/cpython_config.c");
    let config_obj = out_dir.join("config.o");

    // Find WASI SDK tools
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
    let ar = clang.with_file_name("llvm-ar");

    // 1. Compile custom config.c → config.o
    let status = std::process::Command::new(clang)
        .args([
            "-c", &config_src.to_string_lossy(),
            "-o", &config_obj.to_string_lossy(),
            "-I", &include_dir.to_string_lossy(),
            "-O2",
            "--target=wasm32-wasip1",
            "-D_WASI_EMULATED_SIGNAL",
            "-D_WASI_EMULATED_PROCESS_CLOCKS",
            "-D_WASI_EMULATED_MMAN",
            "-D_WASI_EMULATED_GETPID",
        ])
        .status()
        .expect("Failed to run WASI SDK clang for cpython_config.c");
    assert!(status.success(), "Failed to compile cpython_config.c");

    // 2. Copy the original archive to OUT_DIR
    std::fs::copy(&original_lib, &trimmed_lib)
        .expect("Failed to copy libpython3.13.a to OUT_DIR");

    // 3. Replace config.o in the copy with our custom one
    let status = std::process::Command::new(&ar)
        .args(["r", &trimmed_lib.to_string_lossy(), &config_obj.to_string_lossy()])
        .status()
        .expect("Failed to run llvm-ar to replace config.o");
    assert!(status.success(), "Failed to replace config.o in libpython3.13-trimmed.a");

    // 4. Remove .o files for modules NOT in cpython_config.c.
    //    With +whole-archive these would all be pulled in, bloating the wasm.
    //    See CPYTHON_MIGRATION_NOTES.md section 8 for the full rationale.
    let remove_objects = [
        // --- External library deps (libmpdec, libexpat, HACL*) ---
        "_decimal.o",
        "pyexpat.o",
        "_elementtree.o",
        "Hacl_Hash_MD5.o",
        "Hacl_Hash_SHA1.o",
        "Hacl_Hash_SHA3.o",
        // --- Large unused modules (never in config.c) ---
        "unicodedata.o",
        "_codecs_cn.o",
        "_codecs_hk.o",
        "_codecs_jp.o",
        "_codecs_kr.o",
        "_codecs_tw.o",
        "multibytecodec.o",
        "_datetimemodule.o",
        "_pickle.o",
        "_asynciomodule.o",
        "arraymodule.o",
        "cmathmodule.o",
        "_json.o",
        "_csv.o",
        "_lsprof.o",
        "_opcode.o",
        "_randommodule.o",
        "_statisticsmodule.o",
        "_bisectmodule.o",
        "_heapqmodule.o",
        "_queuemodule.o",
        "_zoneinfo.o",
        "selectmodule.o",
        "socketmodule.o",
        "binascii.o",
        "mathmodule.o",
        "_elementtree.o",       // XML C accelerator
        "_decimal.o",           // decimal C accelerator
        "pyexpat.o",            // expat XML parser
        "blake2b_impl.o",       // blake2b hash implementation
        "blake2s_impl.o",       // blake2s hash implementation
        "blake2module.o",       // blake2 module wrapper
        "_codecs_iso2022.o",    // ISO-2022 codec
        // NOTE: picklebufobject.o must NOT be removed — PyPickleBuffer_Type
        // is in CPython's static_types array; removing it causes type_ready
        // failure → _PyErr_Format infinite recursion → stack overflow.
        // --- Stripped for IC mainnet wasm size reduction (section 8) ---
        // These were previously in config.c but are not essential for
        // Py_Initialize + basic script execution on the IC.
        "timemodule.o",         // time module
        "signalmodule.o",       // _signal (PyInit stub in config.c, internals stubbed)
        "_tracemalloc.o",       // _tracemalloc module
        "faulthandler.o",       // faulthandler (config.faulthandler=0 on WASI, init stubbed)
        "_localemodule.o",      // _locale module
        "_contextvarsmodule.o", // _contextvars module
        "itertoolsmodule.o",    // itertools module
        "symtablemodule.o",     // _symtable module
        "_suggestions.o",       // _suggestions module
        "_sysconfig.o",         // _sysconfig module
        // --- Small non-essential core .o files ---
        "perf_trampoline.o",    // Linux perf support (not available on IC)
        "rotatingtree.o",       // profiling tree (only used by removed _lsprof)
        // --- Safe .o file removals (bisected Feb 26, 2026) ---
        "dynload_shlib.o",      // dlopen-based module loading (N/A on WASI)
        "frozenmain.o",         // Py_FrozenMain (not used by canister)
        "main.o",               // Py_Main / Py_BytesMain (not used by canister)
        "myreadline.o",         // readline (N/A on IC)
        "file_tokenizer.o",     // file-based tokenizer (we use string-based)
        "parking_lot.o",        // thread sync primitives (single-threaded on IC)
        // legacy_tracing.o — DO NOT REMOVE: causes heap OOB (ceval state)
        // --- CJK codecs (not needed on IC) ---
        "_codecs_jp.o",
        "_codecs_kr.o",
        "_codecs_cn.o",
        "_codecs_tw.o",
        "_codecs_hk.o",
        // --- Other non-essential modules ---
        "_statisticsmodule.o",  // _statistics (C accelerator for statistics module)
        "dup2.o",               // dup2 emulation (not needed on WASI)
        // --- Module .o removals with stubs in cpython_config.c ---
        "posixmodule.o",        // posix/os module (457K, stubbed — IC has no POSIX)
        "_operator.o",          // _operator C accelerator (256K, pure Python fallback)
        "_collectionsmodule.o", // _collections C accelerator (265K, pure Python fallback)
        "sre.o",                // _sre regex engine (334K, stubbed)
        "_threadmodule.o",      // _thread module (252K, stubbed — IC is single-threaded)
        // NOTE: Do NOT remove core .o files (hamt.o, crossinterp.o, tracemalloc.o,
        // suggestions.o, odictobject.o) — they are referenced during Py_Initialize
        // and stubbing them causes 'heap out of bounds' traps.
        // NOTE: Do NOT remove picklebufobject.o — core type in static_types.
    ];
    for obj in &remove_objects {
        let status = std::process::Command::new(&ar)
            .args(["d", &trimmed_lib.to_string_lossy(), obj])
            .status()
            .unwrap_or_else(|_| panic!("Failed to run llvm-ar d for {}", obj));
        if !status.success() {
            println!("cargo:warning=basilisk_cpython: Could not remove {} from archive (may not exist)", obj);
        }
    }

    println!("cargo:rerun-if-changed={}", config_src.display());
    println!("cargo:warning=basilisk_cpython: Built trimmed libpython3.13.a with custom config.o");

    trimmed_lib
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
