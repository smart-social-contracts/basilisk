//! CPython-specific IC object implementation.
//!
//! Replaces `ic_object/mod.rs` when CPython backend is selected.
//! Instead of using RustPython's `#[pyclass]` / `#[pymethod]` macros,
//! this generates a CPython C extension module `_basilisk_ic` with
//! `PyCFunction` entries for each IC API method.
//!
//! The generated code creates the module via `PyModule_Create` and
//! registers it in `sys.modules` so Python code can `import _basilisk_ic`.

mod functions;

use cdk_framework::act::node::{
    candid::Service,
    canister_method::{QueryMethod, UpdateMethod},
};
use proc_macro2::TokenStream;
use quote::quote;

use crate::StableBTreeMapNode;

pub fn generate(
    update_methods: &Vec<UpdateMethod>,
    query_methods: &Vec<QueryMethod>,
    services: &Vec<Service>,
    stable_b_tree_map_nodes: &Vec<StableBTreeMapNode>,
) -> TokenStream {
    let simple_functions = functions::simple::generate();
    let arg_functions = functions::with_args::generate();
    let timer_functions = functions::timers::generate();
    let stable_functions = functions::stable::generate();
    let reply_function = functions::reply::generate(update_methods, query_methods);
    let notify_functions = functions::notify::generate(services);
    let notify_with_payment128_functions = functions::notify_with_payment128::generate(services);
    let stable_btree_functions = functions::stable_btree::generate(stable_b_tree_map_nodes);

    // Collect all method defs
    let method_def_entries = generate_method_def_entries(services, stable_b_tree_map_nodes);

    quote! {
        // === IC function implementations ===

        #simple_functions
        #arg_functions
        #timer_functions
        #stable_functions
        #reply_function
        #(#notify_functions)*
        #(#notify_with_payment128_functions)*
        #stable_btree_functions

        // === Module definition ===

        static mut IC_MODULE_METHODS: Option<Vec<basilisk_cpython::ffi::PyMethodDef>> = None;

        fn basilisk_ic_create_module() -> Result<basilisk_cpython::PyObjectRef, basilisk_cpython::PyError> {
            // Build the method definitions array
            let methods: Vec<basilisk_cpython::ffi::PyMethodDef> = vec![
                #method_def_entries

                // Sentinel entry (all nulls)
                basilisk_cpython::ffi::PyMethodDef {
                    ml_name: core::ptr::null(),
                    ml_meth: None,
                    ml_flags: 0,
                    ml_doc: core::ptr::null(),
                },
            ];

            // Store methods in a static so they live for the process lifetime
            unsafe {
                IC_MODULE_METHODS = Some(methods);
                let methods_ptr = IC_MODULE_METHODS.as_ref().unwrap().as_ptr()
                    as *mut basilisk_cpython::ffi::PyMethodDef;

                // Create the module
                let module_name = b"_basilisk_ic\0".as_ptr() as *const core::ffi::c_char;

                // We need a static module def
                static mut MODULE_DEF: basilisk_cpython::ffi::PyModuleDef = basilisk_cpython::ffi::PyModuleDef {
                    m_base: basilisk_cpython::ffi::PyModuleDef_HEAD_INIT,
                    m_name: core::ptr::null(),
                    m_doc: core::ptr::null(),
                    m_size: -1,
                    m_methods: core::ptr::null_mut(),
                    m_slots: core::ptr::null_mut(),
                    m_traverse: None,
                    m_clear: None,
                    m_free: None,
                };

                MODULE_DEF.m_name = module_name;
                MODULE_DEF.m_methods = methods_ptr;

                let module = basilisk_cpython::ffi::PyModule_Create(&mut MODULE_DEF);
                if module.is_null() {
                    return Err(basilisk_cpython::PyError::fetch());
                }

                // Register in sys.modules
                let sys_modules = basilisk_cpython::ffi::PySys_GetObject(
                    b"modules\0".as_ptr() as *const core::ffi::c_char,
                );
                if !sys_modules.is_null() {
                    basilisk_cpython::ffi::PyDict_SetItemString(
                        sys_modules,
                        module_name,
                        module,
                    );
                }

                Ok(basilisk_cpython::PyObjectRef::from_owned(module)
                    .ok_or_else(|| basilisk_cpython::PyError::new("SystemError", "null module"))?)
            }
        }
    }
}

