//! Async result handler for cross-canister calls.
//!
//! This module handles Python generators that yield cross-canister call
//! descriptors. It drives the generator protocol (send/StopIteration)
//! and dispatches IC inter-canister calls.
//!
//! Note: In the template pattern, cross-canister calls use call_raw/call_raw128
//! exclusively since we don't have typed canister stubs. The typed call/
//! call_with_payment variants are kept for compatibility but always fall
//! through to an error (user code should use call_raw instead).

#[async_recursion::async_recursion(?Send)]
pub async fn async_result_handler(
    py_object_ref: &basilisk_cpython::PyObjectRef,
    arg: basilisk_cpython::PyObjectRef,
) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
    if !is_generator(py_object_ref) {
        return Ok(py_object_ref.clone());
    }
    let send_method = py_object_ref
        .get_attr("send")
        .map_err(|e| basilisk_cpython::PyError::new("AttributeError", &e.to_rust_err_string()))?;
    let args_tuple = basilisk_cpython::PyTuple::new(vec![arg.clone()])
        .map_err(|e| basilisk_cpython::PyError::new("RuntimeError", &e.to_rust_err_string()))?;
    match send_method.call(&args_tuple.into_object(), None) {
        Ok(returned) => {
            if is_generator(&returned) {
                let recursed = async_result_handler(
                    &returned,
                    basilisk_cpython::PyObjectRef::none(),
                )
                .await?;
                return async_result_handler(py_object_ref, recursed).await;
            }
            let name: String = returned
                .get_attr("name")
                .and_then(|n| n.extract_str())
                .map_err(|e| {
                    basilisk_cpython::PyError::new("AttributeError", &e.to_rust_err_string())
                })?;
            let args_list = returned.get_attr("args").map_err(|e| {
                basilisk_cpython::PyError::new("AttributeError", &e.to_rust_err_string())
            })?;
            match &name[..] {
                "call_raw" => async_result_handler_call_raw(py_object_ref, &args_list).await,
                "call_raw128" => {
                    async_result_handler_call_raw128(py_object_ref, &args_list).await
                }
                "call" | "call_with_payment" | "call_with_payment128" => {
                    Err(basilisk_cpython::PyError::new(
                        "NotImplementedError",
                        &format!(
                            "Typed cross-canister calls ('{}') are not supported in template mode. \
                             Use call_raw or call_raw128 instead.",
                            name
                        ),
                    ))
                }
                _ => Err(basilisk_cpython::PyError::new(
                    "SystemError",
                    &format!("async operation '{}' not supported", name),
                )),
            }
        }
        Err(e) => {
            if e.type_name == "StopIteration" {
                Ok(e.value
                    .unwrap_or_else(|| basilisk_cpython::PyObjectRef::none()))
            } else {
                Err(e)
            }
        }
    }
}

fn is_generator(py_object_ref: &basilisk_cpython::PyObjectRef) -> bool {
    py_object_ref.has_attr("send")
}

fn cpython_get_arg(
    args: &basilisk_cpython::PyObjectRef,
    index: usize,
) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
    let py_index = basilisk_cpython::PyObjectRef::from_i64(index as i64)?;
    args.get_item(&py_index)
}

async fn async_result_handler_call_raw(
    py_object_ref: &basilisk_cpython::PyObjectRef,
    args: &basilisk_cpython::PyObjectRef,
) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
    let canister_id_principal: candid::Principal = {
        let arg = cpython_get_arg(args, 0)?;
        let s = arg.extract_str()?;
        candid::Principal::from_text(&s).map_err(|e| {
            basilisk_cpython::PyError::new("ValueError", &format!("Invalid principal: {}", e))
        })?
    };
    let method_string: String = cpython_get_arg(args, 1)?.extract_str()?;
    let args_raw_vec: Vec<u8> = cpython_get_arg(args, 2)?.extract_bytes()?;
    let payment: u64 = cpython_get_arg(args, 3)?.extract_u64()?;
    let call_raw_result = ic_cdk::api::call::call_raw(
        canister_id_principal,
        &method_string,
        &args_raw_vec,
        payment,
    )
    .await;
    async_result_handler(
        py_object_ref,
        create_call_result_raw_bytes(call_raw_result)?,
    )
    .await
}

