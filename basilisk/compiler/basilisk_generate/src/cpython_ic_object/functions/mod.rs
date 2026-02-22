//! CPython IC object function implementations.
//!
//! Each submodule generates `extern "C" fn` implementations that follow
//! CPython's PyCFunction calling convention.

pub mod notify;
pub mod notify_with_payment128;
pub mod reply;
pub mod simple;
pub mod stable;
pub mod stable_btree;
pub mod timers;
pub mod with_args;
