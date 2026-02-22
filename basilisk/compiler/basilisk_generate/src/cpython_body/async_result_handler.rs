//! CPython-specific async result handler for cross-canister calls.
//!
//! Replaces `body/async_result_handler.rs` for CPython backend.
//! Handles Python generator/coroutine-based async by driving the generator
//! using basilisk_cpython API instead of RustPython's PyIterReturn.

use cdk_framework::act::{
    node::{candid::Service, Context},
    ToTypeAnnotation,
};
use proc_macro2::TokenStream;
use quote::{format_ident, quote};

use crate::{keywords, tuple};

pub fn generate(services: &Vec<Service>) -> TokenStream {
    let call_match_arms = generate_call_match_arms(services);
    let call_with_payment_match_arms = generate_call_with_payment_match_arms(services);
    let call_with_payment128_match_arms = generate_call_with_payment128_match_arms(services);

    quote! {
        #[async_recursion::async_recursion(?Send)]
        async fn async_result_handler(
            py_object_ref: &basilisk_cpython::PyObjectRef,
            arg: basilisk_cpython::PyObjectRef,
        ) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
            if !is_generator(py_object_ref) {
                return Ok(py_object_ref.clone());
            }

            let send_method = py_object_ref.get_attr("send")
                .map_err(|e| basilisk_cpython::PyError::new("AttributeError", &e.to_rust_err_string()))?;

            let args_tuple = basilisk_cpython::PyTuple::new(vec![arg.clone()])
                .map_err(|e| basilisk_cpython::PyError::new("RuntimeError", &e.to_rust_err_string()))?;

            match send_method.call(&args_tuple.into_object(), None) {
                Ok(returned_py_object_ref) => {
                    if is_generator(&returned_py_object_ref) {
                        let recursed = async_result_handler(
                            &returned_py_object_ref,
                            basilisk_cpython::PyObjectRef::none(),
                        ).await?;
                        return async_result_handler(py_object_ref, recursed).await;
                    }

                    let name: String = returned_py_object_ref.get_attr("name")
                        .and_then(|n| n.extract_str())
                        .map_err(|e| basilisk_cpython::PyError::new("AttributeError", &e.to_rust_err_string()))?;

                    let args_list = returned_py_object_ref.get_attr("args")
                        .map_err(|e| basilisk_cpython::PyError::new("AttributeError", &e.to_rust_err_string()))?;

                    match &name[..] {
                        "call" => async_result_handler_call(py_object_ref, &args_list).await,
                        "call_with_payment" => {
                            async_result_handler_call_with_payment(py_object_ref, &args_list).await
                        }
                        "call_with_payment128" => {
                            async_result_handler_call_with_payment128(py_object_ref, &args_list).await
                        }
                        "call_raw" => {
                            async_result_handler_call_raw(py_object_ref, &args_list).await
                        }
                        "call_raw128" => {
                            async_result_handler_call_raw128(py_object_ref, &args_list).await
                        }
                        _ => Err(basilisk_cpython::PyError::new(
                            "SystemError",
                            &format!("async operation '{}' not supported", name),
                        )),
                    }
                }
                Err(e) => {
                    // StopIteration means the generator finished
                    if e.type_name == "StopIteration" {
                        // Extract the return value from StopIteration.value
                        Ok(e.value.unwrap_or_else(|| basilisk_cpython::PyObjectRef::none()))
                    } else {
                        Err(e)
                    }
                }
            }
        }

        fn is_generator(py_object_ref: &basilisk_cpython::PyObjectRef) -> bool {
            py_object_ref.has_attr("send")
        }

        /// Extract a list element by index from a Python sequence
        fn cpython_get_arg(
            args: &basilisk_cpython::PyObjectRef,
            index: usize,
        ) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
            let py_index = basilisk_cpython::PyObjectRef::from_i64(index as i64)?;
            args.get_item(&py_index)
        }

        async fn async_result_handler_call(
            py_object_ref: &basilisk_cpython::PyObjectRef,
            args: &basilisk_cpython::PyObjectRef,
        ) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
            let canister_id_principal: candid::Principal = {
                let arg = cpython_get_arg(args, 0)?;
                let s = arg.extract_str()?;
                candid::Principal::from_text(&s)
                    .map_err(|e| basilisk_cpython::PyError::new("ValueError", &format!("Invalid principal: {}", e)))?
            };
            let qual_name: String = cpython_get_arg(args, 1)?.extract_str()?;

            let cross_canister_call_function_name =
                format!("call_{}", qual_name.replace(".", "_"));

            let call_result_instance = match &cross_canister_call_function_name[..] {
                #(#call_match_arms),*
                _ => return Err(basilisk_cpython::PyError::new(
                    "AttributeError",
                    &format!(
                        "canister '{}' has no attribute '{}'",
                        canister_id_principal,
                        qual_name
                    )
                ))
            };

            async_result_handler(py_object_ref, call_result_instance).await
        }

        async fn async_result_handler_call_with_payment(
            py_object_ref: &basilisk_cpython::PyObjectRef,
            args: &basilisk_cpython::PyObjectRef,
        ) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
            let canister_id_principal: candid::Principal = {
                let arg = cpython_get_arg(args, 0)?;
                let s = arg.extract_str()?;
                candid::Principal::from_text(&s)
                    .map_err(|e| basilisk_cpython::PyError::new("ValueError", &format!("Invalid principal: {}", e)))?
            };
            let qual_name: String = cpython_get_arg(args, 1)?.extract_str()?;

            let cross_canister_call_with_payment_function_name =
                format!("call_with_payment_{}", qual_name.replace(".", "_"));

            let call_result_instance = match &cross_canister_call_with_payment_function_name[..] {
                #(#call_with_payment_match_arms),*
                _ => return Err(basilisk_cpython::PyError::new(
                    "AttributeError",
                    &format!(
                        "canister '{}' has no attribute '{}'",
                        canister_id_principal,
                        qual_name
                    )
                ))
            };

            async_result_handler(py_object_ref, call_result_instance).await
        }

        async fn async_result_handler_call_with_payment128(
            py_object_ref: &basilisk_cpython::PyObjectRef,
            args: &basilisk_cpython::PyObjectRef,
        ) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
            let canister_id_principal: candid::Principal = {
                let arg = cpython_get_arg(args, 0)?;
                let s = arg.extract_str()?;
                candid::Principal::from_text(&s)
                    .map_err(|e| basilisk_cpython::PyError::new("ValueError", &format!("Invalid principal: {}", e)))?
            };
            let qual_name: String = cpython_get_arg(args, 1)?.extract_str()?;

            let cross_canister_call_with_payment128_function_name =
                format!("call_with_payment128_{}", qual_name.replace(".", "_"));

            let call_result_instance =
                match &cross_canister_call_with_payment128_function_name[..] {
                    #(#call_with_payment128_match_arms),*
                    _ => return Err(basilisk_cpython::PyError::new(
                        "AttributeError",
                        &format!(
                            "canister '{}' has no attribute '{}'",
                            canister_id_principal,
                            qual_name
                        )
                    ))
                };

            async_result_handler(py_object_ref, call_result_instance).await
        }

        async fn async_result_handler_call_raw(
            py_object_ref: &basilisk_cpython::PyObjectRef,
            args: &basilisk_cpython::PyObjectRef,
        ) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
            let canister_id_principal: candid::Principal = {
                let arg = cpython_get_arg(args, 0)?;
                let s = arg.extract_str()?;
                candid::Principal::from_text(&s)
                    .map_err(|e| basilisk_cpython::PyError::new("ValueError", &format!("Invalid principal: {}", e)))?
            };
            let method_string: String = cpython_get_arg(args, 1)?.extract_str()?;
            let args_raw_vec: Vec<u8> = cpython_get_arg(args, 2)?.extract_bytes()?;
            let payment: u64 = cpython_get_arg(args, 3)?.extract_u64()?;

            let call_raw_result = ic_cdk::api::call::call_raw(
                canister_id_principal,
                &method_string,
                &args_raw_vec,
                payment
            ).await;

            async_result_handler(
                py_object_ref,
                cpython_create_call_result_instance(call_raw_result)?
            ).await
        }

        async fn async_result_handler_call_raw128(
            py_object_ref: &basilisk_cpython::PyObjectRef,
            args: &basilisk_cpython::PyObjectRef,
        ) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
            let canister_id_principal: candid::Principal = {
                let arg = cpython_get_arg(args, 0)?;
                let s = arg.extract_str()?;
                candid::Principal::from_text(&s)
                    .map_err(|e| basilisk_cpython::PyError::new("ValueError", &format!("Invalid principal: {}", e)))?
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
                payment
            ).await;

            async_result_handler(
                py_object_ref,
                cpython_create_call_result_instance(call_raw_result)?
            ).await
        }

        fn cpython_create_call_result_instance<T>(
            call_result: ic_cdk::api::call::CallResult<T>
        ) -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError>
        where
            T: CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>,
        {
            let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                .ok_or_else(|| basilisk_cpython::PyError::new("SystemError", "missing python interpreter"))?;

            match call_result {
                Ok(ok) => {
                    let ok_value = ok.try_into_vm_value(())
                        .map_err(|e| basilisk_cpython::PyError::new("TypeError", &e.0))?;

                    // Create CallResult(ok_value, None)
                    let code = "from basilisk import CallResult; CallResult";
                    let call_result_class = interpreter.eval_expression(code)?;
                    let none = basilisk_cpython::PyObjectRef::none();
                    let args = basilisk_cpython::PyTuple::new(vec![ok_value, none])?;
                    call_result_class.call(&args.into_object(), None)
                },
                Err(err) => {
                    let err_string = format!(
                        "Rejection code {rejection_code}, {error_message}",
                        rejection_code = (err.0 as i32).to_string(),
                        error_message = err.1
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
    }
}

fn generate_call_match_arms(services: &Vec<Service>) -> Vec<TokenStream> {
    services
        .iter()
        .map(|service| {
            let canister_name = &service.name;

            let arms: Vec<TokenStream> = service
                .methods
                .iter()
                .map(|method| {
                    let cross_canister_function_call_name =
                        format!("call_{}_{}", canister_name, method.name);
                    let cross_canister_function_call_name_ident =
                        format_ident!("{}", cross_canister_function_call_name);

                    let context = Context {
                        keyword_list: keywords::get_python_keywords(),
                        cdk_name: "basilisk".to_string(),
                    };

                    let param_variable_definitions: Vec<TokenStream> = method
                        .params
                        .iter()
                        .enumerate()
                        .map(|(index, param)| {
                            let variable_name = format_ident!("{}", param.get_prefixed_name());
                            let variable_type = param.to_type_annotation(
                                &context,
                                method.create_qualified_name(&service.name),
                            );
                            let actual_index = index + 2;
                            quote! {
                                let #variable_name: (#variable_type) = {
                                    let arg = cpython_get_arg(args, #actual_index)?;
                                    arg.try_from_vm_value(())?
                                };
                            }
                        })
                        .collect();

                    let param_names = method
                        .params
                        .iter()
                        .map(|param| {
                            let name = format_ident!("{}", param.get_prefixed_name());
                            quote! {#name}
                        })
                        .collect();
                    let params = tuple::generate_tuple(&param_names);

                    quote! {
                        #cross_canister_function_call_name => {
                            let canister_id_principal: candid::Principal = {
                                let arg = cpython_get_arg(args, 0)?;
                                let s = arg.extract_str()?;
                                candid::Principal::from_text(&s)
                                    .map_err(|e| basilisk_cpython::PyError::new("ValueError", &format!("Invalid principal: {}", e)))?
                            };

                            #(#param_variable_definitions)*

                            cpython_create_call_result_instance(
                                #cross_canister_function_call_name_ident(
                                    canister_id_principal,
                                    #params
                                )
                                .await
                            )?
                        }
                    }
                })
                .collect();

            quote! { #(#arms)* }
        })
        .collect()
}

fn generate_call_with_payment_match_arms(services: &Vec<Service>) -> Vec<TokenStream> {
    services
        .iter()
        .map(|service| {
            let canister_name = &service.name;

            let arms: Vec<TokenStream> = service
                .methods
                .iter()
                .map(|method| {
                    let name = format!("call_with_payment_{}_{}", canister_name, method.name);
                    let name_ident = format_ident!("{}", name);

                    let context = Context {
                        keyword_list: keywords::get_python_keywords(),
                        cdk_name: "basilisk".to_string(),
                    };

                    let param_defs: Vec<TokenStream> = method
                        .params
                        .iter()
                        .enumerate()
                        .map(|(index, param)| {
                            let var = format_ident!("{}", param.get_prefixed_name());
                            let ty = param.to_type_annotation(
                                &context,
                                method.create_qualified_name(&service.name),
                            );
                            let idx = index + 2;
                            quote! {
                                let #var: (#ty) = {
                                    let arg = cpython_get_arg(args, #idx)?;
                                    arg.try_from_vm_value(())?
                                };
                            }
                        })
                        .collect();

                    let param_names: Vec<TokenStream> = method
                        .params
                        .iter()
                        .map(|param| {
                            let n = format_ident!("{}", param.get_prefixed_name());
                            quote! {#n}
                        })
                        .collect();
                    let params = tuple::generate_tuple(&param_names);

                    let payment_index = method.params.len() + 2;
                    quote! {
                        #name => {
                            let canister_id_principal: candid::Principal = {
                                let arg = cpython_get_arg(args, 0)?;
                                let s = arg.extract_str()?;
                                candid::Principal::from_text(&s)
                                    .map_err(|e| basilisk_cpython::PyError::new("ValueError", &format!("Invalid principal: {}", e)))?
                            };
                            #(#param_defs)*
                            let payment: u64 = cpython_get_arg(args, #payment_index)?.extract_u64()?;
                            cpython_create_call_result_instance(
                                #name_ident(canister_id_principal, #params, payment).await
                            )?
                        }
                    }
                })
                .collect();
            quote! { #(#arms)* }
        })
        .collect()
}

fn generate_call_with_payment128_match_arms(services: &Vec<Service>) -> Vec<TokenStream> {
    services
        .iter()
        .map(|service| {
            let canister_name = &service.name;

            let arms: Vec<TokenStream> = service
                .methods
                .iter()
                .map(|method| {
                    let name = format!("call_with_payment128_{}_{}", canister_name, method.name);
                    let name_ident = format_ident!("{}", name);

                    let context = Context {
                        keyword_list: keywords::get_python_keywords(),
                        cdk_name: "basilisk".to_string(),
                    };

                    let param_defs: Vec<TokenStream> = method
                        .params
                        .iter()
                        .enumerate()
                        .map(|(index, param)| {
                            let var = format_ident!("{}", param.get_prefixed_name());
                            let ty = param.to_type_annotation(
                                &context,
                                method.create_qualified_name(&service.name),
                            );
                            let idx = index + 2;
                            quote! {
                                let #var: (#ty) = {
                                    let arg = cpython_get_arg(args, #idx)?;
                                    arg.try_from_vm_value(())?
                                };
                            }
                        })
                        .collect();

                    let param_names: Vec<TokenStream> = method
                        .params
                        .iter()
                        .map(|param| {
                            let n = format_ident!("{}", param.get_prefixed_name());
                            quote! {#n}
                        })
                        .collect();
                    let params = tuple::generate_tuple(&param_names);

                    let payment_index = method.params.len() + 2;
                    quote! {
                        #name => {
                            let canister_id_principal: candid::Principal = {
                                let arg = cpython_get_arg(args, 0)?;
                                let s = arg.extract_str()?;
                                candid::Principal::from_text(&s)
                                    .map_err(|e| basilisk_cpython::PyError::new("ValueError", &format!("Invalid principal: {}", e)))?
                            };
                            #(#param_defs)*
                            let payment: u128 = {
                                let v = cpython_get_arg(args, #payment_index)?.extract_u64()?;
                                v as u128
                            };
                            cpython_create_call_result_instance(
                                #name_ident(canister_id_principal, #params, payment).await
                            )?
                        }
                    }
                })
                .collect();
            quote! { #(#arms)* }
        })
        .collect()
}
