//! CPython IC stable BTree map functions (dynamic, per-node).

use proc_macro2::TokenStream;
use quote::{format_ident, quote};

use crate::StableBTreeMapNode;

pub fn generate(stable_b_tree_map_nodes: &Vec<StableBTreeMapNode>) -> TokenStream {
    let functions: Vec<TokenStream> = stable_b_tree_map_nodes
        .iter()
        .flat_map(|node| generate_node_functions(node))
        .collect();

    quote! { #(#functions)* }
}

fn generate_node_functions(node: &StableBTreeMapNode) -> Vec<TokenStream> {
    let memory_id = node.memory_id;

    let contains_key_fn = format_ident!("ic_stable_b_tree_map_{}_contains_key", memory_id);
    let get_fn = format_ident!("ic_stable_b_tree_map_{}_get", memory_id);
    let insert_fn = format_ident!("ic_stable_b_tree_map_{}_insert", memory_id);
    let is_empty_fn = format_ident!("ic_stable_b_tree_map_{}_is_empty", memory_id);
    let keys_fn = format_ident!("ic_stable_b_tree_map_{}_keys", memory_id);
    let len_fn = format_ident!("ic_stable_b_tree_map_{}_len", memory_id);
    let remove_fn = format_ident!("ic_stable_b_tree_map_{}_remove", memory_id);
    let values_fn = format_ident!("ic_stable_b_tree_map_{}_values", memory_id);
    let items_fn = format_ident!("ic_stable_b_tree_map_{}_items", memory_id);

    let map_name = format_ident!("STABLE_B_TREE_MAP_{}", memory_id);

    vec![
        quote! {
            unsafe extern "C" fn #contains_key_fn(
                _self_obj: *mut basilisk_cpython::ffi::PyObject,
                arg: *mut basilisk_cpython::ffi::PyObject,
            ) -> *mut basilisk_cpython::ffi::PyObject {
                let key_ref = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                    Some(o) => o,
                    None => return core::ptr::null_mut(),
                };
                let key = match key_ref.try_from_vm_value(()) {
                    Ok(k) => k,
                    Err(e) => { ic_cdk::trap(&e.to_rust_err_string()); }
                };
                let result = #map_name.with(|map| map.borrow().contains_key(&key));
                basilisk_cpython::PyObjectRef::from_bool(result).into_ptr()
            }
        },
        quote! {
            unsafe extern "C" fn #get_fn(
                _self_obj: *mut basilisk_cpython::ffi::PyObject,
                arg: *mut basilisk_cpython::ffi::PyObject,
            ) -> *mut basilisk_cpython::ffi::PyObject {
                let key_ref = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                    Some(o) => o,
                    None => return core::ptr::null_mut(),
                };
                let key = match key_ref.try_from_vm_value(()) {
                    Ok(k) => k,
                    Err(e) => { ic_cdk::trap(&e.to_rust_err_string()); }
                };
                let result = #map_name.with(|map| map.borrow().get(&key));
                match result {
                    Some(value) => match value.try_into_vm_value(()) {
                        Ok(obj) => obj.into_ptr(),
                        Err(e) => { ic_cdk::trap(&e.0); }
                    },
                    None => basilisk_cpython::PyObjectRef::none().into_ptr(),
                }
            }
        },
        quote! {
            unsafe extern "C" fn #insert_fn(
                _self_obj: *mut basilisk_cpython::ffi::PyObject,
                arg: *mut basilisk_cpython::ffi::PyObject,
            ) -> *mut basilisk_cpython::ffi::PyObject {
                // arg is a tuple (key, value)
                let key_obj = basilisk_cpython::ffi::PyTuple_GetItem(arg, 0);
                let value_obj = basilisk_cpython::ffi::PyTuple_GetItem(arg, 1);
                if key_obj.is_null() || value_obj.is_null() {
                    ic_cdk::trap("stable_b_tree_map insert: expected (key, value)");
                }
                let key_ref = basilisk_cpython::PyObjectRef::from_borrowed(key_obj).unwrap();
                let value_ref = basilisk_cpython::PyObjectRef::from_borrowed(value_obj).unwrap();
                let key = match key_ref.try_from_vm_value(()) {
                    Ok(k) => k,
                    Err(e) => { ic_cdk::trap(&e.to_rust_err_string()); }
                };
                let value = match value_ref.try_from_vm_value(()) {
                    Ok(v) => v,
                    Err(e) => { ic_cdk::trap(&e.to_rust_err_string()); }
                };
                let result = #map_name.with(|map| map.borrow_mut().insert(key, value));
                match result {
                    Ok(prev) => match prev {
                        Some(prev_val) => match prev_val.try_into_vm_value(()) {
                            Ok(obj) => obj.into_ptr(),
                            Err(e) => { ic_cdk::trap(&e.0); }
                        },
                        None => basilisk_cpython::PyObjectRef::none().into_ptr(),
                    },
                    Err(e) => match e.try_into_vm_value(()) {
                        Ok(obj) => obj.into_ptr(),
                        Err(e2) => { ic_cdk::trap(&e2.0); }
                    }
                }
            }
        },
        quote! {
            unsafe extern "C" fn #is_empty_fn(
                _self_obj: *mut basilisk_cpython::ffi::PyObject,
                _args: *mut basilisk_cpython::ffi::PyObject,
            ) -> *mut basilisk_cpython::ffi::PyObject {
                let result = #map_name.with(|map| map.borrow().is_empty());
                basilisk_cpython::PyObjectRef::from_bool(result).into_ptr()
            }
        },
        quote! {
            unsafe extern "C" fn #keys_fn(
                _self_obj: *mut basilisk_cpython::ffi::PyObject,
                _args: *mut basilisk_cpython::ffi::PyObject,
            ) -> *mut basilisk_cpython::ffi::PyObject {
                let keys: Vec<_> = #map_name.with(|map| {
                    map.borrow().iter().map(|(k, _)| k).collect()
                });
                match keys.try_into_vm_value(()) {
                    Ok(obj) => obj.into_ptr(),
                    Err(e) => { ic_cdk::trap(&e.0); }
                }
            }
        },
        quote! {
            unsafe extern "C" fn #len_fn(
                _self_obj: *mut basilisk_cpython::ffi::PyObject,
                _args: *mut basilisk_cpython::ffi::PyObject,
            ) -> *mut basilisk_cpython::ffi::PyObject {
                let len = #map_name.with(|map| map.borrow().len());
                match (len as u64).try_into_vm_value(()) {
                    Ok(obj) => obj.into_ptr(),
                    Err(e) => { ic_cdk::trap(&e.0); }
                }
            }
        },
        quote! {
            unsafe extern "C" fn #remove_fn(
                _self_obj: *mut basilisk_cpython::ffi::PyObject,
                arg: *mut basilisk_cpython::ffi::PyObject,
            ) -> *mut basilisk_cpython::ffi::PyObject {
                let key_ref = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                    Some(o) => o,
                    None => return core::ptr::null_mut(),
                };
                let key = match key_ref.try_from_vm_value(()) {
                    Ok(k) => k,
                    Err(e) => { ic_cdk::trap(&e.to_rust_err_string()); }
                };
                let result = #map_name.with(|map| map.borrow_mut().remove(&key));
                match result {
                    Some(value) => match value.try_into_vm_value(()) {
                        Ok(obj) => obj.into_ptr(),
                        Err(e) => { ic_cdk::trap(&e.0); }
                    },
                    None => basilisk_cpython::PyObjectRef::none().into_ptr(),
                }
            }
        },
        quote! {
            unsafe extern "C" fn #values_fn(
                _self_obj: *mut basilisk_cpython::ffi::PyObject,
                _args: *mut basilisk_cpython::ffi::PyObject,
            ) -> *mut basilisk_cpython::ffi::PyObject {
                let values: Vec<_> = #map_name.with(|map| {
                    map.borrow().iter().map(|(_, v)| v).collect()
                });
                match values.try_into_vm_value(()) {
                    Ok(obj) => obj.into_ptr(),
                    Err(e) => { ic_cdk::trap(&e.0); }
                }
            }
        },
        quote! {
            unsafe extern "C" fn #items_fn(
                _self_obj: *mut basilisk_cpython::ffi::PyObject,
                _args: *mut basilisk_cpython::ffi::PyObject,
            ) -> *mut basilisk_cpython::ffi::PyObject {
                // Return list of (key, value) tuples
                let interpreter = match INTERPRETER_OPTION.as_mut() {
                    Some(i) => i,
                    None => { ic_cdk::trap("SystemError: missing python interpreter"); }
                };
                let items: Vec<(_, _)> = #map_name.with(|map| {
                    map.borrow().iter().collect()
                });
                let list = basilisk_cpython::ffi::PyList_New(items.len() as basilisk_cpython::ffi::Py_ssize_t);
                if list.is_null() {
                    ic_cdk::trap("Failed to create items list");
                }
                for (i, (key, value)) in items.into_iter().enumerate() {
                    let py_key = match key.try_into_vm_value(()) {
                        Ok(o) => o,
                        Err(e) => { ic_cdk::trap(&e.0); }
                    };
                    let py_value = match value.try_into_vm_value(()) {
                        Ok(o) => o,
                        Err(e) => { ic_cdk::trap(&e.0); }
                    };
                    let tuple = match basilisk_cpython::PyTuple::new(vec![py_key, py_value]) {
                        Ok(t) => t,
                        Err(e) => { ic_cdk::trap(&e.to_rust_err_string()); }
                    };
                    basilisk_cpython::ffi::PyList_SetItem(
                        list,
                        i as basilisk_cpython::ffi::Py_ssize_t,
                        tuple.into_object().into_ptr(),
                    );
                }
                list
            }
        },
    ]
}
