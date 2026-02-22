//! Python backend selection.
//!
//! Reads the `BASILISK_PYTHON_BACKEND` environment variable to determine
//! whether to generate code targeting RustPython or CPython.

/// The Python interpreter backend to target in generated code.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PythonBackend {
    RustPython,
    CPython,
}

/// Get the selected Python backend from the environment.
///
/// Reads `BASILISK_PYTHON_BACKEND`:
/// - `"cpython"` → `PythonBackend::CPython`
/// - anything else (or unset) → `PythonBackend::RustPython`
pub fn get_python_backend() -> PythonBackend {
    match std::env::var("BASILISK_PYTHON_BACKEND") {
        Ok(val) if val.eq_ignore_ascii_case("cpython") => PythonBackend::CPython,
        _ => PythonBackend::RustPython,
    }
}

/// Returns true if the CPython backend is selected.
pub fn use_cpython() -> bool {
    get_python_backend() == PythonBackend::CPython
}
