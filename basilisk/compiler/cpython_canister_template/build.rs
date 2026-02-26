fn main() {
    // Export C placeholder functions so the wasm manipulator can find them
    // by name and patch their bodies at build time. These functions are
    // defined in cpython_init_helper.c (compiled by WASI SDK clang),
    // making them immune to Rust's LTO inlining.
    for sym in &[
        "python_source_passive_data_size",
        "method_meta_passive_data_size",
        "init_python_source_passive_data",
        "init_method_meta_passive_data",
    ] {
        println!("cargo:rustc-link-arg=--export={sym}");
    }
}
