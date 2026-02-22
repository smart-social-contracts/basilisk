//! CPython-specific trait implementations for generated canister code.
//!
//! Replaces `header/traits.rs` when CPython backend is selected.
//! Instead of converting RustPython PyBaseExceptionRef, we use basilisk_cpython::PyError.

pub fn generate() -> proc_macro2::TokenStream {
    quote::quote! {
        trait ToCdkActTryIntoVmValueError {
            fn to_cdk_act_try_into_vm_value_error(self) -> CdkActTryIntoVmValueError;
        }

        impl ToCdkActTryIntoVmValueError for basilisk_cpython::PyError {
            fn to_cdk_act_try_into_vm_value_error(self) -> CdkActTryIntoVmValueError {
                CdkActTryIntoVmValueError(self.to_rust_err_string())
            }
        }

        trait ToRustErrString {
            fn to_rust_err_string(self) -> String;
        }

        impl ToRustErrString for basilisk_cpython::PyError {
            fn to_rust_err_string(self) -> String {
                self.to_rust_err_string()
            }
        }
    }
}
