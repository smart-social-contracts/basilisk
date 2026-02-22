//! CPython-specific global Python function dispatch.
//!
//! Replaces `body/call_global_python_function.rs` when CPython backend is selected.
//! Uses basilisk_cpython to look up and call Python functions from Rust.

use proc_macro2::TokenStream;
use quote::quote;

pub fn generate() -> TokenStream {
    quote! {
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
