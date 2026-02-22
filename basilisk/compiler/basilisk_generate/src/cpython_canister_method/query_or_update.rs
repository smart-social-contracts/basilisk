//! CPython-specific query/update method body generation.
//!
//! Replaces `canister_method/query_or_update/rust.rs` when CPython backend is selected.
//! Generates method bodies that use basilisk_cpython instead of RustPython.

use proc_macro2::TokenStream;
use quote::{format_ident, quote};
use rustpython_parser::ast::{Located, StmtKind};

use crate::{method_utils::params::InternalOrExternal, source_map::SourceMapped, tuple, Error};

pub fn generate_body(
    source_mapped_located_stmtkind: &SourceMapped<&Located<StmtKind>>,
) -> Result<TokenStream, Vec<Error>> {
    let params = source_mapped_located_stmtkind.build_params(InternalOrExternal::Internal)?;

    let name = source_mapped_located_stmtkind.get_name_or_err()?;

    let param_conversions = params
        .iter()
        .map(|param| {
            let name = format_ident!("{}", param.get_prefixed_name());
            quote! {
                #name.try_into_py_object().unwrap_or_trap()
            }
        })
        .collect();

    let params = tuple::generate_tuple(&param_conversions);

    Ok(quote! {
        let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
            .unwrap_or_else(|| panic!("SystemError: missing python interpreter"));
        let params = #params;

        call_global_python_function(#name, params)
            .await
            .unwrap_or_trap()
    })
}
