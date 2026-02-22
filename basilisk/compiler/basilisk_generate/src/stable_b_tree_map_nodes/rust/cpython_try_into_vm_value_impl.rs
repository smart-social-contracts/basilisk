use proc_macro2::TokenStream;
use syn::Ident;

pub fn generate(wrapper_type_name: &Ident) -> TokenStream {
    quote::quote! {
        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for #wrapper_type_name {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                Ok(self.0.try_into_vm_value(())?)
            }
        }
    }
}
