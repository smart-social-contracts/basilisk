def generate_cargo_toml(canister_name: str) -> str:
    return f"""
[package]
name = "{canister_name}"
version = "0.0.0"
edition = "2021"

[profile.release]
opt-level = 'z'
lto = true
incremental = false
codegen-units = 1

[lib]
crate-type = ["cdylib"]

[features]
default = []

[dependencies]
ic-cdk = "0.13.5"
ic-cdk-macros = "0.9.0"
ic-cdk-timers = "0.7.0"
candid = {{ version = "0.10.6", features = ["value"] }}
candid_parser = "0.1.4"
basilisk-vm-value-derive = {{ path = "./basilisk_vm_value_derive" }}
basilisk_cpython = {{ path = "./basilisk_cpython" }}
num-bigint = "0.4"

serde = {{ version = "1.0.137", default-features = false, features = [] }}
async-recursion = "1.0.0"
ic-stable-structures = "0.6.5"
slotmap = "1.0.6"

ic-wasi-polyfill = {{ version = "0.6.1", features = [
    "transient",
] }}

[patch.crates-io]
num-bigint = {{ git = "https://github.com/rust-num/num-bigint" }}
    """
