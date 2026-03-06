//! IC API bindings exposed as the _basilisk_ic CPython module.
//!
//! Each function is a CPython C-API method (PyCFunction) that wraps an IC system call.
//! These are identical for every canister.

use basilisk_cpython::ffi;
use basilisk_cpython::PyObjectRef;
use slotmap::Key as _SlotMapKey;

/// Create the _basilisk_ic Python module with all IC API bindings.
pub fn basilisk_ic_create_module() -> Result<PyObjectRef, basilisk_cpython::PyError> {
    // Method table for the _basilisk_ic module
    static mut METHODS: [ffi::PyMethodDef; 43] = unsafe { core::mem::zeroed() };

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
        add_method!("reply", ic_reply, ffi::METH_O);
        add_method!("stable_grow", ic_stable_grow, ffi::METH_O);
        add_method!("stable_read", ic_stable_read, ffi::METH_VARARGS);
        add_method!("stable_write", ic_stable_write, ffi::METH_VARARGS);
        add_method!("stable64_grow", ic_stable64_grow, ffi::METH_O);
        add_method!("stable64_read", ic_stable64_read, ffi::METH_VARARGS);
        add_method!("stable64_write", ic_stable64_write, ffi::METH_VARARGS);
        add_method!("set_timer", ic_set_timer, ffi::METH_VARARGS);
        add_method!("set_timer_interval", ic_set_timer_interval, ffi::METH_VARARGS);
        add_method!("clear_timer", ic_clear_timer, ffi::METH_O);
        add_method!("call_raw", ic_call_raw, ffi::METH_VARARGS);
        add_method!("call_raw128", ic_call_raw128, ffi::METH_VARARGS);
        add_method!("notify_raw", ic_notify_raw, ffi::METH_VARARGS);
        add_method!("notify_service_call", ic_notify_service_call, ffi::METH_O);

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

/// ic.reply(value) — encode value to Candid using the current method's return type, then reply.
unsafe extern "C" fn ic_reply(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => { ic_cdk::trap("reply: invalid argument"); }
    };
    let return_type = match crate::CURRENT_RETURN_TYPE.as_ref() {
        Some(rt) => rt.clone(),
        None => { ic_cdk::trap("reply: no return type set (not inside a canister method?)"); }
    };
    let result_bytes = crate::method_dispatch::encode_python_to_candid(&obj, &return_type);
    ic_cdk::api::call::reply_raw(&result_bytes);
    PyObjectRef::none().into_ptr()
}

// ─── Stable memory: grow/read/write ──────────────────────────────────────────

unsafe extern "C" fn ic_stable_grow(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => return core::ptr::null_mut(),
    };
    let new_pages: u32 = match obj.extract_u64() {
        Ok(v) => v as u32,
        Err(_) => { ic_cdk::trap("stable_grow: expected int argument"); }
    };
    match ic_cdk::api::stable::stable_grow(new_pages) {
        Ok(old_size) => match PyObjectRef::from_i64(old_size as i64) {
            Ok(obj) => obj.into_ptr(),
            Err(_) => core::ptr::null_mut(),
        },
        Err(_) => match PyObjectRef::from_i64(-1) {
            Ok(obj) => obj.into_ptr(),
            Err(_) => core::ptr::null_mut(),
        },
    }
}

