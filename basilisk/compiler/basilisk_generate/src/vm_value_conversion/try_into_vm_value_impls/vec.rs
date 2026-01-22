use proc_macro2::TokenStream;

pub fn generate() -> TokenStream {
    quote::quote! {
        trait BasiliskTryIntoVec {}

        impl BasiliskTryIntoVec for () {}

        impl BasiliskTryIntoVec for bool {}

        impl BasiliskTryIntoVec for String {}

        impl BasiliskTryIntoVec for candid::Empty {}

        impl BasiliskTryIntoVec for candid::Reserved {}

        impl BasiliskTryIntoVec for candid::Func {}

        impl BasiliskTryIntoVec for candid::Principal {}

        impl BasiliskTryIntoVec for ic_cdk_timers::TimerId {}

        impl BasiliskTryIntoVec for ic_cdk::api::call::RejectionCode {}

        impl BasiliskTryIntoVec for f64 {}

        impl BasiliskTryIntoVec for f32 {}

        impl BasiliskTryIntoVec for _CdkFloat64 {}

        impl BasiliskTryIntoVec for _CdkFloat32 {}

        impl BasiliskTryIntoVec for candid::Int {}

        impl BasiliskTryIntoVec for i128 {}

        impl BasiliskTryIntoVec for i64 {}

        impl BasiliskTryIntoVec for i32 {}

        impl BasiliskTryIntoVec for i16 {}

        impl BasiliskTryIntoVec for i8 {}

        impl BasiliskTryIntoVec for candid::Nat {}

        impl BasiliskTryIntoVec for u128 {}

        impl BasiliskTryIntoVec for u64 {}

        impl BasiliskTryIntoVec for usize {}

        impl BasiliskTryIntoVec for u32 {}

        impl BasiliskTryIntoVec for u16 {}

        impl<T> BasiliskTryIntoVec for Option<T> {}

        impl<T> BasiliskTryIntoVec for Box<T> {}

        impl<T> BasiliskTryIntoVec for Vec<T> {}

        impl<T> CdkActTryIntoVmValue<&rustpython::vm::VirtualMachine, rustpython::vm::PyObjectRef>
            for Vec<T>
        where
            T: BasiliskTryIntoVec,
            T: for<'a> CdkActTryIntoVmValue<
                &'a rustpython::vm::VirtualMachine,
                rustpython::vm::PyObjectRef,
            >,
        {
            fn try_into_vm_value(
                self,
                vm: &rustpython::vm::VirtualMachine,
            ) -> Result<rustpython::vm::PyObjectRef, CdkActTryIntoVmValueError> {
                try_into_vm_value_generic_array(self, vm)
            }
        }

        impl CdkActTryIntoVmValue<&rustpython::vm::VirtualMachine, rustpython::vm::PyObjectRef>
            for Vec<u8>
        {
            fn try_into_vm_value(
                self,
                vm: &rustpython::vm::VirtualMachine,
            ) -> Result<rustpython::vm::PyObjectRef, CdkActTryIntoVmValueError> {
                Ok(vm.ctx.new_bytes(self).into())
            }
        }


        fn try_into_vm_value_generic_array<T>(
            generic_array: Vec<T>,
            vm: &rustpython::vm::VirtualMachine,
        ) -> Result<rustpython::vm::PyObjectRef, CdkActTryIntoVmValueError>
        where
            T: for<'a> CdkActTryIntoVmValue<
                &'a rustpython::vm::VirtualMachine,
                rustpython::vm::PyObjectRef,
            >,
        {
            let py_object_refs_result: Result<Vec<rustpython_vm::PyObjectRef>, CdkActTryIntoVmValueError> = generic_array
                .into_iter()
                .map(|item| item.try_into_vm_value(vm))
                .collect();

            Ok(vm.ctx.new_list(py_object_refs_result?).into())
        }
    }
}
