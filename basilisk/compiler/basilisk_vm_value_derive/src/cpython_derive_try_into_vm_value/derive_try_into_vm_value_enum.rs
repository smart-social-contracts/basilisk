use cdk_framework::traits::ToIdent;
use proc_macro2::Ident;
use proc_macro2::TokenStream;
use quote::quote;
use syn::{DataEnum, Field, Fields};

pub fn cpython_derive_try_into_vm_value_enum(enum_name: &Ident, data_enum: &DataEnum) -> TokenStream {
    let variant_branches = derive_variant_branches(&enum_name, &data_enum);

    quote! {
        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for #enum_name {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                match self {
                    #(#variant_branches),*
                }
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for Vec<#enum_name> {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                try_into_vm_value_generic_array(self, ())
            }
        }
    }
}

fn derive_variant_branches(enum_name: &Ident, data_enum: &DataEnum) -> Vec<TokenStream> {
    data_enum
        .variants
        .iter()
        .map(|variant| {
            let variant_name = &variant.ident;

            match &variant.fields {
                Fields::Named(_) => panic!("Named fields not currently supported"),
                Fields::Unnamed(fields_unnamed) => derive_variant_branches_unnamed_fields(
                    enum_name,
                    variant_name,
                    fields_unnamed.unnamed.iter().collect(),
                ),
                Fields::Unit => {
                    derive_variant_branches_unnamed_fields(enum_name, variant_name, vec![])
                }
            }
        })
        .collect()
}

fn derive_variant_branches_unnamed_fields(
    enum_name: &Ident,
    variant_name: &Ident,
    unnamed_fields: Vec<&Field>,
) -> TokenStream {
    let restored_variant_name = cdk_framework::keyword::restore_for_vm(
        &variant_name.to_string(),
        &crate::get_python_keywords(),
    )
    .to_ident();
    if unnamed_fields.len() == 0 {
        quote! {
            #enum_name::#variant_name => {
                let dict = basilisk_cpython::PyDict::new()
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;

                dict.set_item_str(
                    stringify!(#restored_variant_name),
                    &basilisk_cpython::PyObjectRef::none(),
                ).map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;

                Ok(dict.into_object())
            }
        }
    } else {
        quote! {
            #enum_name::#variant_name(value) => {
                let dict = basilisk_cpython::PyDict::new()
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;

                let py_value = value.try_into_vm_value(())?;
                dict.set_item_str(
                    stringify!(#restored_variant_name),
                    &py_value,
                ).map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;

                Ok(dict.into_object())
            }
        }
    }
}
