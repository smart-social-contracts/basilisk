use proc_macro2::TokenStream;

pub fn generate() -> TokenStream {
    quote::quote! {
        use candid::{Decode, Encode};
        use basilisk_vm_value_derive::{CdkActTryIntoVmValue, CdkActTryFromVmValue};
        use rustpython_vm::{
            class::PyClassImpl as _BasiliskTraitPyClassImpl,
            convert::ToPyObject as _BasiliskTraitToPyObject,
            function::IntoFuncArgs as _BasiliskTraitIntoFuncArgs,
            AsObject as _BasiliskTraitAsObject,
            TryFromObject as _BasiliskTraitTryFromObject
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
