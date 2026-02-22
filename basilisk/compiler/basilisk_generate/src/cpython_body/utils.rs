//! CPython-specific utility types for generated canister code.
//!
//! Replaces `body/utils.rs` for CPython backend.
//! Provides BasiliskError and CandidError using basilisk_cpython::PyError
//! instead of RustPython's VirtualMachine-based exception creation.

pub fn generate() -> proc_macro2::TokenStream {
    quote::quote! {
        struct BasiliskError {}

        impl BasiliskError {
            fn new(message: String) -> basilisk_cpython::PyError {
                basilisk_cpython::PyError::new("Error", &message)
            }

            fn subtype(subtype: &str, message: String) -> basilisk_cpython::PyError {
                basilisk_cpython::PyError::new(subtype, &message)
            }
        }

        struct CandidError {}

        impl CandidError {
            fn new(message: String) -> basilisk_cpython::PyError {
                BasiliskError::subtype("CandidError", message)
            }
        }
    }
}
