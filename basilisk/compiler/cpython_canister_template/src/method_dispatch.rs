//! Generic method dispatch using dynamic Candid.
//!
//! Instead of generating typed Rust functions per canister method,
//! this module provides a single generic dispatcher that:
//! 1. Reads raw Candid bytes from the IC message
//! 2. Decodes them dynamically using candid::IDLArgs
//! 3. Converts IDLValue arguments to Python objects
//! 4. Calls the named Python function
//! 5. Converts the Python return value back to an IDLValue
//! 6. Encodes and replies with raw Candid bytes

use crate::wasm_data::{MethodInfo, METHOD_METADATA, TYPE_DEFS, LIFECYCLE};
use std::collections::HashMap;

/// Call a user-defined lifecycle hook (init, post_upgrade, pre_upgrade, etc.).
/// Reads the lifecycle metadata from LIFECYCLE global, decodes any Candid init args,
/// and calls the corresponding Python function.
pub fn call_lifecycle_hook(hook_name: &str) {
    let hook_info = unsafe {
        LIFECYCLE
            .as_ref()
            .and_then(|lc| lc.get(hook_name))
    };

    let hook_info = match hook_info {
        Some(info) => info,
        None => return, // No user-defined hook for this lifecycle event
    };

    let function_name = &hook_info.name;

    ensure_cpython_initialized();
    let interpreter = unsafe { crate::INTERPRETER_OPTION.as_mut() }
        .unwrap_or_else(|| {
            ic_cdk::trap("SystemError: missing python interpreter");
        });

    let py_func = interpreter
        .get_global(function_name)
        .unwrap_or_else(|e| {
            ic_cdk::trap(&format!(
                "Lifecycle function '{}' not found: {}",
                function_name,
                e.to_rust_err_string()
            ));
        });

    // Decode init args if the hook takes parameters (e.g. @init with args)
    let args = if !hook_info.params.is_empty() {
        let arg_bytes = ic_cdk::api::call::arg_data_raw();
        decode_candid_args_to_python(&arg_bytes, &hook_info.params)
    } else {
        Vec::new()
    };

    let args_tuple = basilisk_cpython::PyTuple::new(args).unwrap_or_else(|e| {
        ic_cdk::trap(&format!(
            "Failed to create args tuple for '{}': {}",
            function_name,
            e.to_rust_err_string()
        ));
    });

    py_func
        .call(&args_tuple.into_object(), None)
        .unwrap_or_else(|e| {
            ic_cdk::trap(&format!(
                "Error calling lifecycle '{}': {}",
                function_name,
                e.to_rust_err_string()
            ));
        });
}

/// Call a Python function by name with no arguments.
/// Silently returns if CPython is not initialized or the function doesn't exist.
/// Used for internal hooks like _basilisk_save_stable_maps.
pub fn call_python_function(func_name: &str) {
    if !unsafe { crate::CPYTHON_INIT_DONE } {
        return;
    }
    let interpreter = match unsafe { crate::INTERPRETER_OPTION.as_mut() } {
        Some(i) => i,
        None => return,
    };
    let py_func = match interpreter.get_global(func_name) {
        Ok(f) => f,
        Err(_) => return, // Function not found, silently skip
    };
    let empty = basilisk_cpython::PyTuple::new(Vec::new()).unwrap();
    if let Err(e) = py_func.call(&empty.into_object(), None) {
        ic_cdk::println!("Warning: {}() failed: {}", func_name, e.to_rust_err_string());
    }
}

/// Execute a guard function before the main method.
/// Guard functions return a dict: {"Ok": None} to allow, {"Err": "message"} to reject.
/// If the guard throws an exception, the call is rejected with the exception message.
fn execute_guard(guard_name: &str) {
    ensure_cpython_initialized();
    let interpreter = unsafe { crate::INTERPRETER_OPTION.as_mut() }
        .unwrap_or_else(|| {
            ic_cdk::trap("SystemError: missing python interpreter");
        });

    let guard_func = interpreter
        .get_global(guard_name)
        .unwrap_or_else(|e| {
            ic_cdk::trap(&format!(
                "Guard function '{}' not found: {}",
                guard_name,
                e.to_rust_err_string()
            ));
        });

    let empty_args = basilisk_cpython::PyTuple::new(Vec::new()).unwrap_or_else(|e| {
        ic_cdk::trap(&format!(
            "Failed to create empty args: {}",
            e.to_rust_err_string()
        ));
    });

    let result = match guard_func.call(&empty_args.into_object(), None) {
        Ok(r) => r,
        Err(e) => {
            ic_cdk::trap(&format!(
                "Guard function '{}' threw an exception: {}",
                guard_name,
                e.to_rust_err_string()
            ));
        }
    };

    // Guard must return a dict with {"Ok": None} or {"Err": "message"}.
    // Validate the result type and structure, producing Kybra-compatible error messages.

    // Get the Python type name of the result
    let type_name = result.type_name();

    // Check if the result is a dict-like object (has get_item_str capability)
    let has_ok = result.get_item_str("Ok");
    let has_err = result.get_item_str("Err");

    if has_ok.is_err() && has_err.is_err() {
        // Not a dict or doesn't have Ok/Err keys
        ic_cdk::trap(&format!(
            "TypeError: expected Result but received {}",
            type_name
        ));
    }

    // Check for "Err" key first
    if let Ok(err_val) = has_err {
        if !err_val.is_none() {
            // Validate that err value is a string
            match err_val.extract_str() {
                Ok(s) => ic_cdk::trap(&s),
                Err(_) => {
                    let err_type = err_val.type_name();
                    ic_cdk::trap(&format!(
                        "TypeError: Expected type 'str' but '{}' found",
                        err_type
                    ));
                }
            }
        }
    }

    // Check for "Ok" key — if present, validate it's None, then allow the call
    if let Ok(ok_val) = has_ok {
        if ok_val.is_none() {
            return; // Guard passed
        }
        // Ok value must be None
        let ok_type = ok_val.type_name();
        ic_cdk::trap(&format!(
            "TypeError: expected NoneType but received {}",
            ok_type
        ));
    }

    // Neither "Ok" nor "Err" key found in the dict
    ic_cdk::trap(&format!(
        "TypeError: expected Result but received {}",
        type_name
    ));
}