/// ic.stable_read(offset, length) -> bytes
unsafe extern "C" fn ic_stable_read(
    _self: *mut ffi::PyObject,
    args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let args_tuple = match basilisk_cpython::PyTuple::from_object_unchecked(args) {
        Some(t) => t,
        None => { ic_cdk::trap("stable_read: expected tuple args"); }
    };
    if args_tuple.len() != 2 {
        ic_cdk::trap("stable_read: expected 2 arguments (offset, length)");
    }
    let offset = match args_tuple.get_item(0) {
        Some(o) => match o.extract_u64() { Ok(v) => v as u32, Err(_) => { ic_cdk::trap("stable_read: offset must be int"); } },
        None => { ic_cdk::trap("stable_read: missing offset"); }
    };
    let length = match args_tuple.get_item(1) {
        Some(o) => match o.extract_u64() { Ok(v) => v as u32, Err(_) => { ic_cdk::trap("stable_read: length must be int"); } },
        None => { ic_cdk::trap("stable_read: missing length"); }
    };
    let mut buf = vec![0u8; length as usize];
    ic_cdk::api::stable::stable_read(offset, &mut buf);
    match PyObjectRef::from_bytes(&buf) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

/// ic.stable_write(offset, data: bytes)
unsafe extern "C" fn ic_stable_write(
    _self: *mut ffi::PyObject,
    args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let args_tuple = match basilisk_cpython::PyTuple::from_object_unchecked(args) {
        Some(t) => t,
        None => { ic_cdk::trap("stable_write: expected tuple args"); }
    };
    if args_tuple.len() != 2 {
        ic_cdk::trap("stable_write: expected 2 arguments (offset, data)");
    }
    let offset = match args_tuple.get_item(0) {
        Some(o) => match o.extract_u64() { Ok(v) => v as u32, Err(_) => { ic_cdk::trap("stable_write: offset must be int"); } },
        None => { ic_cdk::trap("stable_write: missing offset"); }
    };
    let data = match args_tuple.get_item(1) {
        Some(o) => match o.extract_bytes() { Ok(b) => b, Err(_) => { ic_cdk::trap("stable_write: data must be bytes"); } },
        None => { ic_cdk::trap("stable_write: missing data"); }
    };
    ic_cdk::api::stable::stable_write(offset, &data);
    PyObjectRef::none().into_ptr()
}

unsafe extern "C" fn ic_stable64_grow(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => return core::ptr::null_mut(),
    };
    let new_pages: u64 = match obj.extract_u64() {
        Ok(v) => v,
        Err(_) => { ic_cdk::trap("stable64_grow: expected int argument"); }
    };
    match ic_cdk::api::stable::stable64_grow(new_pages) {
        Ok(old_size) => match PyObjectRef::from_i64(old_size as i64) {
            Ok(obj) => obj.into_ptr(),
            Err(_) => core::ptr::null_mut(),
        },
        Err(_) => match PyObjectRef::from_i64(-1) {
            Ok(obj) => obj.into_ptr(),
            Err(_) => core::ptr::null_mut(),
        },
    }
}

