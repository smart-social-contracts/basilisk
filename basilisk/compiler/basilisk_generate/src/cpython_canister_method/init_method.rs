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
    let interpreter_init = generate_interpreter_init();
    let ic_object_init = generate_ic_object_init();
    let code_init = generate_code_init(entry_module_name);
    let save_global_interpreter = generate_save_global_interpreter();
    let call_to_init_py_function = generate_call_to_py_function(
        &generate_call(&init_function_def_option)?,
    );
    let randomness = generate_randomness();

    Ok(quote! {
        ic_wasi_polyfill::init(&[], &[]);

        #interpreter_init

        #ic_object_init

        #code_init

        #save_global_interpreter

        #call_to_init_py_function

        #randomness
    })
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
    quote! {
        // Import user's entry module (replaces vm.run_code_string with format!("from {} import *"))
        interpreter.import_star(#entry_module_name)
            .unwrap_or_else(|e| panic!("Failed to import {}: {}", #entry_module_name, e.to_rust_err_string()));
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
                    Err(err) => panic!(err)
                };
            });
        });
    }
}
