//! Python dict operations.
//!
//! Provides a `PyDict` type that wraps CPython's dict C API.
//! Mirrors the role of `vm.ctx.new_dict()` and dict operations in the
//! current RustPython-based generated code.

use crate::ffi;
use crate::object::{make_cstring, PyError, PyObjectRef};
use core::ffi::c_char;

/// A Python dict wrapper.
///
/// In the current RustPython code, dicts are used for:
/// - Record types (named structs): `let py_data_structure = vm.ctx.new_dict();`
/// - Variant types (enums): `let dict = vm.ctx.new_dict();`
/// - Scope globals
pub struct PyDict {
    inner: PyObjectRef,
}

impl PyDict {
    /// Create a new empty dict.
    ///
    /// Equivalent to `vm.ctx.new_dict()` in RustPython.
    pub fn new() -> Result<Self, PyError> {
        unsafe {
            let ptr = ffi::PyDict_New();
            if ptr.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyDict {
                    inner: PyObjectRef::from_owned(ptr).unwrap(),
                })
            }
        }
    }

    /// Set an item by string key.
    ///
    /// Equivalent to `dict.set_item(key, value, vm)` in RustPython.
    pub fn set_item_str(&self, key: &str, value: &PyObjectRef) -> Result<(), PyError> {
        let c_key = make_cstring(key);
        unsafe {
            let result = ffi::PyDict_SetItemString(
                self.inner.as_ptr(),
                c_key.as_ptr() as *const c_char,
                value.as_ptr(),
            );
            if result < 0 {
                Err(PyError::fetch())
            } else {
                Ok(())
            }
        }
    }

    /// Set an item by Python object key.
    pub fn set_item(&self, key: &PyObjectRef, value: &PyObjectRef) -> Result<(), PyError> {
        unsafe {
            let result = ffi::PyDict_SetItem(self.inner.as_ptr(), key.as_ptr(), value.as_ptr());
            if result < 0 {
                Err(PyError::fetch())
            } else {
                Ok(())
            }
        }
    }

    /// Get an item by string key. Returns None if not found.
    ///
    /// Equivalent to `dict.get_item(key, vm)` in RustPython.
    pub fn get_item_str(&self, key: &str) -> Option<PyObjectRef> {
        let c_key = make_cstring(key);
        unsafe {
            let item =
                ffi::PyDict_GetItemString(self.inner.as_ptr(), c_key.as_ptr() as *const c_char);
            if item.is_null() {
                ffi::PyErr_Clear(); // Clear any KeyError
                None
            } else {
                PyObjectRef::from_borrowed(item)
            }
        }
    }

    /// Get an item by Python object key. Returns error if not found.
    pub fn get_item(&self, key: &PyObjectRef) -> Result<PyObjectRef, PyError> {
        unsafe {
            let item = ffi::PyDict_GetItem(self.inner.as_ptr(), key.as_ptr());
            if item.is_null() {
                Err(PyError::new("KeyError", "key not found"))
            } else {
                Ok(PyObjectRef::from_borrowed(item).unwrap())
            }
        }
    }

    /// Check if key exists.
    pub fn contains(&self, key: &PyObjectRef) -> bool {
        unsafe { ffi::PyDict_Contains(self.inner.as_ptr(), key.as_ptr()) == 1 }
    }

    /// Get the number of items.
    pub fn len(&self) -> usize {
        unsafe { ffi::PyDict_Size(self.inner.as_ptr()) as usize }
    }

    /// Check if empty.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Convert to a PyObjectRef (for passing to Python functions).
    pub fn into_object(self) -> PyObjectRef {
        self.inner
    }

    /// Get a reference to the inner PyObjectRef.
    pub fn as_object(&self) -> &PyObjectRef {
        &self.inner
    }

    /// Iterate over key-value pairs.
    pub fn iter(&self) -> PyDictIter {
        PyDictIter {
            dict_ptr: self.inner.as_ptr(),
            pos: 0,
        }
    }
}

impl From<PyDict> for PyObjectRef {
    fn from(dict: PyDict) -> PyObjectRef {
        dict.inner
    }
}

/// Iterator over dict items.
pub struct PyDictIter {
    dict_ptr: *mut ffi::PyObject,
    pos: ffi::Py_ssize_t,
}

impl Iterator for PyDictIter {
    type Item = (PyObjectRef, PyObjectRef);

    fn next(&mut self) -> Option<Self::Item> {
        unsafe {
            let mut key: *mut ffi::PyObject = core::ptr::null_mut();
            let mut value: *mut ffi::PyObject = core::ptr::null_mut();

            if ffi::PyDict_Next(self.dict_ptr, &mut self.pos, &mut key, &mut value) != 0 {
                let key_ref = PyObjectRef::from_borrowed(key)?;
                let value_ref = PyObjectRef::from_borrowed(value)?;
                Some((key_ref, value_ref))
            } else {
                None
            }
        }
    }
}