/// Main entry point for canister method execution.
/// Called by execute_query_method / execute_update_method from lib.rs.
pub fn execute_canister_method(method_index: i32, _is_update: bool) {
    let method_info = unsafe {
        METHOD_METADATA
            .as_ref()
            .and_then(|meta| meta.get(method_index as usize))
            .unwrap_or_else(|| {
                ic_cdk::trap(&format!("Invalid method index: {}", method_index));
            })
    };

    let function_name = &method_info.name;

    // Execute guard function if present
    if let Some(guard_name) = &method_info.guard {
        execute_guard(guard_name);
    }

    // Get raw Candid argument bytes from the IC message
    let arg_bytes = ic_cdk::api::call::arg_data_raw();

    // Decode Candid arguments dynamically
    let args = if arg_bytes.len() <= 6 && method_info.params.is_empty() {
        // No arguments expected — common case for simple queries
        Vec::new()
    } else {
        decode_candid_args_to_python(&arg_bytes, &method_info.params)
    };

    // Call the Python function
    ensure_cpython_initialized();

    // Set current return type so ic.reply() can encode properly
    unsafe {
        crate::CURRENT_RETURN_TYPE = Some(method_info.returns.clone());
    }

    let interpreter = unsafe { crate::INTERPRETER_OPTION.as_mut() }
        .unwrap_or_else(|| {
            ic_cdk::trap("SystemError: missing python interpreter");
        });

    let py_func = interpreter
        .get_global(function_name)
        .unwrap_or_else(|e| {
            ic_cdk::trap(&format!(
                "Function '{}' not found: {}",
                function_name,
                e.to_rust_err_string()
            ));
        });

    let args_tuple = basilisk_cpython::PyTuple::new(args).unwrap_or_else(|e| {
        ic_cdk::trap(&format!(
            "Failed to create args tuple: {}",
            e.to_rust_err_string()
        ));
    });

    let py_result = py_func
        .call(&args_tuple.into_object(), None)
        .unwrap_or_else(|e| {
            ic_cdk::trap(&format!(
                "Error calling '{}': {}",
                function_name,
                e.to_rust_err_string()
            ));
        });

    // For async methods (generators), spawn the async driver
    if method_info.is_async {
        let return_type = method_info.returns.clone();
        let manual_reply = method_info.manual_reply;
        let func_name = function_name.clone();
        execute_async_generator(py_result, return_type, manual_reply, func_name);
        return;
    }

    // For Manual[T] methods, the Python function already called ic.reply()
    if method_info.manual_reply {
        return;
    }

    // Encode result back to Candid and reply
    let result_bytes = encode_python_to_candid(&py_result, &method_info.returns);
    ic_cdk::api::call::reply_raw(&result_bytes);
}

/// Drive a Python generator through async cross-canister calls.
/// The generator yields `_ServiceCall` objects which we execute via `ic_cdk::api::call::call_raw`,
/// and we send the results back via `gen.send(result)`. When the generator raises StopIteration,
/// we extract the return value and reply.
fn execute_async_generator(
    generator: basilisk_cpython::PyObjectRef,
    return_type: String,
    manual_reply: bool,
    func_name: String,
) {
    ic_cdk::spawn(async move {
        let result = drive_generator(generator, &func_name).await;

        if manual_reply {
            return;
        }
        let result_bytes = encode_python_to_candid(&result, &return_type);
        ic_cdk::api::call::reply_raw(&result_bytes);
    });
}

/// Recursively drive a Python generator. Handles both _ServiceCall yields (IC calls)
/// and nested generator yields (sub-generators that themselves yield _ServiceCall objects).
/// Returns the generator's return value (from StopIteration.value).
fn drive_generator(
    generator: basilisk_cpython::PyObjectRef,
    func_name: &str,
) -> std::pin::Pin<Box<dyn std::future::Future<Output = basilisk_cpython::PyObjectRef> + 'static>> {
    let func_name = func_name.to_string();
    Box::pin(async move {
        let gen = generator;
        let mut send_value = basilisk_cpython::PyObjectRef::none();

        loop {
            let result = gen.call_method_one_arg("send", &send_value);

            match result {
                Ok(yielded) => {
                    // Check if yielded value is a _ServiceCall (has canister_principal attr)
                    if yielded.has_attr("canister_principal") {
                        // It's a _ServiceCall — make the IC inter-canister call
                        let call_result = perform_service_call(&yielded).await;
                        send_value = match call_result {
                            Ok(raw_bytes) => {
                                let py_val = decode_candid_response_to_python(&raw_bytes);
                                make_python_dict_result("Ok", py_val)
                            }
                            Err((rejection_code, msg)) => {
                                let err_msg = format!("Rejection code {:?}: {}", rejection_code, msg);
                                let py_err = basilisk_cpython::PyObjectRef::from_str(&err_msg)
                                    .unwrap_or_else(|_| basilisk_cpython::PyObjectRef::none());
                                make_python_dict_result("Err", py_err)
                            }
                        };
                    } else if yielded.has_attr("send") {
                        // It's a sub-generator — recursively drive it
                        send_value = drive_generator(yielded, &func_name).await;
                    } else {
                        // Unknown yielded type — pass it through as-is
                        send_value = yielded;
                    }
                }
                Err(e) => {
                    if e.type_name == "StopIteration" {
                        return e.value.unwrap_or_else(basilisk_cpython::PyObjectRef::none);
                    } else {
                        ic_cdk::trap(&format!(
                            "Error in async method '{}': {}",
                            func_name,
                            e.to_rust_err_string()
                        ));
                    }
                }
            }
        }
    })
}

/// Extract fields from a Python _ServiceCall object and make an IC inter-canister call.
async fn perform_service_call(
    service_call: &basilisk_cpython::PyObjectRef,
) -> Result<Vec<u8>, (ic_cdk::api::call::RejectionCode, String)> {
    // Extract canister_principal — a Principal Python object
    let py_principal = service_call
        .get_attr("canister_principal")
        .unwrap_or_else(|e| {
            ic_cdk::trap(&format!("_ServiceCall missing canister_principal: {}", e));
        });

    // Get principal text via .to_str() or ._text
    let principal_text = py_principal
        .get_attr("_text")
        .and_then(|t| t.extract_str())
        .unwrap_or_else(|e| {
            ic_cdk::trap(&format!("Cannot extract principal text: {}", e));
        });

    let ic_principal = candid::Principal::from_text(&principal_text).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Invalid principal '{}': {}", principal_text, e));
    });

    // Extract method_name
    let method_name = service_call
        .get_attr("method_name")
        .and_then(|m| m.extract_str())
        .unwrap_or_else(|e| {
            ic_cdk::trap(&format!("_ServiceCall missing method_name: {}", e));
        });

    // Extract payment (default 0)
    let payment = service_call
        .get_attr("payment")
        .and_then(|p| p.extract_u64())
        .unwrap_or(0u64);

    // Encode args to Candid
    // The args field is a tuple of Python objects — encode them generically
    let args_raw = encode_service_call_args(service_call);

    ic_cdk::api::call::call_raw(ic_principal, &method_name, &args_raw, payment).await
}

