//! CPython IC stable memory functions.

use proc_macro2::TokenStream;
use quote::quote;

pub fn generate() -> TokenStream {
    quote! {
        unsafe extern "C" fn ic_stable_grow(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let new_pages: u32 = match obj.extract_u64() {
                Ok(v) => v as u32,
                Err(_) => { ic_cdk::trap("stable_grow: expected int argument"); }
            };
            match ic_cdk::api::stable::stable_grow(new_pages).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_stable_read(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let offset_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 0);
            let length_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 1);
            if offset_obj.is_null() || length_obj.is_null() {
                ic_cdk::trap("stable_read: expected (offset, length) arguments");
            }
            let offset_ref = basilisk_cpython::PyObjectRef::from_borrowed(offset_obj).unwrap();
            let length_ref = basilisk_cpython::PyObjectRef::from_borrowed(length_obj).unwrap();
            let offset: u32 = offset_ref.extract_u64().unwrap_or_trap() as u32;
            let length: u32 = length_ref.extract_u64().unwrap_or_trap() as u32;
            let mut buf: Vec<u8> = vec![0; length as usize];
            ic_cdk::api::stable::stable_read(offset, &mut buf);
            match basilisk_cpython::PyObjectRef::from_bytes(&buf) {
                Ok(obj) => obj.into_ptr(),
                Err(_) => core::ptr::null_mut(),
            }
        }

        unsafe extern "C" fn ic_stable_write(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let offset_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 0);
            let buf_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 1);
            if offset_obj.is_null() || buf_obj.is_null() {
                ic_cdk::trap("stable_write: expected (offset, buf) arguments");
            }
            let offset_ref = basilisk_cpython::PyObjectRef::from_borrowed(offset_obj).unwrap();
            let buf_ref = basilisk_cpython::PyObjectRef::from_borrowed(buf_obj).unwrap();
            let offset: u32 = offset_ref.extract_u64().unwrap_or_trap() as u32;
            let buf: Vec<u8> = buf_ref.extract_bytes().unwrap_or_trap();
            ic_cdk::api::stable::stable_write(offset, &buf);
            basilisk_cpython::PyObjectRef::none().into_ptr()
        }

        unsafe extern "C" fn ic_stable64_grow(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let new_pages: u64 = match obj.extract_u64() {
                Ok(v) => v,
                Err(_) => { ic_cdk::trap("stable64_grow: expected int argument"); }
            };
            match ic_cdk::api::stable::stable64_grow(new_pages).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_stable64_read(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let offset_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 0);
            let length_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 1);
            if offset_obj.is_null() || length_obj.is_null() {
                ic_cdk::trap("stable64_read: expected (offset, length) arguments");
            }
            let offset_ref = basilisk_cpython::PyObjectRef::from_borrowed(offset_obj).unwrap();
            let length_ref = basilisk_cpython::PyObjectRef::from_borrowed(length_obj).unwrap();
            let offset: u64 = offset_ref.extract_u64().unwrap_or_trap();
            let length: u64 = length_ref.extract_u64().unwrap_or_trap();
            let mut buf: Vec<u8> = vec![0; length as usize];
            ic_cdk::api::stable::stable64_read(offset, &mut buf);
            match basilisk_cpython::PyObjectRef::from_bytes(&buf) {
                Ok(obj) => obj.into_ptr(),
                Err(_) => core::ptr::null_mut(),
            }
        }

        unsafe extern "C" fn ic_stable64_write(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let offset_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 0);
            let buf_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 1);
            if offset_obj.is_null() || buf_obj.is_null() {
                ic_cdk::trap("stable64_write: expected (offset, buf) arguments");
            }
            let offset_ref = basilisk_cpython::PyObjectRef::from_borrowed(offset_obj).unwrap();
            let buf_ref = basilisk_cpython::PyObjectRef::from_borrowed(buf_obj).unwrap();
            let offset: u64 = offset_ref.extract_u64().unwrap_or_trap();
            let buf: Vec<u8> = buf_ref.extract_bytes().unwrap_or_trap();
            ic_cdk::api::stable::stable64_write(offset, &buf);
            basilisk_cpython::PyObjectRef::none().into_ptr()
        }
    }
}
