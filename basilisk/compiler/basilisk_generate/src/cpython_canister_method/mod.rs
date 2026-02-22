//! CPython-specific canister method code generation.
//!
//! This module provides alternative code generation for canister init, query, and update
//! methods using basilisk_cpython instead of RustPython.

pub mod init_method;
pub mod query_or_update;