/// Encode the args from a _ServiceCall to Candid bytes.
/// If _raw_args is present (from ic.call_raw), use those bytes directly.
/// Otherwise, args is a Python tuple — encode generically.
fn encode_service_call_args(service_call: &basilisk_cpython::PyObjectRef) -> Vec<u8> {
    // Check for pre-encoded raw args (from ic.call_raw / ic.call_raw128)
    if let Ok(raw_args) = service_call.get_attr("_raw_args") {
        if let Ok(bytes) = raw_args.extract_bytes() {
            return bytes;
        }
    }

    let py_args = match service_call.get_attr("args") {
        Ok(a) => a,
        Err(_) => return vec![0x44, 0x49, 0x44, 0x4c, 0x00, 0x00], // DIDL empty
    };

    // Check if args tuple is empty
    let length = unsafe { basilisk_cpython::ffi::PyObject_Length(py_args.as_ptr()) };
    if length <= 0 {
        return vec![0x44, 0x49, 0x44, 0x4c, 0x00, 0x00]; // DIDL empty
    }

    // Convert each Python arg to an IDLValue and encode
    let mut idl_values = Vec::new();
    for i in 0..length {
        let idx = basilisk_cpython::PyObjectRef::from_i64(i as i64).unwrap();
        if let Ok(item) = py_args.get_item(&idx) {
            // Use "text" as fallback type for generic encoding
            if let Ok(val) = python_to_idl_value(&item, "text") {
                idl_values.push(val);
            }
        }
    }

    let idl_args = candid::IDLArgs::new(&idl_values);
    idl_args
        .to_bytes()
        .unwrap_or_else(|_| vec![0x44, 0x49, 0x44, 0x4c, 0x00, 0x00])
}

/// Decode Candid response bytes to a Python object.
/// Returns the first value from the decoded IDLArgs, or None if empty.
fn decode_candid_response_to_python(raw_bytes: &[u8]) -> basilisk_cpython::PyObjectRef {
    if raw_bytes.is_empty() {
        return basilisk_cpython::PyObjectRef::none();
    }
    match candid::IDLArgs::from_bytes(raw_bytes) {
        Ok(idl_args) => {
            if let Some(first_val) = idl_args.args.into_iter().next() {
                idl_value_to_python(&first_val).unwrap_or_else(|_| basilisk_cpython::PyObjectRef::none())
            } else {
                basilisk_cpython::PyObjectRef::none()
            }
        }
        Err(_) => {
            // If we can't decode as Candid, return raw bytes
            basilisk_cpython::PyObjectRef::from_bytes(raw_bytes)
                .unwrap_or_else(|_| basilisk_cpython::PyObjectRef::none())
        }
    }
}

/// Create a Python CallResult instance with Ok or Err.
/// Falls back to a plain dict if the CallResult class isn't available.
fn make_python_dict_result(key: &str, value: basilisk_cpython::PyObjectRef) -> basilisk_cpython::PyObjectRef {
    // Try to create a real CallResult instance
    let interpreter = unsafe { crate::INTERPRETER_OPTION.as_mut() };
    if let Some(interp) = interpreter {
        if let Ok(cls) = interp.get_global("CallResult") {
            let (ok_val, err_val) = if key == "Ok" {
                (value.clone(), basilisk_cpython::PyObjectRef::none())
            } else {
                (basilisk_cpython::PyObjectRef::none(), value.clone())
            };
            // Call CallResult(ok=..., err=...)
            let ok_key = basilisk_cpython::PyObjectRef::from_str("ok").unwrap();
            let err_key = basilisk_cpython::PyObjectRef::from_str("err").unwrap();
            let kwargs = basilisk_cpython::PyDict::new().unwrap();
            let _ = kwargs.set_item(&ok_key, &ok_val);
            let _ = kwargs.set_item(&err_key, &err_val);
            let empty_args = basilisk_cpython::PyTuple::new(Vec::new()).unwrap();
            if let Ok(instance) = cls.call(&empty_args.into_object(), Some(&kwargs.into_object())) {
                return instance;
            }
        }
    }
    // Fallback: plain dict
    let dict = basilisk_cpython::PyDict::new().unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Failed to create dict: {}", e));
    });
    let _ = dict.set_item_str(key, &value);
    dict.into_object()
}

/// Ensure CPython is initialized. Traps if not.
fn ensure_cpython_initialized() {
    if unsafe { crate::CPYTHON_INIT_DONE } {
        return;
    }
    ic_cdk::trap(
        "CPython not initialized. canister_init should have completed initialization.",
    );
}

/// Decode raw Candid bytes into Python objects using dynamic IDLArgs.
/// Uses parameter type info from method metadata to resolve record field hashes
/// back to their original names via TYPE_DEFS.
fn decode_candid_args_to_python(
    arg_bytes: &[u8],
    params: &[crate::wasm_data::ParamInfo],
) -> Vec<basilisk_cpython::PyObjectRef> {
    let idl_args = candid::IDLArgs::from_bytes(arg_bytes).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Failed to decode Candid args: {}", e));
    });

    let type_defs = unsafe { TYPE_DEFS.as_ref() };
    let empty_map = HashMap::new();
    let type_defs = type_defs.unwrap_or(&empty_map);

    idl_args
        .args
        .into_iter()
        .enumerate()
        .map(|(i, idl_value)| {
            let expected_type = params.get(i).map(|p| p.candid_type.as_str());
            idl_value_to_python_typed(&idl_value, expected_type, type_defs)
                .unwrap_or_else(|e| {
                    let param_name = params
                        .get(i)
                        .map(|p| p.name.as_str())
                        .unwrap_or("unknown");
                    ic_cdk::trap(&format!(
                        "Failed to convert arg '{}' to Python: {}",
                        param_name, e
                    ));
                })
        })
        .collect()
}

/// Convert a candid::IDLValue to a Python object (convenience wrapper without type info).
pub fn idl_value_to_python(
    value: &candid::IDLValue,
) -> Result<basilisk_cpython::PyObjectRef, String> {
    let type_defs = unsafe { TYPE_DEFS.as_ref() };
    let empty_map = HashMap::new();
    let type_defs = type_defs.unwrap_or(&empty_map);
    idl_value_to_python_typed(value, None, type_defs)
}

