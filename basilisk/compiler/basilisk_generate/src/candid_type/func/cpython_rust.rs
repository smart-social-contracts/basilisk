use proc_macro2::TokenStream;
use quote::{quote, ToTokens};

use cdk_framework::traits::ToIdent;

pub fn generate_func_to_vm_value(name: &String) -> TokenStream {
    let type_alias_name = name.to_ident().to_token_stream();
    quote! {
        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for #type_alias_name {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                self.0.try_into_vm_value(())
            }
        }
    }
}

pub fn generate_func_list_to_vm_value(name: &String) -> TokenStream {
    let type_alias_name = name.to_ident().to_token_stream();
    quote! {
        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for Vec<#type_alias_name> {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                try_into_vm_value_generic_array(self, ())
            }
        }
    }
}

pub fn generate_func_from_vm_value(name: &String) -> TokenStream {
    let type_alias_name = name.to_ident().to_token_stream();
    quote! {
        impl CdkActTryFromVmValue<#type_alias_name, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<#type_alias_name, basilisk_cpython::PyError> {
                let candid_func: candid::Func = self.try_from_vm_value(())?;
                Ok(#type_alias_name::new(candid_func.principal, candid_func.method))
            }
        }
    }
}

pub fn generate_func_list_from_vm_value(name: &String) -> TokenStream {
    let type_alias_name = name.to_ident().to_token_stream();
    quote! {
        impl CdkActTryFromVmValue<Vec<#type_alias_name>, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<Vec<#type_alias_name>, basilisk_cpython::PyError> {
                try_from_vm_value_generic_array(self, ())
            }
        }
    }
}
