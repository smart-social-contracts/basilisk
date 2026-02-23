use proc_macro2::TokenStream;
use syn::Ident;

pub fn generate(wrapper_type_name: &Ident) -> TokenStream {
    quote::quote! {
        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for #wrapper_type_name {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                Ok(self.0.try_into_vm_value(())?)
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for Vec<#wrapper_type_name> {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                unsafe {
                    let list = basilisk_cpython::ffi::PyList_New(self.len() as basilisk_cpython::ffi::Py_ssize_t);
                    if list.is_null() {
                        return Err(CdkActTryIntoVmValueError("Failed to create list".to_string()));
                    }
                    for (i, item) in self.into_iter().enumerate() {
                        let py_item = item.try_into_vm_value(())?;
                        basilisk_cpython::ffi::PyList_SetItem(
                            list,
                            i as basilisk_cpython::ffi::Py_ssize_t,
                            py_item.into_ptr(),
                        );
                    }
                    Ok(basilisk_cpython::PyObjectRef::from_owned(list)
                        .ok_or_else(|| CdkActTryIntoVmValueError("null list".to_string()))?)
                }
            }
        }
    }
}