/// Convert a candid::IDLValue to a Python object with type information.
/// When `expected_type` is provided, Record/Variant field hashes are mapped back
/// to their original names using the type definitions, and types are threaded
/// recursively through nested structures.
fn idl_value_to_python_typed(
    value: &candid::IDLValue,
    expected_type: Option<&str>,
    type_defs: &HashMap<String, String>,
) -> Result<basilisk_cpython::PyObjectRef, String> {
    use candid::IDLValue;

    // Resolve named type references (e.g. "ExtensionCallArgs" → "record { ... }")
    let resolved = expected_type.map(|t| resolve_type(t, type_defs));

    match value {
        IDLValue::Null => Ok(basilisk_cpython::PyObjectRef::none()),
        IDLValue::Bool(b) => Ok(basilisk_cpython::PyObjectRef::from_bool(*b)),
        IDLValue::Text(s) => basilisk_cpython::PyObjectRef::from_str(s)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::Nat(n) => {
            let s = n.0.to_string();
            let interpreter = unsafe { crate::INTERPRETER_OPTION.as_mut() }
                .ok_or_else(|| "missing interpreter".to_string())?;
            interpreter
                .eval_expression(&format!("int('{}')", s))
                .map_err(|e| e.to_rust_err_string())
        }
        IDLValue::Int(n) => {
            let s = n.0.to_string();
            let interpreter = unsafe { crate::INTERPRETER_OPTION.as_mut() }
                .ok_or_else(|| "missing interpreter".to_string())?;
            interpreter
                .eval_expression(&format!("int('{}')", s))
                .map_err(|e| e.to_rust_err_string())
        }
        IDLValue::Nat8(n) => basilisk_cpython::PyObjectRef::from_u64(*n as u64)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::Nat16(n) => basilisk_cpython::PyObjectRef::from_u64(*n as u64)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::Nat32(n) => basilisk_cpython::PyObjectRef::from_u64(*n as u64)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::Nat64(n) => basilisk_cpython::PyObjectRef::from_u64(*n)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::Int8(n) => basilisk_cpython::PyObjectRef::from_i64(*n as i64)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::Int16(n) => basilisk_cpython::PyObjectRef::from_i64(*n as i64)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::Int32(n) => basilisk_cpython::PyObjectRef::from_i64(*n as i64)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::Int64(n) => basilisk_cpython::PyObjectRef::from_i64(*n)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::Float32(f) => basilisk_cpython::PyObjectRef::from_f64(*f as f64)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::Float64(f) => basilisk_cpython::PyObjectRef::from_f64(*f)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::Blob(bytes) => basilisk_cpython::PyObjectRef::from_bytes(bytes)
            .map_err(|e| e.to_rust_err_string()),
        IDLValue::None => Ok(basilisk_cpython::PyObjectRef::none()),
        IDLValue::Opt(inner) => {
            let inner_type = resolved.and_then(|r| {
                let r = r.trim();
                if r.starts_with("opt ") { Some(&r[4..]) } else { None }
            });
            idl_value_to_python_typed(inner.as_ref(), inner_type, type_defs)
        }
        IDLValue::Vec(items) => {
            let elem_type = resolved.and_then(|r| {
                let r = r.trim();
                if r.starts_with("vec ") { Some(&r[4..]) } else { None }
            });
            let py_items: Result<Vec<_>, _> =
                items.iter().map(|item| idl_value_to_python_typed(item, elem_type, type_defs)).collect();
            let items = py_items?;
            unsafe {
                let list = basilisk_cpython::ffi::PyList_New(
                    items.len() as basilisk_cpython::ffi::Py_ssize_t,
                );
                if list.is_null() {
                    return Err("Failed to create Python list".to_string());
                }
                for (i, item) in items.into_iter().enumerate() {
                    basilisk_cpython::ffi::PyList_SetItem(
                        list,
                        i as basilisk_cpython::ffi::Py_ssize_t,
                        item.into_ptr(),
                    );
                }
                basilisk_cpython::PyObjectRef::from_owned(list)
                    .ok_or_else(|| "null list".to_string())
            }
        }
        IDLValue::Record(fields) => {
            // Parse field definitions from the expected type (if available)
            let resolved_str = resolved.unwrap_or("");
            let field_defs: Vec<(String, String)> = if let Some(inner) = strip_compound_wrapper(resolved_str, "record") {
                parse_fields(inner)
            } else {
                Vec::new()
            };

            // Build hash → (name, type) map for field-name resolution
            let hash_to_field: HashMap<u32, (String, String)> = field_defs
                .iter()
                .map(|(name, typ)| (candid_field_hash(name), (name.clone(), typ.clone())))
                .collect();

            // Determine if this is a tuple record
            let is_tuple = if !field_defs.is_empty() {
                is_tuple_record(&field_defs)
            } else {
                // Fallback heuristic when no type info: consecutive numeric IDs
                !fields.is_empty()
                    && fields.iter().enumerate().all(|(i, f)| {
                        matches!(&f.id,
                            candid::types::Label::Id(id) | candid::types::Label::Unnamed(id)
                            if *id == i as u32
                        )
                    })
            };

            if is_tuple {
                let py_items: Result<Vec<_>, _> = fields
                    .iter()
                    .enumerate()
                    .map(|(i, f)| {
                        let ft = field_defs.get(i).map(|(_, t)| t.as_str());
                        idl_value_to_python_typed(&f.val, ft, type_defs)
                    })
                    .collect();
                let items = py_items?;
                let tuple = basilisk_cpython::PyTuple::new(items)
                    .map_err(|e| e.to_rust_err_string())?;
                Ok(tuple.into_object())
            } else {
                let dict = basilisk_cpython::PyDict::new()
                    .map_err(|e| e.to_rust_err_string())?;
                for field in fields {
                    let (key, field_type): (String, Option<&str>) = match &field.id {
                        candid::types::Label::Named(name) => {
                            let ft = hash_to_field.get(&candid_field_hash(name))
                                .map(|(_, t)| t.as_str());
                            // Add back keyword underscore for Python dict key
                            (add_keyword_underscore(name), ft)
                        }
                        candid::types::Label::Id(id) | candid::types::Label::Unnamed(id) => {
                            if let Some((name, typ)) = hash_to_field.get(id) {
                                (add_keyword_underscore(name), Some(typ.as_str()))
                            } else {
                                (format!("_{}", id), None)
                            }
                        }
                    };
                    let value = idl_value_to_python_typed(&field.val, field_type, type_defs)?;
                    dict.set_item_str(&key, &value)
                        .map_err(|e| e.to_rust_err_string())?;
                }
                Ok(dict.into_object())
            }
        }
        IDLValue::Variant(variant) => {
            // Parse case definitions from the expected type
            let resolved_str = resolved.unwrap_or("");
            let case_defs: Vec<(String, String)> = if let Some(inner) = strip_compound_wrapper(resolved_str, "variant") {
                parse_fields(inner)
            } else {
                Vec::new()
            };
            let hash_to_case: HashMap<u32, (String, String)> = case_defs
                .into_iter()
                .map(|(name, typ)| (candid_field_hash(&name), (name, typ)))
                .collect();

            let dict = basilisk_cpython::PyDict::new()
                .map_err(|e| e.to_rust_err_string())?;
            let (key, case_type) = match &variant.0.id {
                candid::types::Label::Named(name) => {
                    let ct = hash_to_case.get(&candid_field_hash(name))
                        .map(|(_, t)| t.clone());
                    // Add back keyword underscore for Python dict key
                    (add_keyword_underscore(name), ct)
                }
                candid::types::Label::Id(id) | candid::types::Label::Unnamed(id) => {
                    if let Some((name, typ)) = hash_to_case.get(id) {
                        (add_keyword_underscore(name), Some(typ.clone()))
                    } else {
                        (format!("_{}", id), None)
                    }
                }
            };
            let value = idl_value_to_python_typed(
                &variant.0.val, case_type.as_deref(), type_defs
            )?;
            dict.set_item_str(&key, &value)
                .map_err(|e| e.to_rust_err_string())?;
            Ok(dict.into_object())
        }
        IDLValue::Principal(p) => {
            let text = p.to_text();
            let principal_class = unsafe { crate::PRINCIPAL_CLASS_OPTION.as_ref() }
                .ok_or_else(|| "Principal class not cached".to_string())?;
            let from_str = principal_class
                .get_attr("from_str")
                .map_err(|e| e.to_rust_err_string())?;
            let text_obj = basilisk_cpython::PyObjectRef::from_str(&text)
                .map_err(|e| e.to_rust_err_string())?;
            let args = basilisk_cpython::PyTuple::new(vec![text_obj])
                .map_err(|e| e.to_rust_err_string())?;
            from_str
                .call(&args.into_object(), None)
                .map_err(|e| e.to_rust_err_string())
        }
        IDLValue::Service(p) => {
            // Service → Python Principal object
            let text = p.to_text();
            let principal_class = unsafe { crate::PRINCIPAL_CLASS_OPTION.as_ref() }
                .ok_or_else(|| "Principal class not cached".to_string())?;
            let from_str = principal_class
                .get_attr("from_str")
                .map_err(|e| e.to_rust_err_string())?;
            let text_obj = basilisk_cpython::PyObjectRef::from_str(&text)
                .map_err(|e| e.to_rust_err_string())?;
            let args = basilisk_cpython::PyTuple::new(vec![text_obj])
                .map_err(|e| e.to_rust_err_string())?;
            from_str
                .call(&args.into_object(), None)
                .map_err(|e| e.to_rust_err_string())
        }
        IDLValue::Func(p, method) => {
            // Func → Python tuple (Principal, method_name_str)
            let text = p.to_text();
            let principal_class = unsafe { crate::PRINCIPAL_CLASS_OPTION.as_ref() }
                .ok_or_else(|| "Principal class not cached".to_string())?;
            let from_str = principal_class
                .get_attr("from_str")
                .map_err(|e| e.to_rust_err_string())?;
            let text_obj = basilisk_cpython::PyObjectRef::from_str(&text)
                .map_err(|e| e.to_rust_err_string())?;
            let args = basilisk_cpython::PyTuple::new(vec![text_obj])
                .map_err(|e| e.to_rust_err_string())?;
            let principal_py = from_str
                .call(&args.into_object(), None)
                .map_err(|e| e.to_rust_err_string())?;
            let method_py = basilisk_cpython::PyObjectRef::from_str(method)
                .map_err(|e| e.to_rust_err_string())?;
            let tuple = basilisk_cpython::PyTuple::new(vec![principal_py, method_py])
                .map_err(|e| e.to_rust_err_string())?;
            Ok(tuple.into_object())
        }
        _ => {
            // Fallback: convert to string representation
            let s = format!("{:?}", value);
            basilisk_cpython::PyObjectRef::from_str(&s)
                .map_err(|e| e.to_rust_err_string())
        }
    }
}