/// ic.stable64_read(offset, length) -> bytes
unsafe extern "C" fn ic_stable64_read(
    _self: *mut ffi::PyObject,
    args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let args_tuple = match basilisk_cpython::PyTuple::from_object_unchecked(args) {
        Some(t) => t,
        None => { ic_cdk::trap("stable64_read: expected tuple args"); }
    };
    if args_tuple.len() != 2 {
        ic_cdk::trap("stable64_read: expected 2 arguments (offset, length)");
    }
    let offset = match args_tuple.get_item(0) {
        Some(o) => match o.extract_u64() { Ok(v) => v, Err(_) => { ic_cdk::trap("stable64_read: offset must be int"); } },
        None => { ic_cdk::trap("stable64_read: missing offset"); }
    };
    let length = match args_tuple.get_item(1) {
        Some(o) => match o.extract_u64() { Ok(v) => v, Err(_) => { ic_cdk::trap("stable64_read: length must be int"); } },
        None => { ic_cdk::trap("stable64_read: missing length"); }
    };
    let mut buf = vec![0u8; length as usize];
    ic_cdk::api::stable::stable64_read(offset, &mut buf);
    match PyObjectRef::from_bytes(&buf) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

/// ic.stable64_write(offset, data: bytes)
unsafe extern "C" fn ic_stable64_write(
    _self: *mut ffi::PyObject,
    args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let args_tuple = match basilisk_cpython::PyTuple::from_object_unchecked(args) {
        Some(t) => t,
        None => { ic_cdk::trap("stable64_write: expected tuple args"); }
    };
    if args_tuple.len() != 2 {
        ic_cdk::trap("stable64_write: expected 2 arguments (offset, data)");
    }
    let offset = match args_tuple.get_item(0) {
        Some(o) => match o.extract_u64() { Ok(v) => v, Err(_) => { ic_cdk::trap("stable64_write: offset must be int"); } },
        None => { ic_cdk::trap("stable64_write: missing offset"); }
    };
    let data = match args_tuple.get_item(1) {
        Some(o) => match o.extract_bytes() { Ok(b) => b, Err(_) => { ic_cdk::trap("stable64_write: data must be bytes"); } },
        None => { ic_cdk::trap("stable64_write: missing data"); }
    };
    ic_cdk::api::stable::stable64_write(offset, &data);
    PyObjectRef::none().into_ptr()
}

// ─── Timers ──────────────────────────────────────────────────────────────────

static mut TIMER_CB_COUNTER: u64 = 0;

/// Resolve a Python callback to a global function name.
/// For named functions, uses their __name__. For lambdas/closures, stores them
/// under a generated unique global name so they can be retrieved later.
unsafe fn resolve_timer_callback(callback: &PyObjectRef) -> String {
    // Try to extract a string name first (if caller passed a string)
    if let Ok(s) = callback.extract_str() {
        return s;
    }
    // Try __name__ — skip if it's "<lambda>" since that's not a real global
    if let Ok(name_obj) = callback.get_attr("__name__") {
        if let Ok(name) = name_obj.extract_str() {
            if name != "<lambda>" {
                return name;
            }
        }
    }
    // Lambda or closure: store under a generated global name
    let id = TIMER_CB_COUNTER;
    TIMER_CB_COUNTER += 1;
    let gen_name = format!("_timer_cb_{}", id);
    let interpreter = crate::INTERPRETER_OPTION.as_mut()
        .expect("SystemError: missing python interpreter");
    interpreter.set_global(&gen_name, callback.clone())
        .unwrap_or_else(|e| {
            ic_cdk::trap(&format!("Failed to store timer callback: {}", e.to_rust_err_string()));
        });
    gen_name
}

/// ic.set_timer(delay_ns, callback) -> timer_id
unsafe extern "C" fn ic_set_timer(
    _self: *mut ffi::PyObject,
    args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let args_tuple = match basilisk_cpython::PyTuple::from_object_unchecked(args) {
        Some(t) => t,
        None => { ic_cdk::trap("set_timer: expected tuple args"); }
    };
    if args_tuple.len() != 2 {
        ic_cdk::trap("set_timer: expected 2 arguments (delay_ns, callback)");
    }
    let delay_ns = match args_tuple.get_item(0) {
        Some(o) => match o.extract_u64() { Ok(v) => v, Err(_) => { ic_cdk::trap("set_timer: delay must be int (nanoseconds)"); } },
        None => { ic_cdk::trap("set_timer: missing delay"); }
    };
    let callback = match args_tuple.get_item(1) {
        Some(o) => o,
        None => { ic_cdk::trap("set_timer: missing callback"); }
    };

    let func_name = resolve_timer_callback(&callback);

    let delay = std::time::Duration::from_nanos(delay_ns);
    let timer_id = ic_cdk_timers::set_timer(delay, move || {
        let interpreter = crate::INTERPRETER_OPTION.as_mut()
            .expect("SystemError: missing python interpreter");
        let py_func = interpreter.get_global(&func_name)
            .unwrap_or_else(|e| {
                ic_cdk::trap(&format!("Timer callback '{}' not found: {}", func_name, e.to_rust_err_string()));
            });
        let empty = basilisk_cpython::PyTuple::new(Vec::new()).unwrap();
        let _ = py_func.call(&empty.into_object(), None);
    });

    // Return timer_id as int
    let id_val = timer_id.data().as_ffi() as u64;
    match PyObjectRef::from_u64(id_val) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

/// ic.set_timer_interval(interval_ns, callback) -> timer_id
unsafe extern "C" fn ic_set_timer_interval(
    _self: *mut ffi::PyObject,
    args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let args_tuple = match basilisk_cpython::PyTuple::from_object_unchecked(args) {
        Some(t) => t,
        None => { ic_cdk::trap("set_timer_interval: expected tuple args"); }
    };
    if args_tuple.len() != 2 {
        ic_cdk::trap("set_timer_interval: expected 2 arguments (interval_ns, callback)");
    }
    let interval_ns = match args_tuple.get_item(0) {
        Some(o) => match o.extract_u64() { Ok(v) => v, Err(_) => { ic_cdk::trap("set_timer_interval: interval must be int (nanoseconds)"); } },
        None => { ic_cdk::trap("set_timer_interval: missing interval"); }
    };
    let callback = match args_tuple.get_item(1) {
        Some(o) => o,
        None => { ic_cdk::trap("set_timer_interval: missing callback"); }
    };

    let func_name = resolve_timer_callback(&callback);

    let interval = std::time::Duration::from_nanos(interval_ns);
    let timer_id = ic_cdk_timers::set_timer_interval(interval, move || {
        let interpreter = crate::INTERPRETER_OPTION.as_mut()
            .expect("SystemError: missing python interpreter");
        let py_func = interpreter.get_global(&func_name)
            .unwrap_or_else(|e| {
                ic_cdk::trap(&format!("Timer callback '{}' not found: {}", func_name, e.to_rust_err_string()));
            });
        let empty = basilisk_cpython::PyTuple::new(Vec::new()).unwrap();
        let _ = py_func.call(&empty.into_object(), None);
    });

    let id_val = timer_id.data().as_ffi() as u64;
    match PyObjectRef::from_u64(id_val) {
        Ok(obj) => obj.into_ptr(),
        Err(_) => core::ptr::null_mut(),
    }
}

/// ic.clear_timer(timer_id)
unsafe extern "C" fn ic_clear_timer(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let obj = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => return core::ptr::null_mut(),
    };
    let id_val: u64 = match obj.extract_u64() {
        Ok(v) => v,
        Err(_) => { ic_cdk::trap("clear_timer: expected int argument"); }
    };
    let key_data = slotmap::KeyData::from_ffi(id_val);
    let timer_id = ic_cdk_timers::TimerId::from(key_data);
    ic_cdk_timers::clear_timer(timer_id);
    PyObjectRef::none().into_ptr()
}

// ─── Cross-canister calls ────────────────────────────────────────────────────

/// ic.call_raw(canister_id: Principal, method: str, args_raw: bytes, cycles: int) -> bytes
/// Returns a future-like that resolves to the raw Candid response bytes.
/// For now, this is synchronous (blocking) since CPython doesn't support IC async natively.
unsafe extern "C" fn ic_call_raw(
    _self: *mut ffi::PyObject,
    args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let args_tuple = match basilisk_cpython::PyTuple::from_object_unchecked(args) {
        Some(t) => t,
        None => { ic_cdk::trap("call_raw: expected tuple args"); }
    };
    if args_tuple.len() < 3 {
        ic_cdk::trap("call_raw: expected at least 3 arguments (canister_id, method, args_raw)");
    }
    // For now, trap with a clear message — async cross-canister calls require generator/async support
    ic_cdk::trap("call_raw: cross-canister calls are not yet supported in CPython mode. This requires async/generator support (Tier 2).");
}

/// ic.call_raw128 — same as call_raw but with 128-bit cycles
unsafe extern "C" fn ic_call_raw128(
    _self: *mut ffi::PyObject,
    _args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    ic_cdk::trap("call_raw128: cross-canister calls are not yet supported in CPython mode. This requires async/generator support (Tier 2).");
}

/// ic.notify_raw(canister_id, method, args_raw, cycles=0) -> NotifyResult
/// Fire-and-forget notification — no response expected.
/// Returns {"Ok": None} on success, {"Err": <RejectionCode>} on failure.
unsafe extern "C" fn ic_notify_raw(
    _self: *mut ffi::PyObject,
    args: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let args_tuple = match basilisk_cpython::PyTuple::from_object_unchecked(args) {
        Some(t) => t,
        None => { ic_cdk::trap("notify_raw: expected tuple args"); }
    };
    if args_tuple.len() < 3 {
        ic_cdk::trap("notify_raw: expected at least 3 arguments (canister_id, method, args_raw)");
    }

    // Extract canister_id (Principal)
    let canister_id_obj = args_tuple.get_item(0).unwrap_or_else(|| {
        ic_cdk::trap("notify_raw: missing canister_id");
    });
    let canister_id_str = if let Ok(to_str) = canister_id_obj.get_attr("to_str") {
        let empty_args = basilisk_cpython::PyTuple::empty().unwrap_or_else(|_| {
            ic_cdk::trap("notify_raw: failed to create empty args");
        });
        let result = to_str.call(&empty_args.into_object(), None).unwrap_or_else(|e| {
            ic_cdk::trap(&format!("notify_raw: to_str failed: {}", e.to_rust_err_string()));
        });
        result.extract_str().unwrap_or_else(|e| {
            ic_cdk::trap(&format!("notify_raw: to_str not string: {}", e.to_rust_err_string()));
        })
    } else {
        canister_id_obj.extract_str().unwrap_or_else(|e| {
            ic_cdk::trap(&format!("notify_raw: canister_id not string: {}", e.to_rust_err_string()));
        })
    };
    let principal = candid::Principal::from_text(&canister_id_str).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("notify_raw: invalid principal '{}': {}", canister_id_str, e));
    });

    // Extract method name
    let method_obj = args_tuple.get_item(1).unwrap_or_else(|| {
        ic_cdk::trap("notify_raw: missing method");
    });
    let method = method_obj.extract_str().unwrap_or_else(|e| {
        ic_cdk::trap(&format!("notify_raw: method not string: {}", e.to_rust_err_string()));
    });

    // Extract args_raw (bytes)
    let args_raw_obj = args_tuple.get_item(2).unwrap_or_else(|| {
        ic_cdk::trap("notify_raw: missing args_raw");
    });
    let args_raw = args_raw_obj.extract_bytes().unwrap_or_else(|e| {
        ic_cdk::trap(&format!("notify_raw: args_raw not bytes: {}", e.to_rust_err_string()));
    });

    // Extract cycles (optional, default 0)
    let cycles: u128 = if args_tuple.len() > 3 {
        if let Some(c) = args_tuple.get_item(3) {
            c.extract_u64().unwrap_or(0) as u128
        } else {
            0
        }
    } else {
        0
    };

    // Call ic_cdk notify_raw
    let result = ic_cdk::api::call::notify_raw(principal, &method, &args_raw, cycles);

    // Build result dict: {"Ok": None} or {"Err": <rejection_code_str>}
    let dict = basilisk_cpython::PyDict::new().unwrap_or_else(|e| {
        ic_cdk::trap(&format!("notify_raw: failed to create dict: {}", e.to_rust_err_string()));
    });

    match result {
        Ok(()) => {
            dict.set_item_str("Ok", &PyObjectRef::none()).unwrap_or_else(|e| {
                ic_cdk::trap(&format!("notify_raw: set Ok failed: {}", e.to_rust_err_string()));
            });
        }
        Err(reject_code) => {
            let code_str = match reject_code {
                ic_cdk::api::call::RejectionCode::NoError => "NoError",
                ic_cdk::api::call::RejectionCode::SysFatal => "SysFatal",
                ic_cdk::api::call::RejectionCode::SysTransient => "SysTransient",
                ic_cdk::api::call::RejectionCode::DestinationInvalid => "DestinationInvalid",
                ic_cdk::api::call::RejectionCode::CanisterReject => "CanisterReject",
                ic_cdk::api::call::RejectionCode::CanisterError => "CanisterError",
                _ => "Unknown",
            };
            // Return as variant dict: {"Err": {"SysFatal": None}} etc.
            let inner_dict = basilisk_cpython::PyDict::new().unwrap_or_else(|e| {
                ic_cdk::trap(&format!("notify_raw: inner dict: {}", e.to_rust_err_string()));
            });
            inner_dict.set_item_str(code_str, &PyObjectRef::none()).unwrap_or_else(|e| {
                ic_cdk::trap(&format!("notify_raw: set code: {}", e.to_rust_err_string()));
            });
            dict.set_item_str("Err", &inner_dict.into_object()).unwrap_or_else(|e| {
                ic_cdk::trap(&format!("notify_raw: set Err failed: {}", e.to_rust_err_string()));
            });
        }
    }

    dict.into_object().into_ptr()
}

