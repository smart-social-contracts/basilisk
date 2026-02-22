//! CPython-specific TryIntoVmValue implementations.
//!
//! Generates `CdkActTryIntoVmValue` trait impls using basilisk_cpython.
//! These impls convert Rust/Candid types → CPython PyObjectRef.

use proc_macro2::TokenStream;

pub fn generate() -> TokenStream {
    let basic = generate_basic();
    let numeric = generate_numeric();
    let generic = generate_generic();
    let vec = generate_vec();

    quote::quote! {
        #basic
        #numeric
        #generic
        #vec
    }
}

fn generate_basic() -> TokenStream {
    quote::quote! {
        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for () {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                Ok(basilisk_cpython::PyObjectRef::none())
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for bool {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                Ok(basilisk_cpython::PyObjectRef::from_bool(self))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for candid::Empty {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                Err(CdkActTryIntoVmValueError("type \"empty\" cannot be represented in python".to_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for candid::Func {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                let principal = self.principal.try_into_vm_value(())?;
                let method = self.method.try_into_vm_value(())?;
                let tuple = basilisk_cpython::PyTuple::new(vec![principal, method])
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                Ok(tuple.into_object())
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for candid::Principal {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                    .ok_or_else(|| CdkActTryIntoVmValueError("missing interpreter".to_string()))?;

                let principal_class = interpreter.eval_expression(
                    "from basilisk import Principal; Principal"
                ).map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;

                let from_str = principal_class.get_attr("from_str")
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;

                let text = basilisk_cpython::PyObjectRef::from_str(&self.to_text())
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                let args = basilisk_cpython::PyTuple::new(vec![text])
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;

                from_str.call(&args.into_object(), None)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for ic_cdk::api::call::RejectionCode {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                let attribute = match self {
                    ic_cdk::api::call::RejectionCode::NoError => "NoError",
                    ic_cdk::api::call::RejectionCode::SysFatal => "SysFatal",
                    ic_cdk::api::call::RejectionCode::SysTransient => "SysTransient",
                    ic_cdk::api::call::RejectionCode::DestinationInvalid => "DestinationInvalid",
                    ic_cdk::api::call::RejectionCode::CanisterReject => "CanisterReject",
                    ic_cdk::api::call::RejectionCode::CanisterError => "CanisterError",
                    ic_cdk::api::call::RejectionCode::Unknown => "Unknown",
                };
                let dict = basilisk_cpython::PyDict::new()
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                let none = basilisk_cpython::PyObjectRef::none();
                dict.set_item_str(attribute, &none)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                Ok(dict.into_object())
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for candid::Reserved {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                Ok(basilisk_cpython::PyObjectRef::none())
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for ic_cdk_timers::TimerId {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                let ffi_val = self.data().as_ffi();
                basilisk_cpython::PyObjectRef::from_u64(ffi_val)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for ic_cdk::api::stable::StableMemoryError {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                let attribute = match self {
                    ic_cdk::api::stable::StableMemoryError::OutOfMemory => "OutOfMemory",
                    ic_cdk::api::stable::StableMemoryError::OutOfBounds => "OutOfBounds",
                };
                let dict = basilisk_cpython::PyDict::new()
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                let none = basilisk_cpython::PyObjectRef::none();
                dict.set_item_str(attribute, &none)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                Ok(dict.into_object())
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for String {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_str(&self)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for ic_stable_structures::btreemap::InsertError {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                match self {
                    ic_stable_structures::btreemap::InsertError::KeyTooLarge { given, max } => {
                        let dict = basilisk_cpython::PyDict::new()
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        let inner = basilisk_cpython::PyDict::new()
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        inner.set_item_str("given", &given.try_into_vm_value(())?)
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        inner.set_item_str("max", &max.try_into_vm_value(())?)
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        dict.set_item_str("KeyTooLarge", &inner.into_object())
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        Ok(dict.into_object())
                    },
                    ic_stable_structures::btreemap::InsertError::ValueTooLarge { given, max } => {
                        let dict = basilisk_cpython::PyDict::new()
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        let inner = basilisk_cpython::PyDict::new()
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        inner.set_item_str("given", &given.try_into_vm_value(())?)
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        inner.set_item_str("max", &max.try_into_vm_value(())?)
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        dict.set_item_str("ValueTooLarge", &inner.into_object())
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        Ok(dict.into_object())
                    }
                }
            }
        }
    }
}

fn generate_numeric() -> TokenStream {
    quote::quote! {
        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for f64 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_f64(self)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for _CdkFloat64 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                self.0.try_into_vm_value(())
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for f32 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_f64(self as f64)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for _CdkFloat32 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                self.0.try_into_vm_value(())
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for candid::Int {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                // Convert BigInt to string then to Python int
                let s = self.0.to_string();
                let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                    .ok_or_else(|| CdkActTryIntoVmValueError("missing interpreter".to_string()))?;
                interpreter.eval_expression(&format!("int('{}')", s))
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for i128 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_i64(self as i64)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for i64 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_i64(self)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for i32 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_i64(self as i64)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for i16 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_i64(self as i64)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for i8 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_i64(self as i64)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for candid::Nat {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                let s = self.0.to_string();
                let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                    .ok_or_else(|| CdkActTryIntoVmValueError("missing interpreter".to_string()))?;
                interpreter.eval_expression(&format!("int('{}')", s))
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for u128 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_u64(self as u64)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for u64 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_u64(self)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for usize {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_u64(self as u64)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for u32 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_u64(self as u64)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for u16 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_u64(self as u64)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for u8 {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_u64(self as u64)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }
    }
}

fn generate_generic() -> TokenStream {
    quote::quote! {
        impl<T> CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for (T,)
        where
            T: CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>,
        {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                self.0.try_into_vm_value(())
            }
        }

        impl<T> CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for Box<T>
        where
            T: CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>,
        {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                (*self).try_into_vm_value(())
            }
        }

        impl<T> CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for Option<T>
        where
            T: CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>,
        {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                match self {
                    Some(value) => value.try_into_vm_value(()),
                    None => Ok(basilisk_cpython::PyObjectRef::none()),
                }
            }
        }

        impl<T, K> CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef> for Result<T, K>
        where
            T: CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>,
            K: CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>,
        {
            fn try_into_vm_value(self, _: ()) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                match self {
                    Ok(ok) => {
                        let dict = basilisk_cpython::PyDict::new()
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        dict.set_item_str("Ok", &ok.try_into_vm_value(())?)
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        Ok(dict.into_object())
                    },
                    Err(err) => {
                        let dict = basilisk_cpython::PyDict::new()
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        dict.set_item_str("Err", &err.try_into_vm_value(())?)
                            .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))?;
                        Ok(dict.into_object())
                    }
                }
            }
        }
    }
}

fn generate_vec() -> TokenStream {
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

        impl<T> CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>
            for Vec<T>
        where
            T: BasiliskTryIntoVec,
            T: CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>,
        {
            fn try_into_vm_value(
                self,
                _: (),
            ) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                try_into_vm_value_generic_array(self, ())
            }
        }

        impl CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>
            for Vec<u8>
        {
            fn try_into_vm_value(
                self,
                _: (),
            ) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError> {
                basilisk_cpython::PyObjectRef::from_bytes(&self)
                    .map_err(|e| CdkActTryIntoVmValueError(e.to_rust_err_string()))
            }
        }

        fn try_into_vm_value_generic_array<T>(
            generic_array: Vec<T>,
            _: (),
        ) -> Result<basilisk_cpython::PyObjectRef, CdkActTryIntoVmValueError>
        where
            T: CdkActTryIntoVmValue<(), basilisk_cpython::PyObjectRef>,
        {
            let py_items: Result<Vec<basilisk_cpython::PyObjectRef>, _> = generic_array
                .into_iter()
                .map(|item| item.try_into_vm_value(()))
                .collect();
            let items = py_items?;

            unsafe {
                let list = basilisk_cpython::ffi::PyList_New(items.len() as basilisk_cpython::ffi::Py_ssize_t);
                if list.is_null() {
                    return Err(CdkActTryIntoVmValueError("Failed to create list".to_string()));
                }
                for (i, item) in items.into_iter().enumerate() {
                    basilisk_cpython::ffi::PyList_SetItem(
                        list,
                        i as basilisk_cpython::ffi::Py_ssize_t,
                        item.into_ptr(),
                    );
                }
                Ok(basilisk_cpython::PyObjectRef::from_owned(list)
                    .ok_or_else(|| CdkActTryIntoVmValueError("null list".to_string()))?)
            }
        }
    }
}
