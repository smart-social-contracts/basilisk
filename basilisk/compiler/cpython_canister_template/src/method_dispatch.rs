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

use crate::wasm_data::{MethodInfo, METHOD_METADATA};

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

    // Encode result back to Candid and reply
    let result_bytes = encode_python_to_candid(&py_result, &method_info.returns);
    ic_cdk::api::call::reply_raw(&result_bytes);
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
fn decode_candid_args_to_python(
    arg_bytes: &[u8],
    params: &[crate::wasm_data::ParamInfo],
) -> Vec<basilisk_cpython::PyObjectRef> {
    let idl_args = candid::IDLArgs::from_bytes(arg_bytes).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Failed to decode Candid args: {}", e));
    });

    idl_args
        .args
        .into_iter()
        .enumerate()
        .map(|(i, idl_value)| {
            idl_value_to_python(&idl_value).unwrap_or_else(|e| {
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

/// Convert a candid::IDLValue to a Python object.
fn idl_value_to_python(
    value: &candid::IDLValue,
) -> Result<basilisk_cpython::PyObjectRef, String> {
    use candid::IDLValue;
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
        IDLValue::Opt(inner) => idl_value_to_python(inner.as_ref()),
        IDLValue::Vec(items) => {
            let py_items: Result<Vec<_>, _> =
                items.iter().map(|item| idl_value_to_python(item)).collect();
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
            let dict = basilisk_cpython::PyDict::new()
                .map_err(|e| e.to_rust_err_string())?;
            for field in fields {
                let key = match &field.id {
                    candid::types::Label::Named(name) => name.clone(),
                    candid::types::Label::Id(id) | candid::types::Label::Unnamed(id) => {
                        format!("_{}", id)
                    }
                };
                let value = idl_value_to_python(&field.val)?;
                dict.set_item_str(&key, &value)
                    .map_err(|e| e.to_rust_err_string())?;
            }
            Ok(dict.into_object())
        }
        IDLValue::Variant(variant) => {
            let dict = basilisk_cpython::PyDict::new()
                .map_err(|e| e.to_rust_err_string())?;
            let key = match &variant.0.id {
                candid::types::Label::Named(name) => name.clone(),
                candid::types::Label::Id(id) | candid::types::Label::Unnamed(id) => {
                    format!("_{}", id)
                }
            };
            let value = idl_value_to_python(&variant.0.val)?;
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
        _ => {
            // Fallback: convert to string representation
            let s = format!("{:?}", value);
            basilisk_cpython::PyObjectRef::from_str(&s)
                .map_err(|e| e.to_rust_err_string())
        }
    }
}

/// Convert a Python object to Candid bytes based on the expected return type.
fn encode_python_to_candid(
    py_result: &basilisk_cpython::PyObjectRef,
    return_type: &str,
) -> Vec<u8> {
    let idl_value = python_to_idl_value(py_result, return_type).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Failed to convert Python result to Candid: {}", e));
    });

    let idl_args = candid::IDLArgs::new(&[idl_value]);
    idl_args.to_bytes().unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Failed to encode Candid result: {}", e));
    })
}

/// Convert a Python object to a candid::IDLValue based on the type string.
fn python_to_idl_value(
    obj: &basilisk_cpython::PyObjectRef,
    candid_type: &str,
) -> Result<candid::IDLValue, String> {
    match candid_type.trim() {
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
        other if other.starts_with("opt ") => {
            if obj.is_none() {
                Ok(candid::IDLValue::Null)
            } else {
                let inner_type = &other[4..];
                let inner = python_to_idl_value(obj, inner_type)?;
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
                    items.push(python_to_idl_value(&py_obj, inner_type)?);
                }
                Ok(candid::IDLValue::Vec(items))
            }
        }
        _ => {
            // Fallback: try to convert as text
            let s = obj.extract_str().map_err(|e| e.to_rust_err_string())?;
            Ok(candid::IDLValue::Text(s))
        }
    }
}
