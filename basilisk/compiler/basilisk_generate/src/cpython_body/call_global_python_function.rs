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
        /// Equivalent to the RustPython version but using CPython C API via basilisk_cpython.
        ///
        /// In the RustPython version:
        /// - Gets function from scope.globals via PyObjectRef
        /// - Calls it with args
        /// - Handles async (generator-based) results via async_result_handler
        /// - Converts result via try_from_vm_value
        ///
        /// In the CPython version:
        /// - Gets function from interpreter globals via PyDict lookup
        /// - Calls it with args packed in a tuple
        /// - Handles async (coroutine) results
        /// - Converts result via TryFromPyObject
        async fn call_global_python_function<'a, T>(
            function_name: &str,
            args: Vec<basilisk_cpython::PyObjectRef>,
        ) -> Result<T, String>
        where
            T: basilisk_cpython::TryFromPyObject,
        {
            let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                .ok_or_else(|| "SystemError: missing python interpreter".to_string())?;

            // Look up the function in globals
            let py_func = interpreter.get_global(function_name)
                .map_err(|e| e.to_rust_err_string())?;

            // Pack args into a tuple for PyObject_Call
            let args_tuple = basilisk_cpython::PyTuple::new(args)
                .map_err(|e| format!("Failed to create args tuple: {}", e.to_rust_err_string()))?;

            // Call the function
            let py_result = py_func.call(&args_tuple.into_object(), None)
                .map_err(|e| e.to_rust_err_string())?;

            // Handle async results (Python coroutines)
            let final_result = cpython_async_result_handler(py_result).await
                .map_err(|e| e.to_rust_err_string())?;

            // Convert Python result to Rust type
            basilisk_cpython::TryFromPyObject::try_from_py_object(final_result)
                .map_err(|e| e.to_rust_err_string())
        }

        /// Call a Python function by name from the global scope (sync version).
        fn call_global_python_function_sync<'a, T>(
            function_name: &str,
            args: Vec<basilisk_cpython::PyObjectRef>,
        ) -> Result<T, String>
        where
            T: basilisk_cpython::TryFromPyObject,
        {
            let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                .ok_or_else(|| "SystemError: missing python interpreter".to_string())?;

            // Look up the function in globals
            let py_func = interpreter.get_global(function_name)
                .map_err(|e| e.to_rust_err_string())?;

            // Pack args into a tuple
            let args_tuple = basilisk_cpython::PyTuple::new(args)
                .map_err(|e| format!("Failed to create args tuple: {}", e.to_rust_err_string()))?;

            // Call the function
            let py_result = py_func.call(&args_tuple.into_object(), None)
                .map_err(|e| e.to_rust_err_string())?;

            // Convert Python result to Rust type
            basilisk_cpython::TryFromPyObject::try_from_py_object(py_result)
                .map_err(|e| e.to_rust_err_string())
        }

        /// Handle Python async results (coroutines/generators).
        ///
        /// In the RustPython version, this is `async_result_handler` which steps through
        /// a Python generator. In CPython, we handle native coroutine objects.
        ///
        /// Python async functions return coroutine objects. We need to drive them
        /// to completion, yielding control back to the IC async runtime as needed.
        async fn cpython_async_result_handler(
            py_object: basilisk_cpython::PyObjectRef,
        ) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
            // Check if the result is a coroutine/generator
            // If not, return it directly
            if !py_object.has_attr("send") {
                return Ok(py_object);
            }

            // Drive the coroutine to completion
            let mut current = py_object;
            loop {
                // Send None to advance the coroutine (equivalent to next())
                let send_method = match current.get_attr("send") {
                    Ok(m) => m,
                    Err(_) => return Ok(current), // Not a coroutine, return as-is
                };

                let none_arg = basilisk_cpython::PyObjectRef::none();
                let args = basilisk_cpython::PyTuple::new(vec![none_arg])
                    .map_err(|e| basilisk_cpython::PyError::new("RuntimeError", &e.to_rust_err_string()))?;

                match send_method.call(&args.into_object(), None) {
                    Ok(yielded_value) => {
                        // The coroutine yielded a value
                        // Check if it's an IC async call that we need to await
                        if yielded_value.has_attr("_basilisk_async_call") {
                            // This is a cross-canister call - await it through IC runtime
                            // The yielded value contains the call details
                            // TODO: Implement IC async call bridging
                            continue;
                        }
                        // Otherwise just continue driving the coroutine
                        continue;
                    }
                    Err(e) => {
                        // StopIteration means the coroutine finished
                        if e.type_name == "StopIteration" {
                            // The return value is in the StopIteration's .value attribute
                            // For now, return None (the actual value extraction needs
                            // CPython-specific StopIteration handling)
                            return Ok(basilisk_cpython::PyObjectRef::none());
                        }
                        // Any other exception is a real error
                        return Err(e);
                    }
                }
            }
        }
    }
}