async fn async_result_handler_call_raw128(
    py_object_ref: &basilisk_cpython::PyObjectRef,
    args: &basilisk_cpython::PyObjectRef,
) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
    let canister_id_principal: candid::Principal = {
        let arg = cpython_get_arg(args, 0)?;
        let s = arg.extract_str()?;
        candid::Principal::from_text(&s).map_err(|e| {
            basilisk_cpython::PyError::new("ValueError", &format!("Invalid principal: {}", e))
        })?
    };
    let method_string: String = cpython_get_arg(args, 1)?.extract_str()?;
    let args_raw_vec: Vec<u8> = cpython_get_arg(args, 2)?.extract_bytes()?;
    let payment: u128 = {
        let v = cpython_get_arg(args, 3)?.extract_u64()?;
        v as u128
    };
    let call_raw_result = ic_cdk::api::call::call_raw128(
        canister_id_principal,
        &method_string,
        &args_raw_vec,
        payment,
    )
    .await;
    async_result_handler(
        py_object_ref,
        create_call_result_raw_bytes(call_raw_result)?,
    )
    .await
}

/// Create a CallResult wrapping raw bytes (for call_raw / call_raw128).
/// The Python code is responsible for decoding with ic.candid_decode().
fn create_call_result_raw_bytes(
    call_result: ic_cdk::api::call::CallResult<Vec<u8>>,
) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
    let interpreter = unsafe { crate::INTERPRETER_OPTION.as_mut() }.ok_or_else(|| {
        basilisk_cpython::PyError::new("SystemError", "missing python interpreter")
    })?;
    match call_result {
        Ok(raw_bytes) => {
            let ok_value = basilisk_cpython::PyObjectRef::from_bytes(&raw_bytes)?;
            let code = "from basilisk import CallResult; CallResult";
            let call_result_class = interpreter.eval_expression(code)?;
            let none = basilisk_cpython::PyObjectRef::none();
            let args = basilisk_cpython::PyTuple::new(vec![ok_value, none])?;
            call_result_class.call(&args.into_object(), None)
        }
        Err(err) => {
            let err_string = format!(
                "Rejection code {}, {}",
                (err.0 as i32).to_string(),
                err.1
            );
            let err_py = basilisk_cpython::PyObjectRef::from_str(&err_string)?;
            let code = "from basilisk import CallResult; CallResult";
            let call_result_class = interpreter.eval_expression(code)?;
            let none = basilisk_cpython::PyObjectRef::none();
            let args = basilisk_cpython::PyTuple::new(vec![none, err_py])?;
            call_result_class.call(&args.into_object(), None)
        }
    }
}

fn create_call_result_instance(
    call_result: ic_cdk::api::call::CallResult<Vec<u8>>,
) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
    let interpreter = unsafe { crate::INTERPRETER_OPTION.as_mut() }.ok_or_else(|| {
        basilisk_cpython::PyError::new("SystemError", "missing python interpreter")
    })?;
    match call_result {
        Ok(raw_bytes) => {
            // Decode Candid response bytes into IDLValues and convert to Python
            let ok_value = match candid::IDLArgs::from_bytes(&raw_bytes) {
                Ok(idl_args) => {
                    if idl_args.args.is_empty() {
                        basilisk_cpython::PyObjectRef::none()
                    } else if idl_args.args.len() == 1 {
                        crate::method_dispatch::idl_value_to_python(&idl_args.args[0])
                            .map_err(|e| basilisk_cpython::PyError::new("ValueError", &e))?
                    } else {
                        // Multiple return values: wrap in a Python tuple
                        let mut py_vals = Vec::new();
                        for val in &idl_args.args {
                            py_vals.push(
                                crate::method_dispatch::idl_value_to_python(val)
                                    .map_err(|e| basilisk_cpython::PyError::new("ValueError", &e))?,
                            );
                        }
                        basilisk_cpython::PyTuple::new(py_vals)?.into_object()
                    }
                }
                Err(_) => {
                    // Fallback: pass raw bytes if decoding fails
                    basilisk_cpython::PyObjectRef::from_bytes(&raw_bytes)?
                }
            };
            let code = "from basilisk import CallResult; CallResult";
            let call_result_class = interpreter.eval_expression(code)?;
            let none = basilisk_cpython::PyObjectRef::none();
            let args = basilisk_cpython::PyTuple::new(vec![ok_value, none])?;
            call_result_class.call(&args.into_object(), None)
        }
        Err(err) => {
            let err_string = format!(
                "Rejection code {}, {}",
                (err.0 as i32).to_string(),
                err.1
            );
            let err_py = basilisk_cpython::PyObjectRef::from_str(&err_string)?;
            let code = "from basilisk import CallResult; CallResult";
            let call_result_class = interpreter.eval_expression(code)?;
            let none = basilisk_cpython::PyObjectRef::none();
            let args = basilisk_cpython::PyTuple::new(vec![none, err_py])?;
            call_result_class.call(&args.into_object(), None)
        }
    }
}
