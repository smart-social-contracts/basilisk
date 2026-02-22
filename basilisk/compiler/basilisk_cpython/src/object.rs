//! Safe wrapper around CPython's PyObject*.
//!
//! PyObjectRef provides RAII-based reference counting and safe access
//! to CPython object operations. It mirrors the role of
//! `rustpython::vm::PyObjectRef` in the current codebase.

use crate::ffi;
use core::ffi::{c_char, c_int};
use core::fmt;
use core::ptr;

/// A reference-counted wrapper around a CPython `PyObject*`.
///
/// Automatically calls `Py_DecRef` on drop. Equivalent to RustPython's `PyObjectRef`.
pub struct PyObjectRef {
    ptr: *mut ffi::PyObject,
}

// CPython objects are not Send/Sync in general, but on wasm32 (single-threaded) this is fine.
// The IC canister runtime is single-threaded.
unsafe impl Send for PyObjectRef {}
unsafe impl Sync for PyObjectRef {}

impl PyObjectRef {
    /// Create a new PyObjectRef from a raw pointer.
    ///
    /// # Safety
    /// The pointer must be a valid, non-null PyObject* with an owned reference
    /// (i.e., the caller has already incremented the refcount or is transferring ownership).
    pub unsafe fn from_owned(ptr: *mut ffi::PyObject) -> Option<Self> {
        if ptr.is_null() {
            None
        } else {
            Some(PyObjectRef { ptr })
        }
    }

    /// Create a PyObjectRef from a borrowed reference (increments refcount).
    ///
    /// # Safety
    /// The pointer must be a valid, non-null PyObject*.
    pub unsafe fn from_borrowed(ptr: *mut ffi::PyObject) -> Option<Self> {
        if ptr.is_null() {
            None
        } else {
            ffi::Py_IncRef(ptr);
            Some(PyObjectRef { ptr })
        }
    }

    /// Get the raw pointer (does not transfer ownership).
    pub fn as_ptr(&self) -> *mut ffi::PyObject {
        self.ptr
    }

    /// Consume self and return the raw pointer without decrementing refcount.
    pub fn into_ptr(self) -> *mut ffi::PyObject {
        let ptr = self.ptr;
        core::mem::forget(self);
        ptr
    }

    // === Attribute access ===

