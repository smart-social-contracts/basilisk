//! Type conversion traits between Rust/Candid types and CPython PyObject.
//!
//! These traits mirror the RustPython-based `CdkActTryIntoVmValue` and
//! `CdkActTryFromVmValue` traits from `basilisk_vm_value_derive`.
//!
//! In the RustPython codebase:
//! - `CdkActTryIntoVmValue<&VirtualMachine, PyObjectRef>` converts Rust → Python
//! - `CdkActTryFromVmValue<T, PyBaseExceptionRef, &VirtualMachine>` converts Python → Rust
//!
//! Here we provide equivalent traits that work with CPython's C API through
//! our `PyObjectRef` wrapper.

use crate::dict::PyDict;
use crate::object::{PyError, PyObjectRef};
use crate::tuple::PyTuple;

/// Error type for conversions into Python values.
#[derive(Debug)]
pub struct TryIntoVmValueError(pub String);

impl core::fmt::Display for TryIntoVmValueError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// Convert a Rust value into a CPython PyObject.
///
/// Equivalent to `CdkActTryIntoVmValue<&VirtualMachine, PyObjectRef>`.
pub trait TryIntoPyObject {
    fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError>;
}

/// Convert a CPython PyObject into a Rust value.
///
/// Equivalent to `CdkActTryFromVmValue<T, PyBaseExceptionRef, &VirtualMachine>`.
pub trait TryFromPyObject: Sized {
    fn try_from_py_object(obj: PyObjectRef) -> Result<Self, PyError>;
}

// === Primitive type implementations ===

impl TryIntoPyObject for () {
    fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError> {
        Ok(PyObjectRef::none())
    }
}

impl TryFromPyObject for () {
    fn try_from_py_object(_obj: PyObjectRef) -> Result<Self, PyError> {
        Ok(())
    }
}

impl TryIntoPyObject for bool {
    fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError> {
        Ok(PyObjectRef::from_bool(self))
    }
}

impl TryFromPyObject for bool {
    fn try_from_py_object(obj: PyObjectRef) -> Result<Self, PyError> {
        Ok(obj.extract_bool())
    }
}

impl TryIntoPyObject for String {
    fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError> {
        PyObjectRef::from_str(&self).map_err(|e| TryIntoVmValueError(e.to_rust_err_string()))
    }
}

impl TryFromPyObject for String {
    fn try_from_py_object(obj: PyObjectRef) -> Result<Self, PyError> {
        obj.extract_str()
    }
}

impl TryIntoPyObject for &str {
    fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError> {
        PyObjectRef::from_str(self).map_err(|e| TryIntoVmValueError(e.to_rust_err_string()))
    }
}

// Signed integers
macro_rules! impl_signed_int {
    ($($ty:ty),*) => {
        $(
            impl TryIntoPyObject for $ty {
                fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError> {
                    PyObjectRef::from_i64(self as i64)
                        .map_err(|e| TryIntoVmValueError(e.to_rust_err_string()))
                }
            }

            impl TryFromPyObject for $ty {
                fn try_from_py_object(obj: PyObjectRef) -> Result<Self, PyError> {
                    let v = obj.extract_i64()?;
                    Ok(v as $ty)
                }
            }
        )*
    };
}

impl_signed_int!(i8, i16, i32, i64, i128);

// Unsigned integers
macro_rules! impl_unsigned_int {
    ($($ty:ty),*) => {
        $(
            impl TryIntoPyObject for $ty {
                fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError> {
                    PyObjectRef::from_u64(self as u64)
                        .map_err(|e| TryIntoVmValueError(e.to_rust_err_string()))
                }
            }

            impl TryFromPyObject for $ty {
                fn try_from_py_object(obj: PyObjectRef) -> Result<Self, PyError> {
                    let v = obj.extract_u64()?;
                    Ok(v as $ty)
                }
            }
        )*
    };
}

impl_unsigned_int!(u8, u16, u32, u64, u128);

// Floats
impl TryIntoPyObject for f32 {
    fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError> {
        PyObjectRef::from_f64(self as f64)
            .map_err(|e| TryIntoVmValueError(e.to_rust_err_string()))
    }
}

impl TryFromPyObject for f32 {
    fn try_from_py_object(obj: PyObjectRef) -> Result<Self, PyError> {
        Ok(obj.extract_f64()? as f32)
    }
}

