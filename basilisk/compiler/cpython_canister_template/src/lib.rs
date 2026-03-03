//! CPython Canister Template
//!
//! This is an azle-style pre-compiled canister template. It contains all the
//! identical boilerplate code that every CPython-based basilisk canister needs:
//! - Type conversion traits (CdkActTryIntoVmValue / CdkActTryFromVmValue)
//! - Async result handler for cross-canister calls
//! - IC API bindings (_basilisk_ic CPython module)
//! - CPython initialization
//! - Generic method dispatch via dynamic Candid
//!
//! Per-project customization (Python source code, method metadata) is injected
//! as passive data segments via wasm binary manipulation at build time.

#![allow(warnings, unused)]

use basilisk_cpython::{
    Interpreter, PyDict, PyError, PyObjectRef, PyTuple, Scope,
    TryFromPyObject as _BasiliskTraitTryFromPyObject,
    TryIntoPyObject as _BasiliskTraitTryIntoPyObject,
};
use candid::{Decode, Encode};
use serde::{
    de::{DeserializeSeed as _BasiliskTraitDeserializeSeed, Visitor as _BasiliskTraitVisitor},
    ser::{
        Serialize as _BasiliskTraitSerialize, SerializeMap as _BasiliskTraitSerializeMap,
        SerializeSeq as _BasiliskTraitSerializeSeq,
        SerializeTuple as _BasiliskTraitSerializeTuple,
    },
};
use slotmap::Key as _BasiliskTraitSlotMapKey;
use std::{convert::TryInto as _BasiliskTraitTryInto, str::FromStr as _BasiliskTraitFromStr};

mod ic_api;
mod type_conversions;
mod async_handler;
mod python_init;
mod method_dispatch;
mod wasm_data;

// Re-export from submodules
use type_conversions::*;
use async_handler::*;
use python_init::*;
use method_dispatch::*;
use wasm_data::*;

// ─── Global state ───────────────────────────────────────────────────────────

static mut INTERPRETER_OPTION: Option<basilisk_cpython::Interpreter> = None;
static mut SCOPE_OPTION: Option<basilisk_cpython::Scope> = None;
static mut CPYTHON_INIT_DONE: bool = false;
static mut PRINCIPAL_CLASS_OPTION: Option<basilisk_cpython::PyObjectRef> = None;
/// Current method's return type string — set before calling Manual[T] methods
/// so that ic.reply() knows how to encode the value.
static mut CURRENT_RETURN_TYPE: Option<String> = None;

// ─── RNG ────────────────────────────────────────────────────────────────────

#[cfg(all(target_arch = "wasm32", target_os = "wasi"))]
fn rng_seed() {
    ic_cdk::spawn(async move {
        let result: ic_cdk::api::call::CallResult<(Vec<u8>,)> =
            ic_cdk::api::management_canister::main::raw_rand().await;
        match result {
            Ok((randomness,)) => ic_wasi_polyfill::init_seed(&randomness),
            Err(err) => panic!("{:?}", err),
        };
    });
}

// ─── Canister lifecycle ─────────────────────────────────────────────────────

#[ic_cdk_macros::init]
#[candid::candid_method(init)]
fn init() {
    ic_wasi_polyfill::init(&[], &[]);

    let python_code = get_python_code();
    let (method_meta, type_defs, lifecycle) = get_method_metadata();

    cpython_full_init(&python_code);

    unsafe {
        METHOD_METADATA = Some(method_meta);
        TYPE_DEFS = Some(type_defs);
        LIFECYCLE = Some(lifecycle);
    }

    // Call user-defined @init function if present
    call_lifecycle_hook("init");

    // Restore StableBTreeMap instances from stable memory (if upgrading with data)
    call_python_function("_basilisk_load_stable_maps");
}

#[ic_cdk_macros::post_upgrade]
fn post_upgrade() {
    ic_wasi_polyfill::init(&[], &[]);

    let python_code = get_python_code();
    let (method_meta, type_defs, lifecycle) = get_method_metadata();

    cpython_full_init(&python_code);

    unsafe {
        METHOD_METADATA = Some(method_meta);
        TYPE_DEFS = Some(type_defs);
        LIFECYCLE = Some(lifecycle);
    }

    // Call user-defined @post_upgrade function if present
    call_lifecycle_hook("post_upgrade");

    // Restore StableBTreeMap instances from stable memory
    call_python_function("_basilisk_load_stable_maps");
}

#[ic_cdk_macros::pre_upgrade]
fn pre_upgrade() {
    // Save StableBTreeMap instances to stable memory before upgrade
    call_python_function("_basilisk_save_stable_maps");

    // Call user-defined @pre_upgrade function if present
    // CPython is already initialized from the original init/post_upgrade
    call_lifecycle_hook("pre_upgrade");
}

#[ic_cdk_macros::heartbeat]
fn heartbeat() {
    // Only call if user defined a @heartbeat function
    call_lifecycle_hook("heartbeat");
}

#[ic_cdk_macros::inspect_message]
fn inspect_message() {
    // Call user-defined @inspect_message function if present.
    // The Python function should call ic.accept_message() to allow the call.
    // If no inspect_message hook is defined, accept all messages by default.
    let has_hook = unsafe {
        LIFECYCLE
            .as_ref()
            .map(|lc| lc.contains_key("inspect_message"))
            .unwrap_or(false)
    };
    if has_hook {
        call_lifecycle_hook("inspect_message");
    } else {
        ic_cdk::api::call::accept_message();
    }
}

// ─── Generic method execution ───────────────────────────────────────────────
// These are placeholder functions that get called by the canister_query/update
// export stubs added via wasm manipulation. The index maps to the method
// metadata array.

#[no_mangle]
pub extern "C" fn execute_query_method(method_index: i32) {
    execute_canister_method(method_index, false);
}

#[no_mangle]
pub extern "C" fn execute_update_method(method_index: i32) {
    execute_canister_method(method_index, true);
}