/// Convert a Python object to Candid bytes based on the expected return type.
pub fn encode_python_to_candid(
    py_result: &basilisk_cpython::PyObjectRef,
    return_type: &str,
) -> Vec<u8> {
    // For void (empty return type), encode zero Candid args.
    // The .did declares () -> () so the agent expects no return values.
    if return_type.is_empty() {
        let idl_args = candid::IDLArgs::new(&[]);
        return idl_args.to_bytes().unwrap_or_else(|e| {
            ic_cdk::trap(&format!("Failed to encode void Candid result: {}", e));
        });
    }

    let idl_value = python_to_idl_value(py_result, return_type).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Failed to convert Python result to Candid: {}", e));
    });

    let idl_args = candid::IDLArgs::new(&[idl_value]);

    // Try typed serialization first — this correctly handles vecs of mixed
    // variants by providing the full type to annotate_type which fixes
    // variant indices.
    let type_defs = unsafe { TYPE_DEFS.as_ref() }.map(|m| m.clone()).unwrap_or_default();
    if let Some(candid_type) = type_str_to_candid_type(return_type, &type_defs) {
        let env = candid::TypeEnv::new();
        if let Ok(bytes) = idl_args.to_bytes_with_types(&env, &[candid_type]) {
            return bytes;
        }
    }

    // Fallback to untyped serialization (works for simple types / single variants)
    idl_args.to_bytes().unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Failed to encode Candid result: {}", e));
    })
}

/// Convert a Candid type string into a `candid::types::Type` for typed serialization.
/// Returns None for types that cannot be represented (func, service, etc.).
fn type_str_to_candid_type(
    type_str: &str,
    type_defs: &HashMap<String, String>,
) -> Option<candid::types::Type> {
    let resolved = resolve_type(type_str, type_defs);
    use candid::types::internal::{TypeInner, Field};
    let ty: candid::types::Type = match resolved {
        "" | "null" => TypeInner::Null.into(),
        "bool" => TypeInner::Bool.into(),
        "nat" => TypeInner::Nat.into(),
        "int" => TypeInner::Int.into(),
        "nat8" => TypeInner::Nat8.into(),
        "nat16" => TypeInner::Nat16.into(),
        "nat32" => TypeInner::Nat32.into(),
        "nat64" => TypeInner::Nat64.into(),
        "int8" => TypeInner::Int8.into(),
        "int16" => TypeInner::Int16.into(),
        "int32" => TypeInner::Int32.into(),
        "int64" => TypeInner::Int64.into(),
        "float32" => TypeInner::Float32.into(),
        "float64" => TypeInner::Float64.into(),
        "text" => TypeInner::Text.into(),
        "blob" => TypeInner::Vec(TypeInner::Nat8.into()).into(),
        "principal" => TypeInner::Principal.into(),
        "empty" => TypeInner::Empty.into(),
        "reserved" => TypeInner::Reserved.into(),
        s if s.starts_with("opt ") => {
            let inner = type_str_to_candid_type(&s[4..], type_defs)?;
            TypeInner::Opt(inner).into()
        }
        s if s.starts_with("vec ") => {
            let inner = type_str_to_candid_type(&s[4..], type_defs)?;
            TypeInner::Vec(inner).into()
        }
        s => {
            if let Some(inner) = strip_compound_wrapper(s, "record") {
                let fields = parse_fields(inner);
                let candid_fields: Vec<Field> = fields.iter().map(|(name, ty)| {
                    Field {
                        id: std::rc::Rc::new(field_name_to_label(name)),
                        ty: type_str_to_candid_type(ty, type_defs)
                            .unwrap_or_else(|| TypeInner::Reserved.into()),
                    }
                }).collect();
                TypeInner::Record(candid_fields).into()
            } else if let Some(inner) = strip_compound_wrapper(s, "variant") {
                let cases = parse_fields(inner);
                let candid_fields: Vec<Field> = cases.iter().map(|(name, ty)| {
                    Field {
                        id: std::rc::Rc::new(field_name_to_label(name)),
                        ty: type_str_to_candid_type(ty, type_defs)
                            .unwrap_or_else(|| TypeInner::Null.into()),
                    }
                }).collect();
                TypeInner::Variant(candid_fields).into()
            } else if s.starts_with("func ") || s.starts_with("service ") {
                return None; // Cannot represent func/service types easily
            } else {
                return None; // Unknown type
            }
        }
    };
    Some(ty)
}