fn generate_method_def_entries(
    services: &Vec<Service>,
    stable_b_tree_map_nodes: &Vec<StableBTreeMapNode>,
) -> TokenStream {
    // Static method names (simple no-arg functions)
    let simple_entries = vec![
        ("accept_message", "ic_accept_message", "METH_NOARGS"),
        ("arg_data_raw", "ic_arg_data_raw", "METH_NOARGS"),
        ("arg_data_raw_size", "ic_arg_data_raw_size", "METH_NOARGS"),
        ("caller", "ic_caller", "METH_NOARGS"),
        ("canister_balance", "ic_canister_balance", "METH_NOARGS"),
        ("canister_balance128", "ic_canister_balance128", "METH_NOARGS"),
        ("data_certificate", "ic_data_certificate", "METH_NOARGS"),
        ("id", "ic_id", "METH_NOARGS"),
        ("method_name", "ic_method_name", "METH_NOARGS"),
        ("msg_cycles_available", "ic_msg_cycles_available", "METH_NOARGS"),
        ("msg_cycles_available128", "ic_msg_cycles_available128", "METH_NOARGS"),
        ("msg_cycles_refunded", "ic_msg_cycles_refunded", "METH_NOARGS"),
        ("msg_cycles_refunded128", "ic_msg_cycles_refunded128", "METH_NOARGS"),
        ("performance_counter", "ic_performance_counter", "METH_O"),
        ("reject_code", "ic_reject_code", "METH_NOARGS"),
        ("reject_message", "ic_reject_message", "METH_NOARGS"),
        ("stable_bytes", "ic_stable_bytes", "METH_NOARGS"),
        ("stable_size", "ic_stable_size", "METH_NOARGS"),
        ("stable64_size", "ic_stable64_size", "METH_NOARGS"),
        ("time", "ic_time", "METH_NOARGS"),
    ];

    let arg_entries = vec![
        ("candid_decode", "ic_candid_decode", "METH_O"),
        ("candid_encode", "ic_candid_encode", "METH_O"),
        ("clear_timer", "ic_clear_timer", "METH_O"),
        ("msg_cycles_accept", "ic_msg_cycles_accept", "METH_O"),
        ("msg_cycles_accept128", "ic_msg_cycles_accept128", "METH_O"),
        ("print", "ic_print", "METH_O"),
        ("reject", "ic_reject", "METH_O"),
        ("reply", "ic_reply", "METH_VARARGS"),
        ("reply_raw", "ic_reply_raw", "METH_O"),
        ("set_certified_data", "ic_set_certified_data", "METH_O"),
        ("set_timer", "ic_set_timer", "METH_VARARGS"),
        ("set_timer_interval", "ic_set_timer_interval", "METH_VARARGS"),
        ("stable_grow", "ic_stable_grow", "METH_O"),
        ("stable_read", "ic_stable_read", "METH_VARARGS"),
        ("stable_write", "ic_stable_write", "METH_VARARGS"),
        ("stable64_grow", "ic_stable64_grow", "METH_O"),
        ("stable64_read", "ic_stable64_read", "METH_VARARGS"),
        ("stable64_write", "ic_stable64_write", "METH_VARARGS"),
        ("trap", "ic_trap", "METH_O"),
    ];

    let all_entries: Vec<TokenStream> = simple_entries
        .iter()
        .chain(arg_entries.iter())
        .map(|(py_name, rust_fn, method_flag)| {
            let name_bytes = format!("{}\0", py_name);
            let fn_ident = quote::format_ident!("{}", rust_fn);
            let flag_ident = match *method_flag {
                "METH_NOARGS" => quote! { basilisk_cpython::ffi::METH_NOARGS },
                "METH_O" => quote! { basilisk_cpython::ffi::METH_O },
                "METH_VARARGS" => quote! { basilisk_cpython::ffi::METH_VARARGS },
                _ => quote! { basilisk_cpython::ffi::METH_VARARGS },
            };
            quote! {
                basilisk_cpython::ffi::PyMethodDef {
                    ml_name: #name_bytes.as_ptr() as *const core::ffi::c_char,
                    ml_meth: Some(#fn_ident),
                    ml_flags: #flag_ident,
                    ml_doc: core::ptr::null(),
                },
            }
        })
        .collect();

    // Add dynamic entries for notify functions
    let notify_entries: Vec<TokenStream> = services
        .iter()
        .flat_map(|service| {
            service.methods.iter().map(move |method| {
                let py_name = format!("notify_{}_{}\0", service.name, method.name);
                let fn_name = quote::format_ident!("ic_notify_{}_{}", service.name, method.name);
                quote! {
                    basilisk_cpython::ffi::PyMethodDef {
                        ml_name: #py_name.as_ptr() as *const core::ffi::c_char,
                        ml_meth: Some(#fn_name),
                        ml_flags: basilisk_cpython::ffi::METH_VARARGS,
                        ml_doc: core::ptr::null(),
                    },
                }
            })
        })
        .collect();

    let notify128_entries: Vec<TokenStream> = services
        .iter()
        .flat_map(|service| {
            service.methods.iter().map(move |method| {
                let py_name = format!("notify_with_payment128_{}_{}\0", service.name, method.name);
                let fn_name = quote::format_ident!(
                    "ic_notify_with_payment128_{}_{}",
                    service.name,
                    method.name
                );
                quote! {
                    basilisk_cpython::ffi::PyMethodDef {
                        ml_name: #py_name.as_ptr() as *const core::ffi::c_char,
                        ml_meth: Some(#fn_name),
                        ml_flags: basilisk_cpython::ffi::METH_VARARGS,
                        ml_doc: core::ptr::null(),
                    },
                }
            })
        })
        .collect();

    // Add stable btree map entries
    let btree_entries: Vec<TokenStream> = stable_b_tree_map_nodes
        .iter()
        .flat_map(|node| {
            let memory_id = node.memory_id;
            let ops = vec![
                "contains_key", "get", "insert", "is_empty", "keys", "len",
                "remove", "values", "items",
            ];
            ops.into_iter().map(move |op| {
                let py_name = format!("stable_b_tree_map_{}_{}\0", memory_id, op);
                let fn_name = quote::format_ident!("ic_stable_b_tree_map_{}_{}", memory_id, op);
                let flag = if op == "is_empty" || op == "len" || op == "keys" || op == "values" || op == "items" {
                    quote! { basilisk_cpython::ffi::METH_NOARGS }
                } else if op == "insert" {
                    quote! { basilisk_cpython::ffi::METH_VARARGS }
                } else {
                    quote! { basilisk_cpython::ffi::METH_O }
                };
                quote! {
                    basilisk_cpython::ffi::PyMethodDef {
                        ml_name: #py_name.as_ptr() as *const core::ffi::c_char,
                        ml_meth: Some(#fn_name),
                        ml_flags: #flag,
                        ml_doc: core::ptr::null(),
                    },
                }
            })
        })
        .collect();

    quote! {
        #(#all_entries)*
        #(#notify_entries)*
        #(#notify128_entries)*
        #(#btree_entries)*
    }
}
