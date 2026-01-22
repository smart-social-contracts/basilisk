// TODO: There has got to be a better way to grab custom errors.
// Let's figure out how and then swap out all this code.

pub fn generate() -> proc_macro2::TokenStream {
    quote::quote! {
        struct BasiliskError {}

        impl BasiliskError {
            fn new(
                vm: &rustpython_vm::VirtualMachine,
                message: String,
            ) -> rustpython_vm::builtins::PyBaseExceptionRef {
                BasiliskError::subtype(vm, "Error", message)
            }

            fn subtype(
                vm: &rustpython_vm::VirtualMachine,
                subtype: &str,
                message: String,
            ) -> rustpython_vm::builtins::PyBaseExceptionRef {
                let basilisk_error_class = match vm
                    .run_block_expr(
                        vm.new_scope_with_builtins(),
                        format!("from basilisk import {subtype}; {subtype}").as_str(),
                    ) {
                        Ok(basilisk_error_class) => basilisk_error_class,
                        Err(py_base_exception) => return py_base_exception
                    };

                let py_type_ref =
                    match rustpython_vm::builtins::PyTypeRef::try_from_object(vm, basilisk_error_class)
                    {
                        Ok(py_type_ref) => py_type_ref,
                        Err(py_base_exception) => return py_base_exception
                    };

                vm.new_exception_msg(py_type_ref, message)
            }
        }

        struct CandidError {}

        impl CandidError {
            fn new(
                vm: &rustpython_vm::VirtualMachine,
                message: String,
            ) -> rustpython_vm::builtins::PyBaseExceptionRef {
                BasiliskError::subtype(vm, "CandidError", message)
            }
        }
    }
}