/// _basilisk_ic.notify_service_call(service_call) -> NotifyResult dict
/// Takes a _ServiceCall object, encodes its args, and sends a one-way notification.
unsafe extern "C" fn ic_notify_service_call(
    _self: *mut ffi::PyObject,
    arg: *mut ffi::PyObject,
) -> *mut ffi::PyObject {
    let service_call = match PyObjectRef::from_borrowed(arg) {
        Some(o) => o,
        None => { ic_cdk::trap("notify_service_call: invalid argument"); }
    };

    // Extract principal text
    let py_principal = service_call.get_attr("canister_principal").unwrap_or_else(|e| {
        ic_cdk::trap(&format!("notify_service_call: missing canister_principal: {}", e.to_rust_err_string()));
    });
    let principal_text = py_principal
        .get_attr("_text")
        .and_then(|t| t.extract_str())
        .unwrap_or_else(|e| {
            ic_cdk::trap(&format!("notify_service_call: cannot extract principal text: {}", e.to_rust_err_string()));
        });
    let principal = candid::Principal::from_text(&principal_text).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("notify_service_call: invalid principal '{}': {}", principal_text, e));
    });

    // Extract method name
    let method_name = service_call.get_attr("method_name")
        .and_then(|m| m.extract_str())
        .unwrap_or_else(|e| {
            ic_cdk::trap(&format!("notify_service_call: missing method_name: {}", e.to_rust_err_string()));
        });

    // Extract payment (default 0)
    let payment = service_call.get_attr("payment")
        .and_then(|p| p.extract_u64())
        .unwrap_or(0u64) as u128;

    // Encode args using the same logic as method_dispatch::encode_service_call_args
    let args_raw = crate::method_dispatch::encode_service_call_args(&service_call);

    // Send notification
    let result = ic_cdk::api::call::notify_raw(principal, &method_name, &args_raw, payment);

    // Build result dict
    let dict = basilisk_cpython::PyDict::new().unwrap_or_else(|e| {
        ic_cdk::trap(&format!("notify_service_call: dict: {}", e.to_rust_err_string()));
    });

    match result {
        Ok(()) => {
            dict.set_item_str("Ok", &PyObjectRef::none()).unwrap_or_else(|e| {
                ic_cdk::trap(&format!("notify_service_call: set Ok: {}", e.to_rust_err_string()));
            });
        }
        Err(reject_code) => {
            let code_str = match reject_code {
                ic_cdk::api::call::RejectionCode::NoError => "NoError",
                ic_cdk::api::call::RejectionCode::SysFatal => "SysFatal",
                ic_cdk::api::call::RejectionCode::SysTransient => "SysTransient",
                ic_cdk::api::call::RejectionCode::DestinationInvalid => "DestinationInvalid",
                ic_cdk::api::call::RejectionCode::CanisterReject => "CanisterReject",
                ic_cdk::api::call::RejectionCode::CanisterError => "CanisterError",
                _ => "Unknown",
            };
            let inner_dict = basilisk_cpython::PyDict::new().unwrap_or_else(|e| {
                ic_cdk::trap(&format!("notify_service_call: inner dict: {}", e.to_rust_err_string()));
            });
            inner_dict.set_item_str(code_str, &PyObjectRef::none()).unwrap_or_else(|e| {
                ic_cdk::trap(&format!("notify_service_call: set code: {}", e.to_rust_err_string()));
            });
            dict.set_item_str("Err", &inner_dict.into_object()).unwrap_or_else(|e| {
                ic_cdk::trap(&format!("notify_service_call: set Err: {}", e.to_rust_err_string()));
            });
        }
    }

    dict.into_object().into_ptr()
}