    /// Get an attribute by name. Equivalent to `getattr(obj, name)`.
    pub fn get_attr(&self, name: &str) -> Result<PyObjectRef, PyError> {
        let c_name = CString::new(name);
        unsafe {
            let result = ffi::PyObject_GetAttrString(self.ptr, c_name.as_ptr());
            if result.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef { ptr: result })
            }
        }
    }

    /// Set an attribute by name. Equivalent to `setattr(obj, name, value)`.
    pub fn set_attr(&self, name: &str, value: &PyObjectRef) -> Result<(), PyError> {
        let c_name = CString::new(name);
        unsafe {
            let result = ffi::PyObject_SetAttrString(self.ptr, c_name.as_ptr(), value.ptr);
            if result < 0 {
                Err(PyError::fetch())
            } else {
                Ok(())
            }
        }
    }

    /// Check if object has an attribute.
    pub fn has_attr(&self, name: &str) -> bool {
        let c_name = CString::new(name);
        unsafe { ffi::PyObject_HasAttrString(self.ptr, c_name.as_ptr()) != 0 }
    }

    // === Call protocol ===

    /// Call this object with positional args (tuple) and optional kwargs (dict).
    pub fn call(
        &self,
        args: &PyObjectRef,
        kwargs: Option<&PyObjectRef>,
    ) -> Result<PyObjectRef, PyError> {
        unsafe {
            let kwargs_ptr = kwargs.map_or(ptr::null_mut(), |k| k.ptr);
            let result = ffi::PyObject_Call(self.ptr, args.ptr, kwargs_ptr);
            if result.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef { ptr: result })
            }
        }
    }

    /// Call this object with no arguments.
    pub fn call_no_args(&self) -> Result<PyObjectRef, PyError> {
        unsafe {
            let empty_tuple = ffi::PyTuple_New(0);
            let result = ffi::PyObject_CallObject(self.ptr, empty_tuple);
            ffi::Py_DecRef(empty_tuple);
            if result.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef { ptr: result })
            }
        }
    }

    // === Item access (for dicts, sequences) ===

    /// Get an item by key. Equivalent to `obj[key]`.
    pub fn get_item(&self, key: &PyObjectRef) -> Result<PyObjectRef, PyError> {
        unsafe {
            let result = ffi::PyObject_GetItem(self.ptr, key.ptr);
            if result.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef { ptr: result })
            }
        }
    }

    /// Get an item by string key. Convenience for dict access.
    pub fn get_item_str(&self, key: &str) -> Result<PyObjectRef, PyError> {
        let py_key = PyObjectRef::from_str(key)?;
        self.get_item(&py_key)
    }

    /// Set an item by key. Equivalent to `obj[key] = value`.
    pub fn set_item(&self, key: &PyObjectRef, value: &PyObjectRef) -> Result<(), PyError> {
        unsafe {
            let result = ffi::PyObject_SetItem(self.ptr, key.ptr, value.ptr);
            if result < 0 {
                Err(PyError::fetch())
            } else {
                Ok(())
            }
        }
    }

    // === String conversion ===

    /// Convert to Python string representation. Equivalent to `str(obj)`.
    pub fn str_repr(&self) -> Result<String, PyError> {
        unsafe {
            let py_str = ffi::PyObject_Str(self.ptr);
            if py_str.is_null() {
                return Err(PyError::fetch());
            }
            let c_str = ffi::PyUnicode_AsUTF8(py_str);
            let result = if c_str.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(cstr_to_string(c_str))
            };
            ffi::Py_DecRef(py_str);
            result
        }
    }

    // === Type checking ===

    /// Get the type name of this object.
    pub fn type_name(&self) -> String {
        unsafe {
            let type_obj = ffi::PyObject_Type(self.ptr);
            if type_obj.is_null() {
                return "unknown".to_string();
            }
            let name_attr = ffi::PyObject_GetAttrString(type_obj, b"__name__\0".as_ptr() as *const c_char);
            let result = if name_attr.is_null() {
                ffi::PyErr_Clear();
                "unknown".to_string()
            } else {
                let c_str = ffi::PyUnicode_AsUTF8(name_attr);
                let s = if c_str.is_null() {
                    ffi::PyErr_Clear();
                    "unknown".to_string()
                } else {
                    cstr_to_string(c_str)
                };
                ffi::Py_DecRef(name_attr);
                s
            };
            ffi::Py_DecRef(type_obj);
            result
        }
    }

    /// Check if the object is Python None.
    pub fn is_none(&self) -> bool {
        unsafe { self.ptr == &mut ffi::_Py_NoneStruct as *mut ffi::PyObject }
    }

    /// Check truthiness. Equivalent to `bool(obj)`.
    pub fn is_true(&self) -> bool {
        unsafe { ffi::PyObject_IsTrue(self.ptr) == 1 }
    }

    // === Factory methods ===

    /// Create Python None.
    pub fn none() -> PyObjectRef {
        unsafe {
            let ptr = &mut ffi::_Py_NoneStruct as *mut ffi::PyObject;
            ffi::Py_IncRef(ptr);
            PyObjectRef { ptr }
        }
    }

    /// Create a Python string from a Rust &str.
    pub fn from_str(s: &str) -> Result<PyObjectRef, PyError> {
        let c_str = CString::new(s);
        unsafe {
            let ptr = ffi::PyUnicode_FromStringAndSize(
                c_str.as_ptr(),
                s.len() as ffi::Py_ssize_t,
            );
            if ptr.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef { ptr })
            }
        }
    }

    /// Create a Python int from i64.
    pub fn from_i64(v: i64) -> Result<PyObjectRef, PyError> {
        unsafe {
            let ptr = ffi::PyLong_FromLongLong(v as core::ffi::c_longlong);
            if ptr.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef { ptr })
            }
        }
    }

    /// Create a Python int from u64.
    pub fn from_u64(v: u64) -> Result<PyObjectRef, PyError> {
        unsafe {
            let ptr = ffi::PyLong_FromUnsignedLongLong(v as core::ffi::c_ulonglong);
            if ptr.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef { ptr })
            }
        }
    }

    /// Create a Python float from f64.
    pub fn from_f64(v: f64) -> Result<PyObjectRef, PyError> {
        unsafe {
            let ptr = ffi::PyFloat_FromDouble(v);
            if ptr.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef { ptr })
            }
        }
    }

    /// Create a Python bool.
    pub fn from_bool(v: bool) -> PyObjectRef {
        unsafe {
            let ptr = ffi::PyBool_FromLong(if v { 1 } else { 0 });
            // PyBool_FromLong never fails
            PyObjectRef { ptr }
        }
    }

    /// Create Python bytes from a byte slice.
    pub fn from_bytes(data: &[u8]) -> Result<PyObjectRef, PyError> {
        unsafe {
            let ptr = ffi::PyBytes_FromStringAndSize(
                data.as_ptr() as *const c_char,
                data.len() as ffi::Py_ssize_t,
            );
            if ptr.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef { ptr })
            }
        }
    }

    // === Extraction methods ===

    /// Extract as Rust String (from Python str).
    pub fn extract_str(&self) -> Result<String, PyError> {
        unsafe {
            let c_str = ffi::PyUnicode_AsUTF8(self.ptr);
            if c_str.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(cstr_to_string(c_str))
            }
        }
    }

    /// Extract as i64 (from Python int).
    pub fn extract_i64(&self) -> Result<i64, PyError> {
        unsafe {
            let v = ffi::PyLong_AsLongLong(self.ptr);
            if v == -1 && !ffi::PyErr_Occurred().is_null() {
                Err(PyError::fetch())
            } else {
                Ok(v as i64)
            }
        }
    }

    /// Extract as u64 (from Python int).
    pub fn extract_u64(&self) -> Result<u64, PyError> {
        unsafe {
            let v = ffi::PyLong_AsUnsignedLongLong(self.ptr);
            if !ffi::PyErr_Occurred().is_null() {
                Err(PyError::fetch())
            } else {
                Ok(v as u64)
            }
        }
    }

    /// Extract as f64 (from Python float).
    pub fn extract_f64(&self) -> Result<f64, PyError> {
        unsafe {
            let v = ffi::PyFloat_AsDouble(self.ptr);
            if v == -1.0 && !ffi::PyErr_Occurred().is_null() {
                Err(PyError::fetch())
            } else {
                Ok(v)
            }
        }
    }

    /// Extract as bool (from Python bool).
    pub fn extract_bool(&self) -> bool {
        unsafe { ffi::PyObject_IsTrue(self.ptr) == 1 }
    }

    /// Extract as byte vector (from Python bytes).
    pub fn extract_bytes(&self) -> Result<Vec<u8>, PyError> {
        unsafe {
            let mut buffer: *const c_char = ptr::null();
            let mut length: ffi::Py_ssize_t = 0;
            let result = ffi::PyBytes_AsStringAndSize(self.ptr, &mut buffer, &mut length);
            if result < 0 {
                Err(PyError::fetch())
            } else {
                let slice = core::slice::from_raw_parts(buffer as *const u8, length as usize);
                Ok(slice.to_vec())
            }
        }
    }
}