// ─── Candid type string parsing ──────────────────────────────────────────────

/// Resolve a Candid type string, expanding named type references via TYPE_DEFS.
fn resolve_type<'a>(candid_type: &'a str, type_defs: &'a HashMap<String, String>) -> &'a str {
    let trimmed = candid_type.trim();
    // If it's a named type reference, look it up
    if !trimmed.starts_with("record")
        && !trimmed.starts_with("variant")
        && !trimmed.starts_with("opt ")
        && !trimmed.starts_with("vec ")
        && !trimmed.contains(' ')
        && !trimmed.contains('{')
    {
        if let Some(def) = type_defs.get(trimmed) {
            return def.as_str();
        }
    }
    trimmed
}

/// Parse field definitions from inside `record { ... }` or `variant { ... }`.
/// Returns a list of (field_name, field_type_string) pairs.
fn parse_fields(inner: &str) -> Vec<(String, String)> {
    let mut fields = Vec::new();
    let mut depth = 0;
    let mut current = String::new();

    for ch in inner.chars() {
        match ch {
            '{' => {
                depth += 1;
                current.push(ch);
            }
            '}' => {
                depth -= 1;
                current.push(ch);
            }
            ';' if depth == 0 => {
                let trimmed = current.trim().to_string();
                if !trimmed.is_empty() {
                    fields.push(trimmed);
                }
                current.clear();
            }
            _ => {
                current.push(ch);
            }
        }
    }
    let trimmed = current.trim().to_string();
    if !trimmed.is_empty() {
        fields.push(trimmed);
    }

    fields
        .iter()
        .map(|f| {
            if let Some(colon_pos) = f.find(':') {
                let raw_name = f[..colon_pos].trim();
                // Strip surrounding double quotes from Candid reserved-word field names
                let name = if raw_name.starts_with('"') && raw_name.ends_with('"') && raw_name.len() >= 2 {
                    raw_name[1..raw_name.len() - 1].to_string()
                } else {
                    raw_name.to_string()
                };
                let type_str = f[colon_pos + 1..].trim().to_string();
                (name, type_str)
            } else {
                (f.clone(), "null".to_string())
            }
        })
        .collect()
}

/// Strip the outer `record { ... }` or `variant { ... }` wrapper and return the inner content.
fn strip_compound_wrapper<'a>(type_str: &'a str, keyword: &str) -> Option<&'a str> {
    let trimmed = type_str.trim();
    if !trimmed.starts_with(keyword) {
        return None;
    }
    let rest = trimmed[keyword.len()..].trim();
    if rest.starts_with('{') && rest.ends_with('}') {
        Some(&rest[1..rest.len() - 1])
    } else {
        None
    }
}

const PY_KEYWORDS: &[&str] = &[
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else",
    "except", "finally", "for", "from", "global", "if", "import",
    "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise",
    "return", "try", "while", "with", "yield",
];

/// Strip trailing underscore from Python keyword-escaped field names.
/// E.g. "False_" → "False", "from_" → "from", "with__" → "with_",
/// but "my_field_" stays unchanged.
/// Rule: strip one _ if the base matches <keyword>_* (keyword + zero or more underscores).
fn strip_keyword_underscore(name: &str) -> &str {
    if name.ends_with('_') && name.len() > 1 {
        let base = &name[..name.len() - 1];
        for kw in PY_KEYWORDS {
            if base == *kw || (base.starts_with(kw) && base[kw.len()..].chars().all(|c| c == '_')) {
                return base;
            }
        }
    }
    name
}

/// Add trailing underscore to Python keywords for use as Python dict keys.
/// E.g. "False" → "False_", "from" → "from_", "with_" → "with__",
/// but "name" stays unchanged.
/// Rule: add _ if name matches <keyword>_* (keyword + zero or more underscores).
fn add_keyword_underscore(name: &str) -> String {
    for kw in PY_KEYWORDS {
        if name == *kw || (name.starts_with(kw) && name[kw.len()..].chars().all(|c| c == '_')) {
            return format!("{}_", name);
        }
    }
    name.to_string()
}

/// Convert a field name to a Candid Label.
/// Names matching `_N_` pattern or plain numeric names become numeric Label::Id(N).
/// Trailing underscores on Python keywords are stripped (e.g. "False_" → "False").
fn field_name_to_label(name: &str) -> candid::types::Label {
    if name.starts_with('_') && name.ends_with('_') && name.len() > 2 {
        if let Ok(id) = name[1..name.len() - 1].parse::<u32>() {
            return candid::types::Label::Id(id);
        }
    }
    // Also handle plain numeric field names (e.g. "0", "1")
    if let Ok(id) = name.parse::<u32>() {
        return candid::types::Label::Id(id);
    }
    let clean = strip_keyword_underscore(name);
    candid::types::Label::Named(clean.to_string())
}

/// Check if a record type string represents a tuple (all fields are positional: _0_, _1_, ...).
fn is_tuple_record(fields: &[(String, String)]) -> bool {
    if fields.is_empty() {
        return false;
    }
    fields.iter().enumerate().all(|(i, (name, _))| {
        // Check _N_ pattern (e.g. _0_, _1_)
        let is_underscore = name.starts_with('_')
            && name.ends_with('_')
            && name.len() > 2
            && name[1..name.len() - 1].parse::<u32>().ok() == Some(i as u32);
        // Also check plain numeric field names (e.g. "0", "1")
        let is_plain_numeric = name.parse::<u32>().ok() == Some(i as u32);
        is_underscore || is_plain_numeric
    })
}

/// Compute the Candid field-name hash (same algorithm as the candid crate).
fn candid_field_hash(name: &str) -> u32 {
    let mut hash: u32 = 0;
    for b in name.bytes() {
        hash = hash.wrapping_mul(223).wrapping_add(b as u32);
    }
    hash
}

// ─── Python → Candid conversion ─────────────────────────────────────────────

/// Convert a Python object to a candid::IDLValue based on the type string.
/// Supports named type references (resolved via TYPE_DEFS), records, variants,
/// tuples, opt, vec, and all primitive types.
fn python_to_idl_value(
    obj: &basilisk_cpython::PyObjectRef,
    candid_type: &str,
) -> Result<candid::IDLValue, String> {
    let type_defs = unsafe { TYPE_DEFS.as_ref() };
    let empty_map = HashMap::new();
    let type_defs = type_defs.unwrap_or(&empty_map);

    python_to_idl_value_inner(obj, candid_type, type_defs)
}

