//! IC API bindings exposed as the _basilisk_ic CPython module.
//!
//! Each function is a CPython C-API method (PyCFunction) that wraps an IC system call.
//! These are identical for every canister.

use basilisk_cpython::ffi;
use basilisk_cpython::PyObjectRef;

/// Create the _basilisk_ic Python module with all IC API bindings.
pub fn basilisk_ic_create_module() -> Result<PyObjectRef, basilisk_cpython::PyError> {
    // Method table for the _basilisk_ic module
    static mut METHODS: [ffi::PyMethodDef; 30] = unsafe { core::mem::zeroed() };

    unsafe {
        let methods = &mut METHODS;
        let mut i = 0;

        macro_rules! add_method {
            ($name:expr, $func:ident, $flags:expr) => {
                methods[i] = ffi::PyMethodDef {
                    ml_name: concat!($name, "\0").as_ptr() as *const core::ffi::c_char,
                    ml_meth: Some($func),
                    ml_flags: $flags,
                    ml_doc: core::ptr::null(),
                };
                i += 1;
            };
        }

        add_method!("accept_message", ic_accept_message, ffi::METH_NOARGS);
        add_method!("arg_data_raw", ic_arg_data_raw, ffi::METH_NOARGS);
        add_method!("arg_data_raw_size", ic_arg_data_raw_size, ffi::METH_NOARGS);
        add_method!("caller", ic_caller, ffi::METH_NOARGS);
        add_method!("canister_balance", ic_canister_balance, ffi::METH_NOARGS);
        add_method!("canister_balance128", ic_canister_balance128, ffi::METH_NOARGS);
        add_method!("data_certificate", ic_data_certificate, ffi::METH_NOARGS);
        add_method!("id", ic_id, ffi::METH_NOARGS);
        add_method!("method_name", ic_method_name, ffi::METH_NOARGS);
        add_method!("msg_cycles_available", ic_msg_cycles_available, ffi::METH_NOARGS);
        add_method!("msg_cycles_available128", ic_msg_cycles_available128, ffi::METH_NOARGS);
        add_method!("msg_cycles_refunded", ic_msg_cycles_refunded, ffi::METH_NOARGS);
        add_method!("msg_cycles_refunded128", ic_msg_cycles_refunded128, ffi::METH_NOARGS);
        add_method!("reject_code", ic_reject_code, ffi::METH_NOARGS);
        add_method!("reject_message", ic_reject_message, ffi::METH_NOARGS);
        add_method!("stable_bytes", ic_stable_bytes, ffi::METH_NOARGS);
        add_method!("stable_size", ic_stable_size, ffi::METH_NOARGS);
        add_method!("stable64_size", ic_stable64_size, ffi::METH_NOARGS);
        add_method!("time", ic_time, ffi::METH_NOARGS);
        add_method!("candid_decode", ic_candid_decode, ffi::METH_O);
        add_method!("candid_encode", ic_candid_encode, ffi::METH_O);
        add_method!("msg_cycles_accept", ic_msg_cycles_accept, ffi::METH_O);
        add_method!("msg_cycles_accept128", ic_msg_cycles_accept128, ffi::METH_O);
        add_method!("performance_counter", ic_performance_counter, ffi::METH_O);
        add_method!("print", ic_print, ffi::METH_O);
        add_method!("reject", ic_reject, ffi::METH_O);
        add_method!("reply_raw", ic_reply_raw, ffi::METH_O);
        add_method!("set_certified_data", ic_set_certified_data, ffi::METH_O);
        add_method!("trap", ic_trap, ffi::METH_O);

        // Sentinel (null terminator)
        methods[i] = core::mem::zeroed();

        // Create module
        static mut MODULE_DEF: ffi::PyModuleDef = unsafe { core::mem::zeroed() };
        MODULE_DEF.m_base = ffi::PyModuleDef_HEAD_INIT;
        MODULE_DEF.m_name = b"_basilisk_ic\0".as_ptr() as *const core::ffi::c_char;
        MODULE_DEF.m_doc = core::ptr::null();
        MODULE_DEF.m_size = -1;
        MODULE_DEF.m_methods = METHODS.as_mut_ptr();

        let module = ffi::PyModule_Create(&mut MODULE_DEF as *mut ffi::PyModuleDef);
        if module.is_null() {
            return Err(basilisk_cpython::PyError::new(
                "SystemError",
                "Failed to create _basilisk_ic module",
            ));
        }

        // Register in sys.modules via Python code
        let sys_import = ffi::PyImport_ImportModule(
            b"sys\0".as_ptr() as *const core::ffi::c_char,
        );
        if !sys_import.is_null() {
            let modules = ffi::PyObject_GetAttrString(
                sys_import,
                b"modules\0".as_ptr() as *const core::ffi::c_char,
            );
            if !modules.is_null() {
                ffi::PyDict_SetItemString(
                    modules,
                    b"_basilisk_ic\0".as_ptr() as *const core::ffi::c_char,
                    module,
                );
                ffi::Py_DecRef(modules);
            }
            ffi::Py_DecRef(sys_import);
        }

        PyObjectRef::from_owned(module)
            .ok_or_else(|| basilisk_cpython::PyError::new("SystemError", "null module"))
    }
}