impl Clone for PyObjectRef {
    fn clone(&self) -> Self {
        unsafe {
            ffi::Py_IncRef(self.ptr);
        }
        PyObjectRef { ptr: self.ptr }
    }
}

impl Drop for PyObjectRef {
    fn drop(&mut self) {
        if !self.ptr.is_null() {
            unsafe {
                ffi::Py_DecRef(self.ptr);
            }
        }
    }
}

impl fmt::Debug for PyObjectRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self.str_repr() {
            Ok(s) => write!(f, "PyObject({})", s),
            Err(_) => write!(f, "PyObject(<repr failed>)"),
        }
    }
}

// === Error type ===

/// Python exception captured from CPython.
/// Equivalent to RustPython's `PyBaseExceptionRef`.
#[derive(Debug)]
pub struct PyError {
    pub type_name: String,
    pub message: String,
    /// For StopIteration exceptions, this holds the `.value` attribute
    /// which carries the generator's return value.
    pub value: Option<PyObjectRef>,
}

impl PyError {
    /// Fetch and clear the current Python exception.
    pub fn fetch() -> Self {
        unsafe {
            let mut ptype: *mut ffi::PyObject = ptr::null_mut();
            let mut pvalue: *mut ffi::PyObject = ptr::null_mut();
            let mut ptraceback: *mut ffi::PyObject = ptr::null_mut();

            ffi::PyErr_Fetch(&mut ptype, &mut pvalue, &mut ptraceback);
            ffi::PyErr_NormalizeException(&mut ptype, &mut pvalue, &mut ptraceback);

            let type_name = if !ptype.is_null() {
                let name_attr = ffi::PyObject_GetAttrString(
                    ptype,
                    b"__name__\0".as_ptr() as *const c_char,
                );
                let name = if !name_attr.is_null() {
                    let c_str = ffi::PyUnicode_AsUTF8(name_attr);
                    let s = if !c_str.is_null() {
                        cstr_to_string(c_str)
                    } else {
                        ffi::PyErr_Clear();
                        "UnknownError".to_string()
                    };
                    ffi::Py_DecRef(name_attr);
                    s
                } else {
                    ffi::PyErr_Clear();
                    "UnknownError".to_string()
                };
                ffi::Py_DecRef(ptype);
                name
            } else {
                "UnknownError".to_string()
            };

            let (message, value) = if !pvalue.is_null() {
                // For StopIteration, extract .value (the generator return value)
                let stop_iter_value = if type_name == "StopIteration" {
                    let val_attr = ffi::PyObject_GetAttrString(
                        pvalue,
                        b"value\0".as_ptr() as *const c_char,
                    );
                    if !val_attr.is_null() {
                        // val_attr is an owned ref from GetAttrString
                        Some(PyObjectRef { ptr: val_attr })
                    } else {
                        ffi::PyErr_Clear();
                        None
                    }
                } else {
                    None
                };

                let str_obj = ffi::PyObject_Str(pvalue);
                let msg = if !str_obj.is_null() {
                    let c_str = ffi::PyUnicode_AsUTF8(str_obj);
                    let s = if !c_str.is_null() {
                        cstr_to_string(c_str)
                    } else {
                        ffi::PyErr_Clear();
                        String::new()
                    };
                    ffi::Py_DecRef(str_obj);
                    s
                } else {
                    ffi::PyErr_Clear();
                    String::new()
                };
                ffi::Py_DecRef(pvalue);
                (msg, stop_iter_value)
            } else {
                (String::new(), None)
            };

            if !ptraceback.is_null() {
                ffi::Py_DecRef(ptraceback);
            }

            PyError { type_name, message, value }
        }
    }

