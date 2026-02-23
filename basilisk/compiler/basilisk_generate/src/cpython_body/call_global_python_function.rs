//! CPython-specific global Python function dispatch.
//!
//! Replaces `body/call_global_python_function.rs` when CPython backend is selected.
//! Uses basilisk_cpython to look up and call Python functions from Rust.

use proc_macro2::TokenStream;
use quote::quote;

pub fn generate() -> TokenStream {
    quote! {
        /// Full CPython init: create interpreter, IC object, import user code.
        fn cpython_init_phase2() {
            let interpreter = basilisk_cpython::Interpreter::initialize()
                .unwrap_or_else(|e| panic!("Failed to create CPython interpreter: {}", e.to_rust_err_string()));
            let scope = interpreter.new_scope();

            let _ic_module = basilisk_ic_create_module()
                .unwrap_or_else(|e| panic!("Failed to create _basilisk_ic module: {}", e.to_rust_err_string()));
            interpreter.set_global("_basilisk_ic", _ic_module)
                .unwrap_or_else(|e| panic!("Failed to register _basilisk_ic: {}", e.to_rust_err_string()));

            let entry_module_name = unsafe { ENTRY_MODULE_NAME };
            interpreter.import_star(entry_module_name)
                .unwrap_or_else(|e| panic!("Failed to import {}: {}", entry_module_name, e.to_rust_err_string()));

            unsafe {
                INTERPRETER_OPTION = Some(interpreter);
                SCOPE_OPTION = Some(scope);
                CPYTHON_INIT_DONE = true;
            }

            // Set up randomness seeding
            ic_cdk_timers::set_timer(std::time::Duration::from_secs(0), || {
                ic_cdk::spawn(async move {
                    let result: ic_cdk::api::call::CallResult<(Vec<u8>,)> = ic_cdk::api::management_canister::main::raw_rand().await;
                    match result {
                        Ok((randomness,)) => {
                            let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                                .ok_or_else(|| "SystemError: missing python interpreter".to_string()).unwrap();
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

        /// Ensure CPython is fully initialized. Called before each method.
        /// With DTS-based init in canister_init, this should always be true.
        fn ensure_cpython_initialized() {
            if unsafe { CPYTHON_INIT_DONE } {
                return;
            }
            panic!("CPython not initialized. This should not happen - canister_init should have completed initialization.");
        }

        /// Call a Python function by name from the global scope (async version).
        ///
        /// Uses basilisk_cpython to look up and call Python functions, then
        /// drives any async results (coroutines/generators) through async_result_handler.
        async fn call_global_python_function<'a, T>(
            function_name: &str,
            args: Vec<basilisk_cpython::PyObjectRef>,
        ) -> Result<T, String>
        where
            basilisk_cpython::PyObjectRef: CdkActTryFromVmValue<T, basilisk_cpython::PyError, ()>,
        {
            ensure_cpython_initialized();

            let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                .ok_or_else(|| "SystemError: missing python interpreter".to_string())?;

            let py_func = interpreter.get_global(function_name)
                .map_err(|e| e.to_rust_err_string())?;

            let args_tuple = basilisk_cpython::PyTuple::new(args)
                .map_err(|e| format!("Failed to create args tuple: {}", e.to_rust_err_string()))?;

            let py_result = py_func.call(&args_tuple.into_object(), None)
                .map_err(|e| e.to_rust_err_string())?;

            // Handle async results (Python coroutines/generators) via the full
            // async_result_handler which also dispatches cross-canister calls
            let final_result = async_result_handler(
                &py_result,
                basilisk_cpython::PyObjectRef::none(),
            ).await
                .map_err(|e| e.to_rust_err_string())?;

            final_result.try_from_vm_value(())
                .map_err(|e| e.to_rust_err_string())
        }

        /// Call a Python function by name from the global scope (sync version).
        /// Used by init/post_upgrade methods which cannot be async.
        fn call_global_python_function_sync<'a, T>(
            function_name: &str,
            args: Vec<basilisk_cpython::PyObjectRef>,
        ) -> Result<T, String>
        where
            basilisk_cpython::PyObjectRef: CdkActTryFromVmValue<T, basilisk_cpython::PyError, ()>,
        {
            ensure_cpython_initialized();

            let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                .ok_or_else(|| "SystemError: missing python interpreter".to_string())?;

            let py_func = interpreter.get_global(function_name)
                .map_err(|e| e.to_rust_err_string())?;

            let args_tuple = basilisk_cpython::PyTuple::new(args)
                .map_err(|e| format!("Failed to create args tuple: {}", e.to_rust_err_string()))?;

            let py_result = py_func.call(&args_tuple.into_object(), None)
                .map_err(|e| e.to_rust_err_string())?;

            py_result.try_from_vm_value(())
                .map_err(|e| e.to_rust_err_string())
        }
    }
}
