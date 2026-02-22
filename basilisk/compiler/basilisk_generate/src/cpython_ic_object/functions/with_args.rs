//! CPython IC functions that take one or more arguments.

use proc_macro2::TokenStream;
use quote::quote;

pub fn generate() -> TokenStream {
    quote! {
        unsafe extern "C" fn ic_candid_decode(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let bytes: Vec<u8> = match obj.extract_bytes() {
                Ok(b) => b,
                Err(_) => { ic_cdk::trap("candid_decode: expected bytes argument"); }
            };
            let interpreter = match INTERPRETER_OPTION.as_mut() {
                Some(i) => i,
                None => { ic_cdk::trap("SystemError: missing python interpreter"); }
            };
            // Decode candid bytes to Python string representation
            match candid::IDLArgs::from_bytes(&bytes) {
                Ok(args) => {
                    let s = format!("{}", args);
                    match basilisk_cpython::PyObjectRef::from_str(&s) {
                        Ok(obj) => obj.into_ptr(),
                        Err(_) => core::ptr::null_mut(),
                    }
                }
                Err(e) => { ic_cdk::trap(&format!("candid_decode error: {}", e)); }
            }
        }

        unsafe extern "C" fn ic_candid_encode(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let s: String = match obj.extract_str() {
                Ok(s) => s,
                Err(_) => { ic_cdk::trap("candid_encode: expected string argument"); }
            };
            match s.parse::<candid::IDLArgs>() {
                Ok(args) => {
                    let bytes = args.to_bytes().unwrap_or_default();
                    match basilisk_cpython::PyObjectRef::from_bytes(&bytes) {
                        Ok(obj) => obj.into_ptr(),
                        Err(_) => core::ptr::null_mut(),
                    }
                }
                Err(e) => { ic_cdk::trap(&format!("candid_encode error: {}", e)); }
            }
        }

        unsafe extern "C" fn ic_msg_cycles_accept(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let max_amount: u64 = match obj.extract_u64() {
                Ok(v) => v,
                Err(_) => { ic_cdk::trap("msg_cycles_accept: expected int argument"); }
            };
            let accepted = ic_cdk::api::call::msg_cycles_accept(max_amount);
            match (accepted as u64).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_msg_cycles_accept128(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let max_amount: u64 = match obj.extract_u64() {
                Ok(v) => v,
                Err(_) => { ic_cdk::trap("msg_cycles_accept128: expected int argument"); }
            };
            let accepted = ic_cdk::api::call::msg_cycles_accept128(max_amount as u128);
            match (accepted as u64).try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_performance_counter(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let counter_type: u32 = match obj.extract_u64() {
                Ok(v) => v as u32,
                Err(_) => { ic_cdk::trap("performance_counter: expected int argument"); }
            };
            let count = ic_cdk::api::performance_counter(counter_type);
            match count.try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_print(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let s: String = match obj.extract_str() {
                Ok(s) => s,
                Err(_) => match obj.str_repr() {
                    Ok(s) => s,
                    Err(_) => "<unprintable>".to_string(),
                },
            };
            ic_cdk::println!("{}", s);
            basilisk_cpython::PyObjectRef::none().into_ptr()
        }

        unsafe extern "C" fn ic_reject(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let message: String = match obj.extract_str() {
                Ok(s) => s,
                Err(_) => { ic_cdk::trap("reject: expected string argument"); }
            };
            ic_cdk::api::call::reject(&message);
            basilisk_cpython::PyObjectRef::none().into_ptr()
        }

        unsafe extern "C" fn ic_reply_raw(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let bytes: Vec<u8> = match obj.extract_bytes() {
                Ok(b) => b,
                Err(_) => { ic_cdk::trap("reply_raw: expected bytes argument"); }
            };
            ic_cdk::api::call::reply_raw(&bytes);
            basilisk_cpython::PyObjectRef::none().into_ptr()
        }

        unsafe extern "C" fn ic_set_certified_data(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let data: Vec<u8> = match obj.extract_bytes() {
                Ok(b) => b,
                Err(_) => { ic_cdk::trap("set_certified_data: expected bytes argument"); }
            };
            ic_cdk::api::set_certified_data(&data);
            basilisk_cpython::PyObjectRef::none().into_ptr()
        }

        unsafe extern "C" fn ic_trap(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => { ic_cdk::trap("trap: invalid argument"); }
            };
            let message: String = match obj.extract_str() {
                Ok(s) => s,
                Err(_) => "trap called with non-string argument".to_string(),
            };
            ic_cdk::api::trap(&message)
        }

        unsafe extern "C" fn ic_clear_timer(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            arg: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let obj = match basilisk_cpython::PyObjectRef::from_borrowed(arg) {
                Some(o) => o,
                None => return core::ptr::null_mut(),
            };
            let timer_id_u64: u64 = match obj.extract_u64() {
                Ok(v) => v,
                Err(_) => { ic_cdk::trap("clear_timer: expected int argument"); }
            };
            let timer_id = ic_cdk_timers::TimerId::from(slotmap::KeyData::from_ffi(timer_id_u64));
            ic_cdk_timers::clear_timer(timer_id);
            basilisk_cpython::PyObjectRef::none().into_ptr()
        }
    }
}