// ─── IC API C functions ─────────────────────────────────────────────────────

unsafe extern "C" fn ic_accept_message(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    ic_cdk::api::call::accept_message();
    PyObjectRef::none().into_ptr()
}

unsafe extern "C" fn ic_arg_data_raw(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let data = ic_cdk::api::call::arg_data_raw();
    match PyObjectRef::from_bytes(&data) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_arg_data_raw_size(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let size = ic_cdk::api::call::arg_data_raw_size();
    match PyObjectRef::from_u64(size as u64) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_caller(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let principal = ic_cdk::api::caller();
    let text = principal.to_text();
    let principal_class = match crate::PRINCIPAL_CLASS_OPTION.as_ref() {
        Some(c) => c,
        None => {
            // Fallback: return as string
            match PyObjectRef::from_str(&text) {
                Ok(obj) => return obj.into_ptr(),
                Err(_) => return core::ptr::null_mut(),
            }
        }
    };
    let from_str = match principal_class.get_attr("from_str") {
        Ok(f) => f,
        Err(_) => return core::ptr::null_mut(),
    };
    let text_obj = match PyObjectRef::from_str(&text) {
        Ok(o) => o,
        Err(_) => return core::ptr::null_mut(),
    };
    let args = match basilisk_cpython::PyTuple::new(vec![text_obj]) {
        Ok(a) => a,
        Err(_) => return core::ptr::null_mut(),
    };
    match from_str.call(&args.into_object(), None) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_canister_balance(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match PyObjectRef::from_u64(ic_cdk::api::canister_balance() as u64) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_canister_balance128(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match PyObjectRef::from_u64(ic_cdk::api::canister_balance128() as u64) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_data_certificate(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match ic_cdk::api::data_certificate() {
        Some(cert) => match PyObjectRef::from_bytes(&cert) {
            Ok(obj) => obj.into_ptr(),
            Err(_) => core::ptr::null_mut(),
        },
        None => PyObjectRef::none().into_ptr(),
    }
}

unsafe extern "C" fn ic_id(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let principal = ic_cdk::api::id();
    let text = principal.to_text();
    let principal_class = match crate::PRINCIPAL_CLASS_OPTION.as_ref() {
        Some(c) => c,
        None => match PyObjectRef::from_str(&text) {
            Ok(obj) => return obj.into_ptr(),
            Err(_) => return core::ptr::null_mut(),
        },
    };
    let from_str = match principal_class.get_attr("from_str") {
        Ok(f) => f,
        Err(_) => return core::ptr::null_mut(),
    };
    let text_obj = match PyObjectRef::from_str(&text) {
        Ok(o) => o,
        Err(_) => return core::ptr::null_mut(),
    };
    let args = match basilisk_cpython::PyTuple::new(vec![text_obj]) {
        Ok(a) => a,
        Err(_) => return core::ptr::null_mut(),
    };
    match from_str.call(&args.into_object(), None) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_method_name(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match PyObjectRef::from_str(&ic_cdk::api::call::method_name()) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_msg_cycles_available(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match PyObjectRef::from_u64(ic_cdk::api::call::msg_cycles_available() as u64) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_msg_cycles_available128(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match PyObjectRef::from_u64(ic_cdk::api::call::msg_cycles_available128() as u64) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_msg_cycles_refunded(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match PyObjectRef::from_u64(ic_cdk::api::call::msg_cycles_refunded() as u64) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_msg_cycles_refunded128(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match PyObjectRef::from_u64(ic_cdk::api::call::msg_cycles_refunded128() as u64) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_reject_code(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let code = ic_cdk::api::call::reject_code();
    let attribute = match code {
        ic_cdk::api::call::RejectionCode::NoError => "NoError",
        ic_cdk::api::call::RejectionCode::SysFatal => "SysFatal",
        ic_cdk::api::call::RejectionCode::SysTransient => "SysTransient",
        ic_cdk::api::call::RejectionCode::DestinationInvalid => "DestinationInvalid",
        ic_cdk::api::call::RejectionCode::CanisterReject => "CanisterReject",
        ic_cdk::api::call::RejectionCode::CanisterError => "CanisterError",
        ic_cdk::api::call::RejectionCode::Unknown => "Unknown",
    };
    match basilisk_cpython::PyDict::new() {
        Ok(dict) => {
            let none = PyObjectRef::none();
            let _ = dict.set_item_str(attribute, &none);
            dict.into_object().into_ptr()
        }
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_reject_message(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match PyObjectRef::from_str(&ic_cdk::api::call::reject_message()) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_stable_bytes(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let bytes = ic_cdk::api::stable::stable_bytes();
    match PyObjectRef::from_bytes(&bytes) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_stable_size(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match PyObjectRef::from_u64(ic_cdk::api::stable::stable_size() as u64) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_stable64_size(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match PyObjectRef::from_u64(ic_cdk::api::stable::stable64_size()) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_time(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    match PyObjectRef::from_u64(ic_cdk::api::time()) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_candid_decode(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => return core::ptr::null_mut(),
    };
    let bytes: Vec<u8> = match obj.extract_bytes() {
        Ok(b) => b,
        Err(_) => { ic_cdk::trap("candid_decode: expected bytes argument"); }
    };
    match candid::IDLArgs::from_bytes(&bytes) {
        Ok(args) => {
            let s = format!("{}", args);
            match PyObjectRef::from_str(&s) {
                Ok(obj) => obj.into_ptr(),
                Err(_) => core::ptr::null_mut(),
            }
        }
        Err(e) => { ic_cdk::trap(&format!("candid_decode error: {}", e)); }
    }
}

unsafe extern "C" fn ic_candid_encode(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => return core::ptr::null_mut(),
    };
    let s: String = match obj.extract_str() {
        Ok(s) => s,
        Err(_) => { ic_cdk::trap("candid_encode: expected string argument"); }
    };
    match candid_parser::parse_idl_args(&s) {
        Ok(args) => {
            let bytes = args.to_bytes().unwrap_or_default();
            match PyObjectRef::from_bytes(&bytes) {
                Ok(obj) => obj.into_ptr(),
                Err(_) => core::ptr::null_mut(),
            }
        }
        Err(e) => { ic_cdk::trap(&format!("candid_encode error: {}", e)); }
    }
}

unsafe extern "C" fn ic_msg_cycles_accept(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => return core::ptr::null_mut(),
    };
    let max_amount: u64 = match obj.extract_u64() {
        Ok(v) => v,
        Err(_) => { ic_cdk::trap("msg_cycles_accept: expected int argument"); }
    };
    let accepted = ic_cdk::api::call::msg_cycles_accept(max_amount);
    match PyObjectRef::from_u64(accepted as u64) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_msg_cycles_accept128(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => return core::ptr::null_mut(),
    };
    let max_amount: u64 = match obj.extract_u64() {
        Ok(v) => v,
        Err(_) => { ic_cdk::trap("msg_cycles_accept128: expected int argument"); }
    };
    let accepted = ic_cdk::api::call::msg_cycles_accept128(max_amount as u128);
    match PyObjectRef::from_u64(accepted as u64) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_performance_counter(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => return core::ptr::null_mut(),
    };
    let counter_type: u32 = match obj.extract_u64() {
        Ok(v) => v as u32,
        Err(_) => { ic_cdk::trap("performance_counter: expected int argument"); }
    };
    let count = ic_cdk::api::performance_counter(counter_type);
    match PyObjectRef::from_u64(count) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

unsafe extern "C" fn ic_print(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
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
    PyObjectRef::none().into_ptr()
}

unsafe extern "C" fn ic_reject(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => return core::ptr::null_mut(),
    };
    let message: String = match obj.extract_str() {
        Ok(s) => s,
        Err(_) => { ic_cdk::trap("reject: expected string argument"); }
    };
    ic_cdk::api::call::reject(&message);
    PyObjectRef::none().into_ptr()
}

unsafe extern "C" fn ic_reply_raw(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => return core::ptr::null_mut(),
    };
    let bytes: Vec<u8> = match obj.extract_bytes() {
        Ok(b) => b,
        Err(_) => { ic_cdk::trap("reply_raw: expected bytes argument"); }
    };
    ic_cdk::api::call::reply_raw(&bytes);
    PyObjectRef::none().into_ptr()
}

unsafe extern "C" fn ic_set_certified_data(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => return core::ptr::null_mut(),
    };
    let data: Vec<u8> = match obj.extract_bytes() {
        Ok(b) => b,
        Err(_) => { ic_cdk::trap("set_certified_data: expected bytes argument"); }
    };
    ic_cdk::api::set_certified_data(&data);
    PyObjectRef::none().into_ptr()
}

unsafe extern "C" fn ic_trap(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => { ic_cdk::trap("trap: invalid argument"); }
    };
    let message: String = match obj.extract_str() {
        Ok(s) => s,
        Err(_) => "trap called with non-string argument".to_string(),
    };
    ic_cdk::trap(&message);
}
