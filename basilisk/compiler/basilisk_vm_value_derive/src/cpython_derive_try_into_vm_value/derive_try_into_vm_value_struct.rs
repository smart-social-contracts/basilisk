use cdk_framework::traits::ToIdent;
use proc_macro2::{Ident, TokenStream};
use quote::{format_ident, quote};
use syn::{DataStruct, Fields, Index};

pub fn cpython_derive_try_into_vm_value_struct(
    struct_name: &Ident,
    data_struct: &DataStruct,
) -> TokenStream {
    let data_structure_definition = derive_data_structure_definition(data_struct);
    let variable_definitions = derive_struct_fields_variable_definitions(data_struct);
    let property_definitions = derive_struct_fields_property_definitions(data_struct);

    quote! {
        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for #struct_name {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                #(#variable_definitions)*

                #data_structure_definition

                #(#property_definitions)*

                Ok(py_data_structure.into_object())
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for Vec<#struct_name> {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                try_into_vm_value_generic_array(self, ())
            }
        }
    }
}

fn derive_data_structure_definition(data_struct: &DataStruct) -> TokenStream {
    match &data_struct.fields {
        Fields::Named(_) => quote! {
            let py_data_structure = basilisk_cpython::PyDict::new()
                .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
        },
        Fields::Unnamed(fields_unnamed) => {
            let field_names: Vec<TokenStream> = fields_unnamed
                .unnamed
                .iter()
                .enumerate()
                .map(|(index, _)| {
                    let field_name = format_ident!("field_{}_js_value", index);
                    quote!(#field_name)
                })
                .collect();

            quote! {
                let py_data_structure = basilisk_cpython::PyTuple::new(vec![#(#field_names),*])
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
            }
        }
        _ => panic!("Only named and unnamed fields supported for Structs"),
    }
}

fn derive_struct_fields_variable_definitions(data_struct: &DataStruct) -> Vec<TokenStream> {
    match &data_struct.fields {
        Fields::Named(fields_named) => fields_named
            .named
            .iter()
            .map(|field| {
                let field_name = field.ident.as_ref().expect("Named field must have a name");
                let variable_name = format_ident!("{}_js_value", field_name);

                quote! {
                    let #variable_name = self.#field_name.try_into_vm_value(())?;
                }
            })
            .collect(),
        Fields::Unnamed(fields_unnamed) => fields_unnamed
            .unnamed
            .iter()
            .enumerate()
            .map(|(index, _)| {
                let variable_name = format_ident!("field_{}_js_value", index);
                let syn_index = Index::from(index);

                quote! {
                    let #variable_name = self.#syn_index.try_into_vm_value(())?;
                }
            })
            .collect(),
        _ => panic!("Only named and unnamed fields supported for Structs"),
    }
}

fn derive_struct_fields_property_definitions(data_struct: &DataStruct) -> Vec<TokenStream> {
    match &data_struct.fields {
        Fields::Named(fields_named) => fields_named
            .named
            .iter()
            .map(|field| {
                let field_name = field.ident.as_ref().expect("Named field must have a name");
                let variable_name = format_ident!("{}_js_value", field_name);

                let restored_field_name = cdk_framework::keyword::restore_for_vm(
                    &field_name.to_string(),
                    &crate::get_python_keywords(),
                )
                .to_ident();

                quote! {
                    py_data_structure.set_item_str(
                        stringify!(#restored_field_name),
                        &#variable_name,
                    ).map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                }
            })
            .collect(),
        Fields::Unnamed(_) => vec![],
        _ => panic!("Only named and unnamed fields supported for Structs"),
    }
}
