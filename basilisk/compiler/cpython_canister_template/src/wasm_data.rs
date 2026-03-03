//! Passive data segment reading.
//!
//! At build time, the wasm manipulator injects two passive data segments:
//! 1. Python source code (UTF-8)
//! 2. Method metadata (JSON) — contains methods array + type_defs map
//!
//! This module provides placeholder functions that the wasm manipulator
//! replaces with actual data segment initialization code.

use std::collections::HashMap;

/// Top-level metadata JSON structure injected by the wasm manipulator.
#[derive(serde::Deserialize, Debug)]
pub struct Metadata {
    pub methods: Vec<MethodInfo>,
    /// Named Candid type definitions, e.g. {"User": "record { id : text; name : text }"}
    #[serde(default)]
    pub type_defs: HashMap<String, String>,
    /// Lifecycle hooks: init, pre_upgrade, post_upgrade, heartbeat, inspect_message
    #[serde(default)]
    pub lifecycle: HashMap<String, MethodInfo>,
}

/// Method metadata for a single canister method.
#[derive(serde::Deserialize, Debug, Clone)]
pub struct MethodInfo {
    pub name: String,
    pub method_type: String, // "query" or "update"
    pub params: Vec<ParamInfo>,
    pub returns: String,     // Candid type string (may reference named types)
    #[serde(default)]
    pub guard: Option<String>, // Optional guard function name
    #[serde(default)]
    pub manual_reply: bool, // If true, Python function calls ic.reply() itself
    #[serde(default)]
    pub is_async: bool, // If true, function is a generator (uses yield for cross-canister calls)
}

/// Parameter metadata.
#[derive(serde::Deserialize, Debug, Clone)]
pub struct ParamInfo {
    pub name: String,
    pub candid_type: String,
}

/// Global storage for method metadata (populated at init).
pub static mut METHOD_METADATA: Option<Vec<MethodInfo>> = None;

/// Global storage for named type definitions (populated at init).
pub static mut TYPE_DEFS: Option<HashMap<String, String>> = None;

/// Global storage for lifecycle hooks (populated at init).
pub static mut LIFECYCLE: Option<HashMap<String, MethodInfo>> = None;

// ─── Placeholder functions (defined in C: cpython_init_helper.c) ────────────
// These are compiled by WASI SDK clang as opaque object code, immune to
// Rust's LTO. The wasm manipulator patches their bodies at build time.
extern "C" {
    pub fn python_source_passive_data_size() -> i32;
    pub fn method_meta_passive_data_size() -> i32;
    pub fn init_python_source_passive_data(dest: i32);
    pub fn init_method_meta_passive_data(dest: i32);
}

/// Read the Python source code from the passive data segment.
pub fn get_python_code() -> String {
    let size = unsafe { python_source_passive_data_size() } as usize;
    if size == 0 {
        return String::new();
    }
    let mut buffer = vec![0u8; size];
    unsafe { init_python_source_passive_data(buffer.as_mut_ptr() as i32) };
    String::from_utf8(buffer).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Invalid UTF-8 in Python source: {}", e));
    })
}

/// Read the method metadata JSON from the passive data segment.
/// Returns (methods, type_defs, lifecycle).
pub fn get_method_metadata() -> (Vec<MethodInfo>, HashMap<String, String>, HashMap<String, MethodInfo>) {
    let size = unsafe { method_meta_passive_data_size() } as usize;
    if size == 0 {
        return (Vec::new(), HashMap::new(), HashMap::new());
    }
    let mut buffer = vec![0u8; size];
    unsafe { init_method_meta_passive_data(buffer.as_mut_ptr() as i32) };
    let json_str = String::from_utf8(buffer).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Invalid UTF-8 in method metadata: {}", e));
    });

    // Try new format first (wrapped object with methods + type_defs + lifecycle)
    if let Ok(metadata) = serde_json::from_str::<Metadata>(&json_str) {
        return (metadata.methods, metadata.type_defs, metadata.lifecycle);
    }

    // Fall back to old format (bare array of methods) for backwards compatibility
    let methods: Vec<MethodInfo> = serde_json::from_str(&json_str).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Invalid method metadata JSON: {}", e));
    });
    (methods, HashMap::new(), HashMap::new())
}
