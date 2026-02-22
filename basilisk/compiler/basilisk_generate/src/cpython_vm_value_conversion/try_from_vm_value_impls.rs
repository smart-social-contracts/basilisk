//! CPython-specific TryFromVmValue implementations.
//!
//! Generates `CdkActTryFromVmValue` trait impls using basilisk_cpython.
//! These impls convert CPython PyObjectRef → Rust/Candid types.

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
        impl CdkActTryFromVmValue<(), basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<(), basilisk_cpython::PyError> {
                if self.is_none() {
                    Ok(())
                } else {
                    let type_name = self.type_name();
                    Err(basilisk_cpython::PyError::new(
                        "TypeError",
                        &format!("expected NoneType but received {type_name}"),
                    ))
                }
            }
        }

        impl CdkActTryFromVmValue<bool, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<bool, basilisk_cpython::PyError> {
                Ok(self.extract_bool())
            }
        }

        impl CdkActTryFromVmValue<candid::Empty, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<candid::Empty, basilisk_cpython::PyError> {
                Err(basilisk_cpython::PyError::new(
                    "TypeError",
                    "value cannot be converted to Empty",
                ))
            }
        }

        impl CdkActTryFromVmValue<candid::Func, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<candid::Func, basilisk_cpython::PyError> {
                let idx0 = basilisk_cpython::PyObjectRef::from_i64(0)?;
                let idx1 = basilisk_cpython::PyObjectRef::from_i64(1)?;
                let principal_obj = self.get_item(&idx0)?;
                let method_obj = self.get_item(&idx1)?;
                Ok(candid::Func {
                    principal: principal_obj.try_from_vm_value(())?,
                    method: method_obj.try_from_vm_value(())?,
                })
            }
        }

        impl CdkActTryFromVmValue<candid::Principal, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<candid::Principal, basilisk_cpython::PyError> {
                let to_str = self.get_attr("to_str")?;
                let args = basilisk_cpython::PyTuple::empty()?;
                let result = to_str.call(&args.into_object(), None)?;
                let result_string = result.extract_str()?;
                candid::Principal::from_text(&result_string).map_err(|err| {
                    basilisk_cpython::PyError::new(
                        "TypeError",
                        &format!("could not convert value to Principal: {}", err),
                    )
                })
            }
        }

        impl CdkActTryFromVmValue<candid::Reserved, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<candid::Reserved, basilisk_cpython::PyError> {
                Ok(candid::Reserved)
            }
        }

        impl CdkActTryFromVmValue<ic_cdk_timers::TimerId, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<ic_cdk_timers::TimerId, basilisk_cpython::PyError> {
                let val = self.extract_u64()?;
                Ok(ic_cdk_timers::TimerId::from(slotmap::KeyData::from_ffi(val)))
            }
        }

        impl CdkActTryFromVmValue<String, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<String, basilisk_cpython::PyError> {
                self.extract_str()
            }
        }

        impl CdkActTryFromVmValue<Result<(), String>, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<Result<(), String>, basilisk_cpython::PyError> {
                if let Ok(err_val) = self.get_item_str("Err") {
                    let s: String = err_val.try_from_vm_value(())?;
                    return Ok(Err(s));
                }
                if let Ok(ok_val) = self.get_item_str("Ok") {
                    let _: () = ok_val.try_from_vm_value(())?;
                    return Ok(Ok(()));
                }
                let type_name = self.type_name();
                Err(basilisk_cpython::PyError::new(
                    "TypeError",
                    &format!("expected Result but received {type_name}"),
                ))
            }
        }
    }
}

