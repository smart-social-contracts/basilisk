//! CPython IC reply function (dynamic, per-canister-method).

use cdk_framework::{
    act::node::{
        canister_method::{QueryMethod, UpdateMethod},
        Context,
    },
    traits::ToTypeAnnotation,
};
use proc_macro2::TokenStream;
use quote::quote;

use crate::keywords;

pub fn generate(
    update_methods: &Vec<UpdateMethod>,
    query_methods: &Vec<QueryMethod>,
) -> TokenStream {
    let match_arms = generate_match_arms(update_methods, query_methods);
    quote! {
        unsafe extern "C" fn ic_reply(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let name_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 0);
            let value_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 1);
            if name_obj.is_null() || value_obj.is_null() {
                ic_cdk::trap("reply: expected (function_name, value) arguments");
            }
            let name_ref = match basilisk_cpython::PyObjectRef::from_borrowed(name_obj) {
                Some(o) => o,
                None => { ic_cdk::trap("reply: null function_name"); }
            };
            let value_ref = match basilisk_cpython::PyObjectRef::from_borrowed(value_obj) {
                Some(o) => o,
                None => { ic_cdk::trap("reply: null value"); }
            };
            let function_name: String = match name_ref.extract_str() {
                Ok(s) => s,
                Err(_) => { ic_cdk::trap("reply: function_name must be a string"); }
            };

            match &function_name[..] {
                #(#match_arms)*
                _ => {
                    ic_cdk::trap(&format!(
                        "attempted to reply from \"{}\", but it does not appear to be a canister method",
                        function_name
                    ));
                }
            }
        }
    }
}

fn generate_match_arms(
    update_methods: &Vec<UpdateMethod>,
    query_methods: &Vec<QueryMethod>,
) -> Vec<TokenStream> {
    let mut arms: Vec<TokenStream> = update_methods
        .iter()
        .filter(|m| m.is_manual)
        .map(|m| generate_match_arm(&m.name, &m.return_type, &m.name))
        .collect();

    arms.extend(
        query_methods
            .iter()
            .filter(|m| m.is_manual)
            .map(|m| generate_match_arm(&m.name, &m.return_type, &m.name)),
    );

    arms
}

fn generate_match_arm(
    name: &str,
    return_type: &cdk_framework::act::node::ReturnType,
    qualified_name: &str,
) -> TokenStream {
    let context = Context {
        keyword_list: keywords::get_python_keywords(),
        cdk_name: "basilisk".to_string(),
    };
    let rust_type = return_type.to_type_annotation(&context, qualified_name.to_string());

    quote! {
        #name => {
            let reply_value: (#rust_type) = match value_ref.try_from_vm_value(()) {
                Ok(v) => v,
                Err(e) => { ic_cdk::trap(&format!("reply type error: {}", e.to_rust_err_string())); }
            };
            match ic_cdk::api::call::reply((reply_value,))
                .try_into_vm_value(())
            {
                Ok(obj) => return obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }
    }
}
