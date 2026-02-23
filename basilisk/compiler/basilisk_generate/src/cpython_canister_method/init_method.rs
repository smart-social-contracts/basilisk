//! CPython-specific init method code generation.
//!
//! Replaces `canister_method/init_method/rust.rs` when CPython backend is selected.
//! Generates Rust code that initializes CPython via basilisk_cpython instead of RustPython.

use proc_macro2::TokenStream;
use quote::quote;
use rustpython_parser::ast::{Located, StmtKind};

use crate::{source_map::SourceMapped, Error};

pub fn generate(
    init_function_def_option: Option<&SourceMapped<&Located<StmtKind>>>,
    entry_module_name: &str,
) -> Result<TokenStream, Vec<Error>> {
    let call_to_init_py_function = generate_call_to_py_function(
        &generate_call(&init_function_def_option)?,
    );
    let has_init_function = init_function_def_option.is_some();

    if has_init_function {
        // If there's a user @init function, we must initialize CPython during
        // canister_init. This may be slow but is required for correctness.
        let interpreter_init = generate_interpreter_init();
        let ic_object_init = generate_ic_object_init();
        let code_init = generate_code_init(entry_module_name);
        let save_global_interpreter = generate_save_global_interpreter();
        let randomness = generate_randomness();

        Ok(quote! {
            ic_wasi_polyfill::init(&[], &[]);

            unsafe { ENTRY_MODULE_NAME = #entry_module_name; }

            #interpreter_init
            #ic_object_init
            #code_init
            #save_global_interpreter
            #call_to_init_py_function
            #randomness
        })
    } else {
        // No user @init function: do all CPython init during canister_init.
        // canister_init gets Deterministic Time Slicing (DTS) which allows
        // hundreds of billions of instructions — enough for CPython init.
        // Timer callbacks only get ~40B which is insufficient.
        let interpreter_init = generate_interpreter_init();
        let ic_object_init = generate_ic_object_init();
        let code_init = generate_code_init(entry_module_name);
        let save_global_interpreter = generate_save_global_interpreter();
        let randomness = generate_randomness();

        Ok(quote! {
            ic_wasi_polyfill::init(&[], &[]);

            unsafe { ENTRY_MODULE_NAME = #entry_module_name; }

            #interpreter_init

            #ic_object_init

            #code_init

            #save_global_interpreter
            unsafe { CPYTHON_INIT_DONE = true; }

            #randomness
        })
    }
}

pub fn generate_call(
    function_def_option: &Option<&SourceMapped<&Located<StmtKind>>>,
) -> Result<TokenStream, Vec<Error>> {
    match &function_def_option {
        Some(function_def) => function_def.generate_call_to_py_function(),
        None => Ok(quote!()),
    }
}

pub fn generate_interpreter_init() -> TokenStream {
    quote! {
        // Initialize CPython interpreter (replaces RustPython Interpreter::with_init)
        let interpreter = basilisk_cpython::Interpreter::initialize()
            .unwrap_or_else(|e| panic!("Failed to initialize CPython: {}", e.to_rust_err_string()));
        let scope = interpreter.new_scope();
    }
}

pub fn generate_ic_object_init() -> TokenStream {
    quote! {
        // Create and register the _basilisk_ic CPython extension module.
        // This replaces RustPython's Ic pyclass with a C extension module containing
        // PyCFunction entries for each IC API method.
        let _ic_module = basilisk_ic_create_module()
            .unwrap_or_else(|e| panic!("Failed to create _basilisk_ic module: {}", e.to_rust_err_string()));

        // Also make it accessible as a builtin so Python code can use `_basilisk_ic.method()`
        interpreter.set_global("_basilisk_ic", _ic_module)
            .unwrap_or_else(|e| panic!("Failed to register _basilisk_ic: {}", e.to_rust_err_string()));
    }
}

pub fn generate_code_init(entry_module_name: &str) -> TokenStream {
    // For CPython, user modules aren't registered as frozen modules (no py_freeze!).
    // We register a minimal basilisk shim (no heavy stdlib imports like zlib/hashlib)
    // then execute the user's entry module source directly.
    let source_path = format!("../python_source/{}.py", entry_module_name);
    quote! {
        // Register minimal basilisk runtime shim — only imports sys (builtin).
        // Avoids 'import types' which triggers frozen module loading and hangs on IC.
        interpreter.run_code_string(r#"
import sys
_m = type(sys)("basilisk")
_m.__file__ = "<frozen basilisk>"
_m.int64 = _m.int32 = _m.int16 = _m.int8 = int
_m.nat = _m.nat64 = _m.nat32 = _m.nat16 = _m.nat8 = int
_m.float64 = _m.float32 = float
_m.text = str
_m.blob = bytes
_m.null = None
_m.void = None
_m.Opt = None
_m.Vec = list
_m.Record = dict
_m.Variant = dict
_m.Tuple = tuple
def _dec(_func=None, **kw):
    def _w(f): return f
    return _w(_func) if _func else _w
_m.query = _dec
_m.update = _dec
_m.init = lambda f: f
_m.heartbeat = _dec
_m.pre_upgrade = _dec
_m.post_upgrade = lambda f: f
_m.inspect_message = _dec
_m.canister = lambda c: c
sys.modules["basilisk"] = _m
del _m, _dec
"#)
            .unwrap_or_else(|e| panic!("Failed to register basilisk shim: {}", e.to_rust_err_string()));

        // Execute user's entry module source directly
        const _ENTRY_MODULE_SOURCE: &str = include_str!(#source_path);
        interpreter.run_code_string(_ENTRY_MODULE_SOURCE)
            .unwrap_or_else(|e| panic!("Failed to execute {}: {}", #entry_module_name, e.to_rust_err_string()));
    }
}

pub fn generate_save_global_interpreter() -> TokenStream {
    quote! {
        unsafe {
            INTERPRETER_OPTION = Some(interpreter);
            SCOPE_OPTION = Some(scope);
        };
    }
}

pub fn generate_call_to_py_function(
    call_to_py_function: &TokenStream,
) -> TokenStream {
    quote! {
        {
            let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                .unwrap_or_else(|| panic!("SystemError: missing python interpreter"));

            #call_to_py_function
        }
    }
}

pub fn generate_randomness() -> TokenStream {
    quote! {
        ic_cdk_timers::set_timer(std::time::Duration::from_secs(0), || {
            ic_cdk::spawn(async move {
                let result: ic_cdk::api::call::CallResult<(Vec<u8>,)> = ic_cdk::api::management_canister::main::raw_rand().await;

                match result {
                    Ok((randomness,)) => {
                        let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                            .ok_or_else(|| "SystemError: missing python interpreter".to_string()).unwrap();

                        // Seed Python's random module with IC randomness
                        let seed_code = format!(
                            "import random; random.seed({})",
                            randomness.iter().map(|b| b.to_string()).collect::<Vec<_>>().join(",")
                        );
                        interpreter.run_code_string(&seed_code)
                            .unwrap_or_else(|e| panic!("Failed to seed random: {}", e.to_rust_err_string()));
                    },
                    Err(err) => panic!("{:?}", err)
                };
            });
        });
    }
}