    /// Create an error without fetching from Python.
    pub fn new(type_name: &str, message: &str) -> Self {
        PyError {
            type_name: type_name.to_string(),
            message: message.to_string(),
            value: None,
        }
    }

    /// Format as "TypeName: message" (matching RustPython's error string format).
    pub fn to_rust_err_string(&self) -> String {
        if self.message.is_empty() {
            self.type_name.clone()
        } else {
            format!("{}: {}", self.type_name, self.message)
        }
    }
}

impl fmt::Display for PyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.to_rust_err_string())
    }
}

// === Helper: simple C string without std ===

/// A minimal owned C string (null-terminated).
pub(crate) struct CString {
    data: Vec<u8>,
}

impl CString {
    pub(crate) fn new(s: &str) -> Self {
        let mut data = Vec::with_capacity(s.len() + 1);
        data.extend_from_slice(s.as_bytes());
        data.push(0);
        CString { data }
    }

    pub(crate) fn as_ptr(&self) -> *const c_char {
        self.data.as_ptr() as *const c_char
    }
}

/// Create a CString from a &str (convenience for other modules).
pub(crate) fn make_cstring(s: &str) -> CString {
    CString::new(s)
}

/// Convert a C string pointer to a Rust String.
pub(crate) unsafe fn cstr_to_string(ptr: *const c_char) -> String {
    let mut len = 0;
    while *ptr.add(len) != 0 {
        len += 1;
    }
    let slice = core::slice::from_raw_parts(ptr as *const u8, len);
    String::from_utf8_lossy(slice).into_owned()
}
