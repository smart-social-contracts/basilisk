use proc_macro2::{Ident, Span};

/// Convert a string to a proc_macro2 Ident.
pub trait ToIdent {
    fn to_ident(&self) -> Ident;
}

impl ToIdent for String {
    fn to_ident(&self) -> Ident {
        Ident::new(self, Span::call_site())
    }
}

impl ToIdent for &str {
    fn to_ident(&self) -> Ident {
        Ident::new(self, Span::call_site())
    }
}

/// Restore a Rust identifier that was mangled to avoid Python keyword conflicts.
///
/// Candid field/variant names that collide with Python keywords get a trailing `_`
/// appended during code generation (e.g. `class` → `class_`). This function strips
/// that trailing `_` so the Python-side dict key matches the original Candid name.
pub fn restore_for_vm(name: &str, keywords: &[String]) -> String {
    if let Some(stripped) = name.strip_suffix('_') {
        if keywords.iter().any(|kw| kw == stripped) {
            return stripped.to_string();
        }
    }
    name.to_string()
}