fn python_to_idl_value_inner(
    obj: &basilisk_cpython::PyObjectRef,
    candid_type: &str,
    type_defs: &HashMap<String, String>,
) -> Result<candid::IDLValue, String> {
    // First resolve named type references
    let resolved = resolve_type(candid_type, type_defs);

    // Check for record { ... }
    if let Some(inner) = strip_compound_wrapper(resolved, "record") {
        let fields = parse_fields(inner);
        let is_tuple = is_tuple_record(&fields);

        if is_tuple {
            // Python tuple → positional Candid record
            return python_tuple_to_record(obj, &fields, type_defs);
        } else {
            // Python dict → named Candid record
            return python_dict_to_record(obj, &fields, type_defs);
        }
    }

    // Check for variant { ... }
    if let Some(inner) = strip_compound_wrapper(resolved, "variant") {
        let cases = parse_fields(inner);
        return python_dict_to_variant(obj, &cases, type_defs);
    }

    // Primitive and compound types
    match resolved {
        "" | "null" => Ok(candid::IDLValue::Null),
        "bool" => Ok(candid::IDLValue::Bool(obj.extract_bool())),
        "text" => {
            let s = obj.extract_str().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Text(s))
        }
        "nat" => {
            let s = obj.str_repr().map_err(|e| e.to_rust_err_string())?;
            let n: num_bigint::BigUint =
                s.parse().map_err(|e| format!("parse nat: {}", e))?;
            Ok(candid::IDLValue::Nat(candid::Nat(n)))
        }
        "int" => {
            let s = obj.str_repr().map_err(|e| e.to_rust_err_string())?;
            let n: num_bigint::BigInt =
                s.parse().map_err(|e| format!("parse int: {}", e))?;
            Ok(candid::IDLValue::Int(candid::Int(n)))
        }
        "nat8" => {
            let v = obj.extract_u64().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Nat8(v as u8))
        }
        "nat16" => {
            let v = obj.extract_u64().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Nat16(v as u16))
        }
        "nat32" => {
            let v = obj.extract_u64().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Nat32(v as u32))
        }
        "nat64" => {
            let v = obj.extract_u64().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Nat64(v))
        }
        "int8" => {
            let v = obj.extract_i64().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Int8(v as i8))
        }
        "int16" => {
            let v = obj.extract_i64().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Int16(v as i16))
        }
        "int32" => {
            let v = obj.extract_i64().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Int32(v as i32))
        }
        "int64" => {
            let v = obj.extract_i64().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Int64(v))
        }
        "float32" => {
            let v = obj.extract_f64().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Float32(v as f32))
        }
        "float64" => {
            let v = obj.extract_f64().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Float64(v))
        }
        "blob" => {
            let bytes = obj.extract_bytes().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Blob(bytes))
        }
        "principal" => {
            let to_str = obj.get_attr("to_str").map_err(|e| e.to_rust_err_string())?;
            let args = basilisk_cpython::PyTuple::empty()
                .map_err(|e| e.to_rust_err_string())?;
            let result = to_str
                .call(&args.into_object(), None)
                .map_err(|e| e.to_rust_err_string())?;
            let text = result.extract_str().map_err(|e| e.to_rust_err_string())?;
            let p = candid::Principal::from_text(&text)
                .map_err(|e| format!("invalid principal: {}", e))?;
            Ok(candid::IDLValue::Principal(p))
        }
        "empty" => Ok(candid::IDLValue::Null),
        "reserved" => Ok(candid::IDLValue::Reserved),
        other if other.starts_with("func ") => {
            // Func type: Python tuple (Principal, method_name_str)
            unsafe {
                let len = basilisk_cpython::ffi::PySequence_Length(obj.as_ptr());
                if len != 2 {
                    return Err(format!("func value must be a 2-tuple (principal, method), got length {}", len));
                }
                let principal_obj = basilisk_cpython::ffi::PySequence_GetItem(obj.as_ptr(), 0);
                if principal_obj.is_null() {
                    return Err("func: null principal".to_string());
                }
                let principal_py = basilisk_cpython::PyObjectRef::from_owned(principal_obj)
                    .ok_or_else(|| "func: null principal obj".to_string())?;
                let to_str = principal_py.get_attr("to_str").map_err(|e| e.to_rust_err_string())?;
                let empty_args = basilisk_cpython::PyTuple::empty().map_err(|e| e.to_rust_err_string())?;
                let principal_text = to_str.call(&empty_args.into_object(), None)
                    .map_err(|e| e.to_rust_err_string())?;
                let text = principal_text.extract_str().map_err(|e| e.to_rust_err_string())?;
                let p = candid::Principal::from_text(&text)
                    .map_err(|e| format!("func principal: {}", e))?;

                let method_obj = basilisk_cpython::ffi::PySequence_GetItem(obj.as_ptr(), 1);
                if method_obj.is_null() {
                    return Err("func: null method name".to_string());
                }
                let method_py = basilisk_cpython::PyObjectRef::from_owned(method_obj)
                    .ok_or_else(|| "func: null method obj".to_string())?;
                let method_name = method_py.extract_str().map_err(|e| e.to_rust_err_string())?;

                Ok(candid::IDLValue::Func(p, method_name))
            }
        }
        other if other.starts_with("opt ") => {
            if obj.is_none() {
                Ok(candid::IDLValue::None)
            } else {
                let inner_type = &other[4..];
                let inner = python_to_idl_value_inner(obj, inner_type, type_defs)?;
                Ok(candid::IDLValue::Opt(Box::new(inner)))
            }
        }
        other if other.starts_with("vec ") => {
            let inner_type = &other[4..];
            unsafe {
                let len = basilisk_cpython::ffi::PySequence_Length(obj.as_ptr());
                if len < 0 {
                    return Err("not a sequence".to_string());
                }
                let mut items = Vec::with_capacity(len as usize);
                for i in 0..len {
                    let item = basilisk_cpython::ffi::PySequence_GetItem(obj.as_ptr(), i);
                    if item.is_null() {
                        return Err(format!("null item at index {}", i));
                    }
                    let py_obj = basilisk_cpython::PyObjectRef::from_owned(item)
                        .ok_or_else(|| "null item".to_string())?;
                    items.push(python_to_idl_value_inner(&py_obj, inner_type, type_defs)?);
                }
                Ok(candid::IDLValue::Vec(items))
            }
        }
        other if other.starts_with("service ") => {
            // Service type: extract principal via to_str(), _principal attr, or plain string
            let text = if let Ok(to_str) = obj.get_attr("to_str") {
                let empty_args = basilisk_cpython::PyTuple::empty()
                    .map_err(|e| e.to_rust_err_string())?;
                let result = to_str.call(&empty_args.into_object(), None)
                    .map_err(|e| e.to_rust_err_string())?;
                result.extract_str().map_err(|e| e.to_rust_err_string())?
            } else if let Ok(principal_attr) = obj.get_attr("_principal") {
                let to_str = principal_attr.get_attr("to_str")
                    .map_err(|e| e.to_rust_err_string())?;
                let empty_args = basilisk_cpython::PyTuple::empty()
                    .map_err(|e| e.to_rust_err_string())?;
                let result = to_str.call(&empty_args.into_object(), None)
                    .map_err(|e| e.to_rust_err_string())?;
                result.extract_str().map_err(|e| e.to_rust_err_string())?
            } else {
                // Fallback: try as plain string (principal text)
                obj.extract_str().map_err(|e| {
                    format!("service: expected Principal object or string, got: {}", e.to_rust_err_string())
                })?
            };
            let p = candid::Principal::from_text(&text)
                .map_err(|e| format!("service principal: {}", e))?;
            Ok(candid::IDLValue::Service(p))
        }
        _ => {
            // Fallback: try str_repr for display, then extract_str for actual string
            let s = obj.extract_str().map_err(|e| {
                format!("Cannot convert Python object to Candid type '{}': {}", resolved, e.to_rust_err_string())
            })?;
            Ok(candid::IDLValue::Text(s))
        }
    }
}

