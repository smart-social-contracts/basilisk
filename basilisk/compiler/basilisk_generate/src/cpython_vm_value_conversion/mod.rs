//! CPython-specific vm_value_conversion implementations.
//!
//! Generates `CdkActTryIntoVmValue` and `CdkActTryFromVmValue` trait impls
//! that use `basilisk_cpython` types instead of RustPython types.
//!
//! The trait signatures remain the same (they're defined in cdk_framework),
//! but the type parameters change:
//! - `&rustpython::vm::VirtualMachine` → no VM parameter (CPython is global)
//! - `rustpython::vm::PyObjectRef` → `basilisk_cpython::PyObjectRef`
//! - `rustpython_vm::builtins::PyBaseExceptionRef` → `basilisk_cpython::PyError`

pub mod try_into_vm_value_impls;
pub mod try_from_vm_value_impls;
