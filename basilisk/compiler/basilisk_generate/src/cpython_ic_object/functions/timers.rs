//! CPython IC timer functions (set_timer, set_timer_interval).

use proc_macro2::TokenStream;
use quote::quote;

pub fn generate() -> TokenStream {
    quote! {
        unsafe extern "C" fn ic_set_timer(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            // args is a tuple: (delay_seconds, callback_fn)
            let delay_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 0);
            let func_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 1);
            if delay_obj.is_null() || func_obj.is_null() {
                ic_cdk::trap("set_timer: expected (delay, func) arguments");
            }

            let delay_ref = match basilisk_cpython::PyObjectRef::from_borrowed(delay_obj) {
                Some(o) => o,
                None => { ic_cdk::trap("set_timer: null delay argument"); }
            };
            let func_ref = match basilisk_cpython::PyObjectRef::from_borrowed(func_obj) {
                Some(o) => o,
                None => { ic_cdk::trap("set_timer: null func argument"); }
            };

            let delay_secs: u64 = match delay_ref.extract_u64() {
                Ok(v) => v,
                Err(_) => { ic_cdk::trap("set_timer: delay must be an integer"); }
            };
            let delay = core::time::Duration::new(delay_secs, 0);

            let closure = move || {
                let interpreter = match INTERPRETER_OPTION.as_mut() {
                    Some(i) => i,
                    None => { ic_cdk::trap("SystemError: missing python interpreter"); }
                };

                let empty_args = match basilisk_cpython::PyTuple::empty() {
                    Ok(t) => t,
                    Err(_) => { ic_cdk::trap("set_timer: failed to create args tuple"); }
                };
                let py_result = match func_ref.call(&empty_args.into_object(), None) {
                    Ok(r) => r,
                    Err(e) => { ic_cdk::trap(&format!("set_timer callback error: {}", e.to_rust_err_string())); }
                };

                ic_cdk::spawn(async move {
                    let _ = async_result_handler(
                        &py_result,
                        basilisk_cpython::PyObjectRef::none(),
                    ).await;
                });
            };

            let timer_id = ic_cdk_timers::set_timer(delay, closure);
            match timer_id.try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }

        unsafe extern "C" fn ic_set_timer_interval(
            _self_obj: *mut basilisk_cpython::ffi::PyObject,
            args: *mut basilisk_cpython::ffi::PyObject,
        ) -> *mut basilisk_cpython::ffi::PyObject {
            let interval_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 0);
            let func_obj = basilisk_cpython::ffi::PyTuple_GetItem(args, 1);
            if interval_obj.is_null() || func_obj.is_null() {
                ic_cdk::trap("set_timer_interval: expected (interval, func) arguments");
            }

            let interval_ref = match basilisk_cpython::PyObjectRef::from_borrowed(interval_obj) {
                Some(o) => o,
                None => { ic_cdk::trap("set_timer_interval: null interval argument"); }
            };
            let func_ref = match basilisk_cpython::PyObjectRef::from_borrowed(func_obj) {
                Some(o) => o,
                None => { ic_cdk::trap("set_timer_interval: null func argument"); }
            };

            let interval_secs: u64 = match interval_ref.extract_u64() {
                Ok(v) => v,
                Err(_) => { ic_cdk::trap("set_timer_interval: interval must be an integer"); }
            };
            let interval = core::time::Duration::new(interval_secs, 0);

            let closure = move || {
                let interpreter = match INTERPRETER_OPTION.as_mut() {
                    Some(i) => i,
                    None => { ic_cdk::trap("SystemError: missing python interpreter"); }
                };

                let empty_args = match basilisk_cpython::PyTuple::empty() {
                    Ok(t) => t,
                    Err(_) => { ic_cdk::trap("set_timer_interval: failed to create args tuple"); }
                };
                let py_result = match func_ref.call(&empty_args.into_object(), None) {
                    Ok(r) => r,
                    Err(e) => { ic_cdk::trap(&format!("set_timer_interval callback error: {}", e.to_rust_err_string())); }
                };

                ic_cdk::spawn(async move {
                    let _ = async_result_handler(
                        &py_result,
                        basilisk_cpython::PyObjectRef::none(),
                    ).await;
                });
            };

            let timer_id = ic_cdk_timers::set_timer_interval(interval, closure);
            match timer_id.try_into_vm_value(()) {
                Ok(obj) => obj.into_ptr(),
                Err(e) => { ic_cdk::trap(&e.0); }
            }
        }
    }
}
