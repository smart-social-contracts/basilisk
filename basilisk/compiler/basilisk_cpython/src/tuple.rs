//! Python tuple operations.
//!
//! Provides a `PyTuple` type that wraps CPython's tuple C API.
//! Mirrors the role of `vm.ctx.new_tuple(vec![...])` in the current RustPython-based code.

use crate::ffi;
use crate::object::{PyError, PyObjectRef};

/// A Python tuple wrapper.
///
/// In the current RustPython code, tuples are used for:
/// - Unnamed struct fields: `vm.ctx.new_tuple(vec![field_0, field_1, ...])`
/// - Function call arguments: args are packed into tuples
pub struct PyTuple {
    inner: PyObjectRef,
}

impl PyTuple {
    /// Create a new tuple from a vector of PyObjectRef.
    ///
    /// Equivalent to `vm.ctx.new_tuple(vec![...])` in RustPython.
    pub fn new(items: Vec<PyObjectRef>) -> Result<Self, PyError> {
        unsafe {
            let len = items.len() as ffi::Py_ssize_t;
            let tuple = ffi::PyTuple_New(len);
            if tuple.is_null() {
                return Err(PyError::fetch());
            }

            for (i, item) in items.into_iter().enumerate() {
                // PyTuple_SetItem steals a reference, so we use into_ptr()
                let result = ffi::PyTuple_SetItem(tuple, i as ffi::Py_ssize_t, item.into_ptr());
                if result < 0 {
                    ffi::Py_DecRef(tuple);
                    return Err(PyError::fetch());
                }
            }

            Ok(PyTuple {
                inner: PyObjectRef::from_owned(tuple).unwrap(),
            })
        }
    }

    /// Create an empty tuple.
    pub fn empty() -> Result<Self, PyError> {
        Self::new(vec![])
    }

    /// Get the length of the tuple.
    pub fn len(&self) -> usize {
        unsafe { ffi::PyTuple_Size(self.inner.as_ptr()) as usize }
    }

    /// Check if empty.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Get an item by index (returns a borrowed reference).
    ///
    /// Equivalent to `tuple_ref.get(index)` in RustPython.
    pub fn get(&self, index: usize) -> Option<PyObjectRef> {
        if index >= self.len() {
            return None;
        }
        unsafe {
            let item = ffi::PyTuple_GetItem(self.inner.as_ptr(), index as ffi::Py_ssize_t);
            if item.is_null() {
                ffi::PyErr_Clear();
                None
            } else {
                // PyTuple_GetItem returns a borrowed ref, so we incref
                PyObjectRef::from_borrowed(item)
            }
        }
    }

    /// Convert to a PyObjectRef (for passing to Python functions as args).
    pub fn into_object(self) -> PyObjectRef {
        self.inner
    }

    /// Get a reference to the inner PyObjectRef.
    pub fn as_object(&self) -> &PyObjectRef {
        &self.inner
    }
}

impl From<PyTuple> for PyObjectRef {
    fn from(tuple: PyTuple) -> PyObjectRef {
        tuple.inner
    }
}