/// Convert a Python dict to a Candid Record.
fn python_dict_to_record(
    obj: &basilisk_cpython::PyObjectRef,
    fields: &[(String, String)],
    type_defs: &HashMap<String, String>,
) -> Result<candid::IDLValue, String> {
    let mut idl_fields = Vec::with_capacity(fields.len());

    for (field_name, field_type) in fields {
        // Try the Candid field name first, then the Python keyword-escaped version
        let py_key = add_keyword_underscore(field_name);
        let key = basilisk_cpython::PyObjectRef::from_str(&py_key)
            .map_err(|e| e.to_rust_err_string())?;
        let value = unsafe {
            let item = basilisk_cpython::ffi::PyObject_GetItem(obj.as_ptr(), key.as_ptr());
            if item.is_null() {
                basilisk_cpython::ffi::PyErr_Clear();
                // Fallback: try the original Candid field name
                let key2 = basilisk_cpython::PyObjectRef::from_str(field_name)
                    .map_err(|e| e.to_rust_err_string())?;
                let item2 = basilisk_cpython::ffi::PyObject_GetItem(obj.as_ptr(), key2.as_ptr());
                if item2.is_null() {
                    basilisk_cpython::ffi::PyErr_Clear();
                    return Err(format!("Record field '{}' not found in Python dict", field_name));
                }
                basilisk_cpython::PyObjectRef::from_owned(item2)
                    .ok_or_else(|| format!("null value for field '{}'", field_name))?
            } else {
                basilisk_cpython::PyObjectRef::from_owned(item)
                    .ok_or_else(|| format!("null value for field '{}'", field_name))?
            }
        };

        let idl_val = python_to_idl_value_inner(&value, field_type, type_defs)?;
        idl_fields.push(candid::types::value::IDLField {
            id: field_name_to_label(field_name),
            val: idl_val,
        });
    }

    // Sort fields by label hash as required by Candid
    idl_fields.sort_by(|a, b| a.id.get_id().cmp(&b.id.get_id()));
    Ok(candid::IDLValue::Record(idl_fields))
}

/// Convert a Python tuple to a positional Candid Record (tuple encoding).
fn python_tuple_to_record(
    obj: &basilisk_cpython::PyObjectRef,
    fields: &[(String, String)],
    type_defs: &HashMap<String, String>,
) -> Result<candid::IDLValue, String> {
    let mut idl_fields = Vec::with_capacity(fields.len());

    for (i, (_field_name, field_type)) in fields.iter().enumerate() {
        let value = unsafe {
            let item = basilisk_cpython::ffi::PySequence_GetItem(
                obj.as_ptr(),
                i as basilisk_cpython::ffi::Py_ssize_t,
            );
            if item.is_null() {
                basilisk_cpython::ffi::PyErr_Clear();
                return Err(format!(
                    "Tuple element {} not found (expected {} elements)",
                    i,
                    fields.len()
                ));
            }
            basilisk_cpython::PyObjectRef::from_owned(item)
                .ok_or_else(|| format!("null tuple element {}", i))?
        };

        let idl_val = python_to_idl_value_inner(&value, field_type, type_defs)?;
        idl_fields.push(candid::types::value::IDLField {
            id: candid::types::Label::Id(i as u32),
            val: idl_val,
        });
    }

    Ok(candid::IDLValue::Record(idl_fields))
}

/// Convert a Python dict (single key) to a Candid Variant.
fn python_dict_to_variant(
    obj: &basilisk_cpython::PyObjectRef,
    cases: &[(String, String)],
    type_defs: &HashMap<String, String>,
) -> Result<candid::IDLValue, String> {
    // Get the keys of the dict to find which variant case is active
    let keys = unsafe {
        let keys_obj = basilisk_cpython::ffi::PyDict_Keys(obj.as_ptr());
        if keys_obj.is_null() {
            return Err("Variant value is not a dict".to_string());
        }
        let len = basilisk_cpython::ffi::PyList_Size(keys_obj);
        if len != 1 {
            basilisk_cpython::ffi::Py_DecRef(keys_obj);
            return Err(format!(
                "Variant dict should have exactly 1 key, got {}",
                len
            ));
        }
        let key = basilisk_cpython::ffi::PyList_GetItem(keys_obj, 0); // borrowed ref
        let key_obj = basilisk_cpython::PyObjectRef::from_borrowed(key)
            .ok_or_else(|| "null variant key".to_string())?;
        let key_str = key_obj.extract_str().map_err(|e| e.to_rust_err_string())?;
        basilisk_cpython::ffi::Py_DecRef(keys_obj);
        key_str
    };

    // Find the matching case and its type
    // Strip keyword underscore from Python key (e.g. "False_" -> "False")
    let clean_key = strip_keyword_underscore(&keys);
    let (case_idx, case_type) = cases
        .iter()
        .enumerate()
        .find(|(_, (name, _))| *name == clean_key || *name == keys)
        .map(|(i, (_, t))| (i, t.as_str()))
        .ok_or_else(|| format!("Unknown variant case '{}'", keys))?;

    // Get the value for this case
    let key = basilisk_cpython::PyObjectRef::from_str(&keys)
        .map_err(|e| e.to_rust_err_string())?;
    let value = unsafe {
        let item = basilisk_cpython::ffi::PyObject_GetItem(obj.as_ptr(), key.as_ptr());
        if item.is_null() {
            basilisk_cpython::ffi::PyErr_Clear();
            return Err(format!("Variant value for '{}' is null", keys));
        }
        basilisk_cpython::PyObjectRef::from_owned(item)
            .ok_or_else(|| "null variant value".to_string())?
    };

    let idl_val = if value.is_none() && case_type == "null" {
        candid::IDLValue::Null
    } else {
        python_to_idl_value_inner(&value, case_type, type_defs)?
    };

    let field = candid::types::value::IDLField {
        id: field_name_to_label(&clean_key),
        val: idl_val,
    };

    Ok(candid::IDLValue::Variant(candid::types::value::VariantValue(Box::new(field), 0u64)))
}
