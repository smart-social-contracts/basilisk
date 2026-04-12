//! # basilisk_cpython
//!
//! CPython FFI bridge for Basilisk IC canisters.
//!
//! This crate provides a safe Rust API over CPython's C API, specifically designed
//! for use inside IC canisters compiled to `wasm32-wasip1`.
//!
//! ## Architecture
//!
//! | Type | Description |
//! |---|---|
//! | [`Interpreter`] | Manages CPython lifecycle and global namespace |
//! | [`Scope`] | Holds globals/locals dict for executing user Python code |
//! | [`PyObjectRef`] | RAII wrapper around `PyObject*` with automatic ref counting |
//! | [`PyError`] | Captured Python exception |
//! | [`PyDict::new()`] | Python dict wrapper |
//! | [`PyTuple::new(vec![...])`] | Python tuple wrapper |
//! | [`TryIntoPyObject`] | Convert Rust → Python |
//! | [`TryFromPyObject`] | Convert Python → Rust |
//!
//! ## Usage
//!
//! ```ignore
//! let interpreter = basilisk_cpython::Interpreter::initialize()?;
//! let scope = interpreter.new_scope();
//! ```

pub mod ffi;
pub mod object;
pub mod interpreter;
pub mod dict;
pub mod tuple;
pub mod convert;
#[cfg(target_arch = "wasm32")]
pub mod wasm_stubs;

// Re-export main types at crate root
pub use object::{PyObjectRef, PyError};
pub use interpreter::{Interpreter, Scope};
pub use dict::PyDict;
pub use tuple::PyTuple;
pub use convert::{
    TryIntoPyObject, TryFromPyObject, TryIntoVmValueError,
    try_into_vm_value, try_from_vm_value,
    try_into_vm_value_generic_array, try_from_vm_value_generic_array,
};

/// Trait for panicking on error.
///
/// On the IC, panics result in the canister trapping the message.
pub trait UnwrapOrTrap {
    type Output;
    fn unwrap_or_trap(self) -> Self::Output;
    fn unwrap_or_trap_with(self, msg: &str) -> Self::Output;
}

impl<T> UnwrapOrTrap for Result<T, PyError> {
    type Output = T;

    fn unwrap_or_trap(self) -> T {
        match self {
            Ok(v) => v,
            Err(e) => panic!("{}", e.to_rust_err_string()),
        }
    }

    fn unwrap_or_trap_with(self, msg: &str) -> T {
        match self {
            Ok(v) => v,
            Err(e) => panic!("{}: {}", msg, e.to_rust_err_string()),
        }
    }
}

impl<T> UnwrapOrTrap for Result<T, String> {
    type Output = T;

    fn unwrap_or_trap(self) -> T {
        match self {
            Ok(v) => v,
            Err(e) => panic!("{}", e),
        }
    }

    fn unwrap_or_trap_with(self, msg: &str) -> T {
        match self {
            Ok(v) => v,
            Err(e) => panic!("{}: {}", msg, e),
        }
    }
}

impl<T> UnwrapOrTrap for Option<T> {
    type Output = T;

    fn unwrap_or_trap(self) -> T {
        match self {
            Some(v) => v,
            None => panic!("unwrap_or_trap called on None"),
        }
    }

    fn unwrap_or_trap_with(self, msg: &str) -> T {
        match self {
            Some(v) => v,
            None => panic!("{}", msg),
        }
    }
}