fn generate_numeric() -> TokenStream {
    quote::quote! {
        impl CdkActTryFromVmValue<f64, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<f64, basilisk_cpython::PyError> {
                self.extract_f64()
            }
        }

        impl CdkActTryFromVmValue<_CdkFloat64, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<_CdkFloat64, basilisk_cpython::PyError> {
                Ok(_CdkFloat64(self.extract_f64()?))
            }
        }

        impl CdkActTryFromVmValue<f32, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<f32, basilisk_cpython::PyError> {
                Ok(self.extract_f64()? as f32)
            }
        }

        impl CdkActTryFromVmValue<_CdkFloat32, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<_CdkFloat32, basilisk_cpython::PyError> {
                Ok(_CdkFloat32(self.extract_f64()? as f32))
            }
        }

        impl CdkActTryFromVmValue<candid::Int, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<candid::Int, basilisk_cpython::PyError> {
                let s = self.str_repr()?;
                let big_int: num_bigint::BigInt = s.parse().map_err(|e: num_bigint::ParseBigIntError| {
                    basilisk_cpython::PyError::new("TypeError", &format!("could not parse int: {}", e))
                })?;
                Ok(candid::Int(big_int))
            }
        }

        impl CdkActTryFromVmValue<i128, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<i128, basilisk_cpython::PyError> {
                Ok(self.extract_i64()? as i128)
            }
        }

        impl CdkActTryFromVmValue<i64, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<i64, basilisk_cpython::PyError> {
                self.extract_i64()
            }
        }

        impl CdkActTryFromVmValue<i32, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<i32, basilisk_cpython::PyError> {
                Ok(self.extract_i64()? as i32)
            }
        }

        impl CdkActTryFromVmValue<i16, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<i16, basilisk_cpython::PyError> {
                Ok(self.extract_i64()? as i16)
            }
        }

        impl CdkActTryFromVmValue<i8, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<i8, basilisk_cpython::PyError> {
                Ok(self.extract_i64()? as i8)
            }
        }

        impl CdkActTryFromVmValue<candid::Nat, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<candid::Nat, basilisk_cpython::PyError> {
                let s = self.str_repr()?;
                let big_uint: num_bigint::BigUint = s.parse().map_err(|e: num_bigint::ParseBigIntError| {
                    basilisk_cpython::PyError::new("TypeError", &format!("could not parse nat: {}", e))
                })?;
                Ok(candid::Nat(big_uint))
            }
        }

        impl CdkActTryFromVmValue<u128, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<u128, basilisk_cpython::PyError> {
                Ok(self.extract_u64()? as u128)
            }
        }

        impl CdkActTryFromVmValue<u64, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<u64, basilisk_cpython::PyError> {
                self.extract_u64()
            }
        }

        impl CdkActTryFromVmValue<usize, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<usize, basilisk_cpython::PyError> {
                Ok(self.extract_u64()? as usize)
            }
        }

        impl CdkActTryFromVmValue<u32, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<u32, basilisk_cpython::PyError> {
                Ok(self.extract_u64()? as u32)
            }
        }

        impl CdkActTryFromVmValue<u16, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<u16, basilisk_cpython::PyError> {
                Ok(self.extract_u64()? as u16)
            }
        }

        impl CdkActTryFromVmValue<u8, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<u8, basilisk_cpython::PyError> {
                Ok(self.extract_u64()? as u8)
            }
        }
    }
}

fn generate_generic() -> TokenStream {
    quote::quote! {
        impl<T> CdkActTryFromVmValue<(T,), basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef
        where
            basilisk_cpython::PyObjectRef: CdkActTryFromVmValue<T, basilisk_cpython::PyError, ()>,
        {
            fn try_from_vm_value(self, _: ()) -> Result<(T,), basilisk_cpython::PyError> {
                Ok((self.try_from_vm_value(())?,))
            }
        }

        impl<T> CdkActTryFromVmValue<Box<T>, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef
        where
            basilisk_cpython::PyObjectRef: CdkActTryFromVmValue<T, basilisk_cpython::PyError, ()>,
        {
            fn try_from_vm_value(self, _: ()) -> Result<Box<T>, basilisk_cpython::PyError> {
                Ok(Box::new(self.try_from_vm_value(())?))
            }
        }

        impl<T> CdkActTryFromVmValue<Option<T>, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef
        where
            basilisk_cpython::PyObjectRef: CdkActTryFromVmValue<T, basilisk_cpython::PyError, ()>,
        {
            fn try_from_vm_value(self, _: ()) -> Result<Option<T>, basilisk_cpython::PyError> {
                if self.is_none() {
                    Ok(None)
                } else {
                    Ok(Some(self.try_from_vm_value(())?))
                }
            }
        }
    }
}

fn generate_vec() -> TokenStream {
    quote::quote! {
        impl<T> CdkActTryFromVmValue<Vec<T>, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef
        where
            T: BasiliskTryIntoVec,
            basilisk_cpython::PyObjectRef: CdkActTryFromVmValue<T, basilisk_cpython::PyError, ()>,
        {
            fn try_from_vm_value(self, _: ()) -> Result<Vec<T>, basilisk_cpython::PyError> {
                try_from_vm_value_generic_array(self, ())
            }
        }

        impl CdkActTryFromVmValue<Vec<u8>, basilisk_cpython::PyError, ()> for basilisk_cpython::PyObjectRef {
            fn try_from_vm_value(self, _: ()) -> Result<Vec<u8>, basilisk_cpython::PyError> {
                self.extract_bytes()
            }
        }

        fn try_from_vm_value_generic_array<T>(
            obj: basilisk_cpython::PyObjectRef,
            _: (),
        ) -> Result<Vec<T>, basilisk_cpython::PyError>
        where
            basilisk_cpython::PyObjectRef: CdkActTryFromVmValue<T, basilisk_cpython::PyError, ()>,
        {
            unsafe {
                let len = basilisk_cpython::ffi::PySequence_Length(obj.as_ptr());
                if len < 0 {
                    return Err(basilisk_cpython::PyError::fetch());
                }
                let mut result = Vec::with_capacity(len as usize);
                for i in 0..len {
                    let item = basilisk_cpython::ffi::PySequence_GetItem(obj.as_ptr(), i);
                    if item.is_null() {
                        return Err(basilisk_cpython::PyError::fetch());
                    }
                    let py_obj = basilisk_cpython::PyObjectRef::from_owned(item)
                        .ok_or_else(|| basilisk_cpython::PyError::new("TypeError", "null item"))?;
                    result.push(py_obj.try_from_vm_value(())?);
                }
                Ok(result)
            }
        }
    }
}