impl TryIntoPyObject for f64 {
    fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError> {
        PyObjectRef::from_f64(self).map_err(|e| TryIntoVmValueError(e.to_rust_err_string()))
    }
}

impl TryFromPyObject for f64 {
    fn try_from_py_object(obj: PyObjectRef) -> Result<Self, PyError> {
        obj.extract_f64()
    }
}

// Vec<u8> (bytes/blob)
impl TryIntoPyObject for Vec<u8> {
    fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError> {
        PyObjectRef::from_bytes(&self).map_err(|e| TryIntoVmValueError(e.to_rust_err_string()))
    }
}

impl TryFromPyObject for Vec<u8> {
    fn try_from_py_object(obj: PyObjectRef) -> Result<Self, PyError> {
        obj.extract_bytes()
    }
}

// Option<T> maps to Python None | T
impl<T: TryIntoPyObject> TryIntoPyObject for Option<T> {
    fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError> {
        match self {
            Some(v) => v.try_into_py_object(),
            None => Ok(PyObjectRef::none()),
        }
    }
}

impl<T: TryFromPyObject> TryFromPyObject for Option<T> {
    fn try_from_py_object(obj: PyObjectRef) -> Result<Self, PyError> {
        if obj.is_none() {
            Ok(None)
        } else {
            Ok(Some(T::try_from_py_object(obj)?))
        }
    }
}

// Vec<T> maps to Python list
impl<T: TryIntoPyObject> TryIntoPyObject for Vec<T> {
    fn try_into_py_object(self) -> Result<PyObjectRef, TryIntoVmValueError> {
        let py_items: Vec<PyObjectRef> = self
            .into_iter()
            .map(|item| item.try_into_py_object())
            .collect::<Result<Vec<_>, _>>()?;

        // Create a Python list
        unsafe {
            let list = crate::ffi::PyList_New(py_items.len() as crate::ffi::Py_ssize_t);
            if list.is_null() {
                return Err(TryIntoVmValueError("Failed to create Python list".to_string()));
            }
            for (i, item) in py_items.into_iter().enumerate() {
                // PyList_SetItem steals a reference
                crate::ffi::PyList_SetItem(list, i as crate::ffi::Py_ssize_t, item.into_ptr());
            }
            Ok(PyObjectRef::from_owned(list).unwrap())
        }
    }
}

impl<T: TryFromPyObject> TryFromPyObject for Vec<T> {
    fn try_from_py_object(obj: PyObjectRef) -> Result<Self, PyError> {
        unsafe {
            let len = crate::ffi::PySequence_Length(obj.as_ptr());
            if len < 0 {
                return Err(PyError::fetch());
            }
            let mut result = Vec::with_capacity(len as usize);
            for i in 0..len {
                let item = crate::ffi::PySequence_GetItem(obj.as_ptr(), i);
                if item.is_null() {
                    return Err(PyError::fetch());
                }
                let py_obj = PyObjectRef::from_owned(item).unwrap();
                result.push(T::try_from_py_object(py_obj)?);
            }
            Ok(result)
        }
    }
}

// === Helpers for generated code ===

/// Convert a Rust value to a PyObjectRef using the trait.
/// This is the function generated code will call.
pub fn try_into_vm_value<T: TryIntoPyObject>(value: T) -> Result<PyObjectRef, TryIntoVmValueError> {
    value.try_into_py_object()
}

/// Convert a PyObjectRef to a Rust value using the trait.
/// This is the function generated code will call.
pub fn try_from_vm_value<T: TryFromPyObject>(obj: PyObjectRef) -> Result<T, PyError> {
    T::try_from_py_object(obj)
}

/// Generic array conversion helper (mirrors `try_into_vm_value_generic_array` in RustPython code).
pub fn try_into_vm_value_generic_array<T: TryIntoPyObject>(
    items: Vec<T>,
) -> Result<PyObjectRef, TryIntoVmValueError> {
    items.try_into_py_object()
}

/// Generic array extraction helper (mirrors `try_from_vm_value_generic_array` in RustPython code).
pub fn try_from_vm_value_generic_array<T: TryFromPyObject>(
    obj: PyObjectRef,
) -> Result<Vec<T>, PyError> {
    Vec::<T>::try_from_py_object(obj)
}
