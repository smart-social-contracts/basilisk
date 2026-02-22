//! CPython-specific body code generation.
//!
//! Replaces `body/mod.rs` when CPython backend is selected.
//! Generates body code that uses basilisk_cpython instead of RustPython.

pub mod async_result_handler;
pub mod call_global_python_function;
mod unwrap_or_trap;
mod utils;

use cdk_framework::act::node::{
    candid::Service,
    canister_method::{QueryMethod, UpdateMethod},
};
use proc_macro2::TokenStream;

use crate::{cpython_ic_object, stable_b_tree_map_nodes::rust, StableBTreeMapNode};

pub fn generate(
    update_methods: &Vec<UpdateMethod>,
    query_methods: &Vec<QueryMethod>,
    services: &Vec<Service>,
    stable_b_tree_map_nodes: &Vec<StableBTreeMapNode>,
) -> TokenStream {
    let async_result_handler = async_result_handler::generate(services);
    let call_global_python_function = call_global_python_function::generate();
    let guard_against_non_controllers = crate::body::guard_against_non_controllers::generate();
    // CPython-specific IC object (C extension module instead of RustPython pyclass)
    let ic_object = cpython_ic_object::generate(
        update_methods,
        query_methods,
        services,
        stable_b_tree_map_nodes,
    );
    let stable_b_tree_map = rust::generate(stable_b_tree_map_nodes);
    let unwrap_or_trap = unwrap_or_trap::generate();
    let utils = utils::generate();

    quote::quote! {
        #async_result_handler
        #call_global_python_function
        #guard_against_non_controllers
        #ic_object
        #stable_b_tree_map
        #unwrap_or_trap
        #utils
    }
}
