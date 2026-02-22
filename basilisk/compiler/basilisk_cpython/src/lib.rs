//! # basilisk_cpython
//!
//! CPython FFI bridge for Basilisk IC canisters.
//!
//! This crate provides a safe Rust API over CPython's C API, specifically designed
//! for use inside IC canisters compiled to `wasm32-wasip1`. It replaces the
//! RustPython interpreter (`rustpython`, `rustpython-vm`, etc.) with CPython 3.13,
//! providing a **7-20x performance improvement** for Python execution on the IC.
//!
//! ## Architecture
//!
//! The crate mirrors the RustPython API surface used by Basilisk's generated canister code:
//!
//! | RustPython type | basilisk_cpython equivalent |
//! |---|---|
//! | `rustpython_vm::Interpreter` | [`Interpreter`] |
//! | `rustpython_vm::scope::Scope` | [`Scope`] |
//! | `rustpython::vm::PyObjectRef` | [`PyObjectRef`] |
//! | `rustpython_vm::builtins::PyBaseExceptionRef` | [`PyError`] |
//! | `vm.ctx.new_dict()` | [`PyDict::new()`] |
//! | `vm.ctx.new_tuple(vec![...])` | [`PyTuple::new(vec![...])`] |
//! | `CdkActTryIntoVmValue` | [`TryIntoPyObject`] |
//! | `CdkActTryFromVmValue` | [`TryFromPyObject`] |
//!
//! ## Usage in generated code
//!
//! The code generator (`basilisk_generate`) will emit Rust code that uses this crate
//! instead of RustPython. For example, the current generated init code:
//!
//! ```ignore
//! // Current (RustPython):
//! let interpreter = rustpython_vm::Interpreter::with_init(Default::default(), |vm| { ... });
//! let scope = interpreter.enter(|vm| vm.new_scope_with_builtins());
//! let vm = &interpreter.vm;
//!
//! // New (CPython):
//! let interpreter = basilisk_cpython::Interpreter::initialize()?;
//! let scope = interpreter.new_scope();
//! ```

pub mod ffi;
pub mod object;
pub mod interpreter;
pub mod dict;
pub mod tuple;
pub mod convert;

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

/// Trait for panicking on error (mirrors `unwrap_or_trap` in RustPython code).
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
