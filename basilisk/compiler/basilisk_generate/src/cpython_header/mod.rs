//! CPython-specific header generation.
//!
//! This module generates the header code for canisters using CPython instead of RustPython.
//! It replaces `header/mod.rs` when the CPython backend is selected.

mod traits;
mod use_statements;

use proc_macro2::TokenStream;

pub fn generate() -> TokenStream {
    let use_statements = use_statements::generate();
    let traits = traits::generate();

    quote::quote! {
        #![allow(warnings, unused)]

        #use_statements
        #traits

        static mut INTERPRETER_OPTION: Option<basilisk_cpython::Interpreter> = None;
        static mut SCOPE_OPTION: Option<basilisk_cpython::Scope> = None;
    }
}
