//! CPython-specific use statements for generated canister code.
//!
//! Replaces `header/use_statements.rs` when CPython backend is selected.
//! Instead of importing from `rustpython_vm`, we import from `basilisk_cpython`.

use proc_macro2::TokenStream;

pub fn generate() -> TokenStream {
    quote::quote! {
        use candid::{Decode, Encode};
        use basilisk_vm_value_derive::{CdkActTryIntoVmValue, CdkActTryFromVmValue};
        use basilisk_cpython::{
            PyObjectRef,
            PyError,
            PyDict,
            PyTuple,
            Interpreter,
            Scope,
            TryIntoPyObject as _BasiliskTraitTryIntoPyObject,
            TryFromPyObject as _BasiliskTraitTryFromPyObject,
            UnwrapOrTrap as _BasiliskTraitUnwrapOrTrap,
        };
        use serde::{
            de::{
                DeserializeSeed as _BasiliskTraitDeserializeSeed,
                Visitor as _BasiliskTraitVisitor
            },
            ser::{
                Serialize as _BasiliskTraitSerialize,
                SerializeMap as _BasiliskTraitSerializeMap,
                SerializeSeq as _BasiliskTraitSerializeSeq,
                SerializeTuple as _BasiliskTraitSerializeTuple
            }
        };
        use slotmap::Key as _BasiliskTraitSlotMapKey;
        use std::{
            convert::TryInto as _BasiliskTraitTryInto,
            str::FromStr as _BasiliskTraitFromStr
        };
    }
}
