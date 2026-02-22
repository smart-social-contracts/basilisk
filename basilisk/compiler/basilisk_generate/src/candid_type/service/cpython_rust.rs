use proc_macro2::TokenStream;
use quote::{quote, ToTokens};

use cdk_framework::traits::ToIdent;

pub fn to_vm_value(name: String) -> TokenStream {
    let service_name = name.to_ident().to_token_stream();
    quote! {
        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>
            for #service_name
        {
            fn try_into_vm_value(
                self,
                _: (),
            ) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                unsafe {
                    let interpreter = match INTERPRETER_OPTION.as_mut() {
                        Some(i) => i,
                        None => {
                            return Err(CdkActTryIntoVmValueError(
                                "SystemError: missing python interpreter".to_string(),
                            ))
                        }
                    };
                    let code = format!(
                        "from basilisk import Principal; {}(Principal.from_str('{}'))",
                        stringify!(#service_name),
                        self.0.principal.to_string()
                    );
                    interpreter.run_code_string(&code)
                        .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
                }
            }
        }
    }
}

pub fn list_to_vm_value(name: String) -> TokenStream {
    let service_name = name.to_ident().to_token_stream();
    quote! {
        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>
            for Vec<#service_name>
        {
            fn try_into_vm_value(
                self,
                _: (),
            ) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                try_into_vm_value_generic_array(self, ())
            }
        }
    }
}

pub fn from_vm_value(name: String) -> TokenStream {
    let service_name = name.to_ident().to_token_stream();
    quote! {
        impl CdkActTryFromVmValue<#service_name, basilisk_cpython::PyError, ()>
            for basilisk_cpython::PyObjectRef
        {
            fn try_from_vm_value(
                self,
                _: (),
            ) -> Result<#service_name, basilisk_cpython::PyError> {
                let canister_id = self.get_item_str("canister_id")?;
                let to_str_fn = canister_id.get_attr("to_str")?;
                let empty_args = basilisk_cpython::PyTuple::empty()
                    .map_err(|e| basilisk_cpython::PyError::new("TypeError", &e.to_rust_err_string()))?;
                let result = to_str_fn.call(&empty_args.into_object(), None)?;
                let result_string: String = result.extract_str()?;
                match candid::Principal::from_text(result_string) {
                    Ok(principal) => Ok(#service_name::new(principal)),
                    Err(err) => Err(basilisk_cpython::PyError::new(
                        "TypeError",
                        &format!("Could not convert value to Principal: {}", err),
                    )),
                }
            }
        }
    }
}

pub fn list_from_vm_value(name: String) -> TokenStream {
    let service_name = name.to_ident().to_token_stream();
    quote! {
        impl CdkActTryFromVmValue<Vec<#service_name>, basilisk_cpython::PyError, ()>
            for basilisk_cpython::PyObjectRef
        {
            fn try_from_vm_value(
                self,
                _: (),
            ) -> Result<Vec<#service_name>, basilisk_cpython::PyError>
            {
                try_from_vm_value_generic_array(self, ())
            }
        }
    }
}
