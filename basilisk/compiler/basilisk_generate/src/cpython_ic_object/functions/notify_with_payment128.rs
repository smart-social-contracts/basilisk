//! CPython IC notify_with_payment128 functions (dynamic, per-service).

use cdk_framework::{
    act::node::{
        candid::{service::Method, Service},
        Context,
    },
    traits::ToTypeAnnotation,
};
use proc_macro2::TokenStream;
use quote::{format_ident, quote};

use crate::{keywords, tuple};

pub fn generate(services: &Vec<Service>) -> Vec<TokenStream> {
    services
        .iter()
        .flat_map(|service| {
            service
                .methods
                .iter()
                .map(move |method| generate_notify_with_payment128_fn(service, method))
        })
        .collect()
}

fn generate_notify_with_payment128_fn(service: &Service, method: &Method) -> TokenStream {
    let fn_name = format_ident!(
        "ic_notify_with_payment128_{}_{}",
        service.name,
        method.name
    );
    let real_fn_name = format_ident!(
        "notify_with_payment128_{}_{}",
        service.name,
        method.name
    );

    let param_extractions: Vec<TokenStream> = method
        .params
        .iter()
        .enumerate()
        .map(|(index, param)| {
            let var_name = format_ident!("{}", param.get_prefixed_name());
            let context = Context {
                keyword_list: keywords::get_python_keywords(),
                cdk_name: "basilisk".to_string(),
            };
            let var_type =
                param.to_type_annotation(&context, method.create_qualified_name(&service.name));
            let actual_index = (index + 1) as isize;
            quote! {
                let arg_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, #actual_index);
                let arg_ref = basilisk_cpython::PyObjectRef::from_borrowed(arg_obj).unwrap();
                let #var_name: (#var_type) = arg_ref.try_from_vm_value(()).unwrap_or_trap();
            }
        })
        .collect();

    let param_names: Vec<TokenStream> = method
        .params
        .iter()
        .map(|param| {
            let name = format_ident!("{}", param.get_prefixed_name());
            quote! { #name }
        })
        .collect();
    let params = tuple::generate_tuple(&param_names);

    let payment_index = (method.params.len() + 1) as isize;

    quote! {
        unsafe extern "C" fn #fn_name(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let canister_id_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 0);
            let canister_id_ref = basilisk_cpython::PyObjectRef::from_borrowed(canister_id_obj).unwrap();
            let canister_id_principal: candid::Principal = canister_id_ref.try_from_vm_value(()).unwrap_or_trap();

            #(#param_extractions)*

            let payment_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, #payment_index);
            let payment_ref = basilisk_cpython::PyObjectRef::from_borrowed(payment_obj).unwrap();
            let payment: u128 = payment_ref.extract_u64().unwrap_or_trap() as u128;

            let notify_result = #real_fn_name(canister_id_principal, #params, payment);

            match notify_result.try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }
    }
}
