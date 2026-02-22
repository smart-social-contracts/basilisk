use cdk_framework::traits::ToIdent;
use proc_macro2::Ident;
use proc_macro2::TokenStream;
use quote::{format_ident, quote};
use syn::{DataStruct, Fields, Index};

pub fn cpython_derive_try_from_vm_value_struct(
    struct_name: &Ident,
    data_struct: &DataStruct,
) -> TokenStream {
    let field_variable_definitions = generate_field_variable_definitions(data_struct);
    let field_variable_names = generate_field_initializers(data_struct);

    quote! {
        impl CdkActTryFromVmValue<#struct_name, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<#struct_name, basilisk_cpython::PyError> {
                #(#field_variable_definitions)*

                Ok(#struct_name {
                    #(#field_variable_names),*
                })
            }
        }

        impl CdkActTryFromVmValue<Vec<#struct_name>, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<Vec<#struct_name>, basilisk_cpython::PyError> {
                try_from_vm_value_generic_array(self, ())
            }
        }
    }
}

fn generate_field_variable_definitions(data_struct: &DataStruct) -> Vec<TokenStream> {
    match &data_struct.fields {
        Fields::Named(fields_named) => fields_named
            .named
            .iter()
            .map(|field| {
                let field_name = &field.ident;
                let variable_name = format_ident!(
                    "user_defined_{}",
                    field.ident.as_ref().expect("Named field must have a name")
                );
                let restored_field_name = match field_name {
                    Some(field_name) => Some(
                        cdk_framework::keyword::restore_for_vm(
                            &field_name.to_string(),
                            &crate::get_python_keywords(),
                        )
                        .to_ident(),
                    ),
                    None => field_name.clone(),
                };

                quote! {
                    let key = basilisk_cpython::PyObjectRef::from_str(stringify!(#restored_field_name))
                        .map_err(|e| basilisk_cpython::PyError::new("TypeError", &e.to_rust_err_string()))?;
                    let #variable_name = self.get_item(&key)?;
                }
            })
            .collect(),
        Fields::Unnamed(fields_unnamed) => fields_unnamed
            .unnamed
            .iter()
            .enumerate()
            .map(|(index, _)| {
                let variable_name = format_ident!("field_{}", index);
                let idx = index as isize;

                quote! {
                    let #variable_name = {
                        let raw_item = unsafe {
                            basilisk_cpython::ffi::PyTuple_GetItem(self.as_ptr(), #idx)
                        };
                        if raw_item.is_null() {
                            return Err(basilisk_cpython::PyError::new(
                                "IndexError",
                                &format!("tuple index {} out of range", #idx),
                            ));
                        }
                        unsafe {
                            basilisk_cpython::PyObjectRef::from_borrowed(raw_item)
                                .ok_or_else(|| basilisk_cpython::PyError::new("TypeError", "null tuple element"))?
                        }
                    };
                }
            })
            .collect(),
        _ => panic!("Only named and unnamed fields supported for Structs"),
    }
}

fn generate_field_initializers(data_struct: &DataStruct) -> Vec<TokenStream> {
    match &data_struct.fields {
        Fields::Named(fields_named) => fields_named
            .named
            .iter()
            .map(|field| {
                let field_name = &field.ident;
                let variable_name = format_ident!(
                    "user_defined_{}",
                    field.ident.as_ref().expect("Named field must have a name")
                );

                quote! {
                    #field_name: #variable_name.try_from_vm_value(())?
                }
            })
            .collect(),
        Fields::Unnamed(fields_unnamed) => fields_unnamed
            .unnamed
            .iter()
            .enumerate()
            .map(|(index, _)| {
                let variable_name = format_ident!("field_{}", index);
                let syn_index = Index::from(index);

                quote! {
                    #syn_index: #variable_name.try_from_vm_value(())?
                }
            })
            .collect(),
        _ => panic!("Only named and unnamed fields supported for Structs"),
    }
}
