//! CPython IC functions that take no arguments.
//!
//! Each function follows the PyCFunction METH_NOARGS convention:
//! `extern "C" fn(self, Py_None) -> *mut PyObject`

use proc_macro2::TokenStream;
use quote::quote;

pub fn generate() -> TokenStream {
    quote! {
        unsafe extern "C" fn ic_accept_message(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            ic_cdk::api::call::accept_message();
            basilisk_cpython::PyObjectRef::none().into_ptr()
        }

        unsafe extern "C" fn ic_arg_data_raw(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let data = ic_cdk::api::call::arg_data_raw();
            match basilisk_cpython::PyObjectRef::from_bytes(&data) {
                Ok(obj) => obj.into_ptr(),
                Err(_) => core::ptr::null_mut(),
            }
        }

        unsafe extern "C" fn ic_arg_data_raw_size(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let size = ic_cdk::api::call::arg_data_raw_size();
            match basilisk_cpython::PyObjectRef::from_u64(size as u64) {
                Ok(obj) => obj.into_ptr(),
                Err(_) => core::ptr::null_mut(),
            }
        }

        unsafe extern "C" fn ic_caller(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match ic_cdk::api::caller().try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_canister_balance(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match (ic_cdk::api::canister_balance() as u64).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_canister_balance128(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match (ic_cdk::api::canister_balance128() as u64).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_data_certificate(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match ic_cdk::api::data_certificate() {
                Some(cert) => match basilisk_cpython::PyObjectRef::from_bytes(&cert) {
                    Ok(obj) => obj.into_ptr(),
                    Err(_) => core::ptr::null_mut(),
                },
                None => basilisk_cpython::PyObjectRef::none().into_ptr(),
            }
        }

        unsafe extern "C" fn ic_id(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match ic_cdk::api::id().try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_method_name(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match ic_cdk::api::call::method_name().try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_msg_cycles_available(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match (ic_cdk::api::call::msg_cycles_available() as u64).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_msg_cycles_available128(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match (ic_cdk::api::call::msg_cycles_available128() as u64).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_msg_cycles_refunded(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match (ic_cdk::api::call::msg_cycles_refunded() as u64).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_msg_cycles_refunded128(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match (ic_cdk::api::call::msg_cycles_refunded128() as u64).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_reject_code(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match ic_cdk::api::call::reject_code().try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_reject_message(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match ic_cdk::api::call::reject_message().try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_stable_bytes(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let bytes = ic_cdk::api::stable::stable_bytes();
            match basilisk_cpython::PyObjectRef::from_bytes(&bytes) {
                Ok(obj) => obj.into_ptr(),
                Err(_) => core::ptr::null_mut(),
            }
        }

        unsafe extern "C" fn ic_stable_size(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match (ic_cdk::api::stable::stable_size() as u64).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_stable64_size(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match (ic_cdk::api::stable::stable64_size()).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_time(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            _args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            match ic_cdk::api::time().try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }
    }
}
