//! Passive data segment reading.
//!
//! At build time, the wasm manipulator injects two passive data segments:
//! 1. Python source code (UTF-8)
//! 2. Method metadata (JSON)
//!
//! This module provides placeholder functions that the wasm manipulator
//! replaces with actual data segment initialization code.

/// Method metadata for a single canister method.
#[derive(serde::Deserialize, Debug, Clone)]
pub struct MethodInfo {
    pub name: String,
    pub method_type: String, // "query" or "update"
    pub params: Vec<ParamInfo>,
    pub returns: String,     // Candid type string
}

/// Parameter metadata.
#[derive(serde::Deserialize, Debug, Clone)]
pub struct ParamInfo {
    pub name: String,
    pub candid_type: String,
}

/// Global storage for method metadata (populated at init).
pub static mut METHOD_METADATA: Option<Vec<MethodInfo>> = None;

// ─── Placeholder functions ──────────────────────────────────────────────────
// These functions are replaced by the wasm manipulator at build time.
// The wasm manipulator patches them to read from the injected passive
// data segments (same technique as azle's manipulate.ts).

/// Returns the size of the Python source passive data segment.
/// Replaced by wasm manipulator with the actual size constant.
#[no_mangle]
pub extern "C" fn python_source_passive_data_size() -> i32 {
    0 // placeholder — wasm manipulator replaces this function body
}

/// Returns the size of the method metadata passive data segment.
/// Replaced by wasm manipulator with the actual size constant.
#[no_mangle]
pub extern "C" fn method_meta_passive_data_size() -> i32 {
    0 // placeholder — wasm manipulator replaces this function body
}

/// Initialize the Python source passive data segment into linear memory.
/// Replaced by wasm manipulator with memory.init + data.drop instructions.
#[no_mangle]
pub extern "C" fn init_python_source_passive_data(_dest: i32) {
    // placeholder — wasm manipulator replaces this function body
}

/// Initialize the method metadata passive data segment into linear memory.
/// Replaced by wasm manipulator with memory.init + data.drop instructions.
#[no_mangle]
pub extern "C" fn init_method_meta_passive_data(_dest: i32) {
    // placeholder — wasm manipulator replaces this function body
}

/// Read the Python source code from the passive data segment.
pub fn get_python_code() -> String {
    let size = python_source_passive_data_size() as usize;
    if size == 0 {
        return String::new();
    }
    let mut buffer = vec![0u8; size];
    init_python_source_passive_data(buffer.as_mut_ptr() as i32);
    String::from_utf8(buffer).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Invalid UTF-8 in Python source: {}", e));
    })
}

/// Read the method metadata JSON from the passive data segment.
pub fn get_method_metadata() -> Vec<MethodInfo> {
    let size = method_meta_passive_data_size() as usize;
    if size == 0 {
        return Vec::new();
    }
    let mut buffer = vec![0u8; size];
    init_method_meta_passive_data(buffer.as_mut_ptr() as i32);
    let json_str = String::from_utf8(buffer).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Invalid UTF-8 in method metadata: {}", e));
    });
    serde_json::from_str(&json_str).unwrap_or_else(|e| {
        ic_cdk::trap(&format!("Invalid method metadata JSON: {}", e));
    })
}
