//! CPython interpreter lifecycle management.
//!
//! Provides `Interpreter` and `Scope` types that mirror the RustPython equivalents:
//! - `rustpython_vm::Interpreter` → `basilisk_cpython::Interpreter`
//! - `rustpython_vm::scope::Scope` → `basilisk_cpython::Scope`
//!
//! The Interpreter manages CPython initialization and provides access to the VM.
//! The Scope holds the globals/locals dict for executing user Python code.

use crate::ffi;
use crate::object::{PyError, PyObjectRef};
use core::ffi::c_char;

/// Produce a Python repr()-style string literal from a Rust &str.
/// Wraps the string in single quotes and escapes backslashes, single quotes,
/// newlines, carriage returns, and tabs.
fn python_repr(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('\'');
    for ch in s.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\'' => out.push_str("\\'"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c => out.push(c),
        }
    }
    out.push('\'');
    out
}

/// Manages the CPython interpreter lifecycle.
///
/// Equivalent to `rustpython_vm::Interpreter` in the current codebase.
/// On the IC, there is exactly one interpreter per canister.
pub struct Interpreter {
    /// The __main__ module's global dict. All user code executes in this namespace.
    globals: *mut ffi::PyObject,
    /// Whether we own the interpreter (and should finalize it on drop).
    owned: bool,
}

unsafe impl Send for Interpreter {}
unsafe impl Sync for Interpreter {}

/// Holds the execution scope (globals dict) for Python code.
///
/// Equivalent to `rustpython_vm::scope::Scope` in the current codebase.
pub struct Scope {
    pub globals: PyObjectRef,
}

unsafe impl Send for Scope {}
unsafe impl Sync for Scope {}

impl Interpreter {
    /// Initialize CPython and create a new interpreter.
    ///
    /// This is the equivalent of:
    /// ```ignore
    /// let interpreter = rustpython_vm::Interpreter::with_init(Default::default(), |vm| {
    ///     vm.add_native_modules(rustpython_stdlib::get_module_inits());
    ///     vm.add_frozen(rustpython_vm::py_freeze!(dir = "python_source"));
    ///     vm.add_frozen(rustpython_compiler_core::frozen_lib::FrozenLib::from_ref(PYTHON_STDLIB));
    /// });
    /// ```
    pub fn initialize() -> Result<Self, PyError> {
        unsafe {
            // Use our own init check since Py_IsInitialized() returns 0
            // for core-only init (_init_main=0).
            extern "C" {
                fn basilisk_cpython_init() -> i32;
                fn basilisk_cpython_is_initialized() -> i32;
            }
            if basilisk_cpython_is_initialized() == 0 && ffi::Py_IsInitialized() == 0 {
                // Initialize CPython via C helper which uses PyConfig with
                // _init_main=0 to skip sys.streams setup (needs encodings).
                // Core init is sufficient for running Python code on the IC.
                let rc = basilisk_cpython_init();
                if rc != 0 {
                    return Err(PyError::new(
                        "SystemError",
                        "Failed to initialize CPython interpreter via C helper",
                    ));
                }
            }

            // Get the __main__ module's globals dict
            let main_module = ffi::PyImport_AddModule(b"__main__\0".as_ptr() as *const c_char);
            if main_module.is_null() {
                return Err(PyError::fetch());
            }

            let globals = ffi::PyModule_GetDict(main_module); // borrowed ref
            if globals.is_null() {
                return Err(PyError::fetch());
            }
            ffi::Py_IncRef(globals); // take ownership

            // Set up builtins reference in globals (needed for exec/eval)
            let builtins = ffi::PyImport_ImportModule(b"builtins\0".as_ptr() as *const c_char);
            if !builtins.is_null() {
                ffi::PyDict_SetItemString(
                    globals,
                    b"__builtins__\0".as_ptr() as *const c_char,
                    builtins,
                );
                ffi::Py_DecRef(builtins);
            }

            Ok(Interpreter {
                globals,
                owned: true,
            })
        }
    }

    /// Convert a null-terminated ASCII/UTF-8 string to a Vec of wchar_t (UTF-32).
    /// The input must end with '\0'. Each char is widened to i32.
    fn str_to_wchar(s: &str) -> Vec<ffi::wchar_t> {
        s.chars().map(|c| c as ffi::wchar_t).collect()
    }

    /// Create a new scope with builtins available.
    ///
    /// Equivalent to `interpreter.enter(|vm| vm.new_scope_with_builtins())`.
    pub fn new_scope(&self) -> Scope {
        unsafe {
            ffi::Py_IncRef(self.globals);
            Scope {
                globals: PyObjectRef::from_owned(self.globals).unwrap(),
            }
        }
    }

    /// Get the globals dict pointer (for use in PyRun_String etc.)
    pub fn globals_ptr(&self) -> *mut ffi::PyObject {
        self.globals
    }

    /// Execute a string of Python code in the interpreter's global scope.
    ///
    /// Equivalent to `vm.run_code_string(scope, code, "")`.
    pub fn run_code_string(&self, code: &str) -> Result<PyObjectRef, PyError> {
        let c_code = crate::object::make_cstring(code);
        unsafe {
            let result = ffi::PyRun_String(
                c_code.as_ptr() as *const c_char,
                ffi::PY_FILE_INPUT,
                self.globals,
                self.globals,
            );
            if result.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef::from_owned(result).unwrap_or_else(|| PyObjectRef::none()))
            }
        }
    }

    /// Evaluate a Python expression and return the result.
    pub fn eval_expression(&self, expr: &str) -> Result<PyObjectRef, PyError> {
        let c_expr = crate::object::make_cstring(expr);
        unsafe {
            let result = ffi::PyRun_String(
                c_expr.as_ptr() as *const c_char,
                ffi::PY_EVAL_INPUT,
                self.globals,
                self.globals,
            );
            if result.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef::from_owned(result).unwrap_or_else(|| PyObjectRef::none()))
            }
        }
    }

    /// Import a module and execute "from <module> import *" in the global scope.
    ///
    /// Equivalent to:
    /// ```ignore
    /// vm.run_code_string(scope, &format!("from {} import *", module_name), "")
    /// ```
    pub fn import_star(&self, module_name: &str) -> Result<(), PyError> {
        let code = format!("from {} import *", module_name);
        self.run_code_string(&code)?;
        Ok(())
    }

    /// Import a module by name.
    pub fn import_module(&self, name: &str) -> Result<PyObjectRef, PyError> {
        let c_name = crate::object::make_cstring(name);
        unsafe {
            let module = ffi::PyImport_ImportModule(c_name.as_ptr() as *const c_char);
            if module.is_null() {
                Err(PyError::fetch())
            } else {
                Ok(PyObjectRef::from_owned(module).unwrap())
            }
        }
    }

    /// Set a global variable in the interpreter's namespace.
    ///
    /// Equivalent to `vm.builtins.set_attr(name, value, vm)`.
    pub fn set_global(&self, name: &str, value: PyObjectRef) -> Result<(), PyError> {
        let c_name = crate::object::make_cstring(name);
        unsafe {
            let result = ffi::PyDict_SetItemString(
                self.globals,
                c_name.as_ptr() as *const c_char,
                value.as_ptr(),
            );
            if result < 0 {
                Err(PyError::fetch())
            } else {
                Ok(())
            }
        }
    }

    /// Get a global variable from the interpreter's namespace.
    ///
    /// Equivalent to `scope.globals.get_item(name, vm)`.
    pub fn get_global(&self, name: &str) -> Result<PyObjectRef, PyError> {
        let c_name = crate::object::make_cstring(name);
        unsafe {
            let item = ffi::PyDict_GetItemString(self.globals, c_name.as_ptr() as *const c_char);
            if item.is_null() {
                Err(PyError::new("KeyError", &format!("'{}'", name)))
            } else {
                // PyDict_GetItemString returns a borrowed ref
                Ok(PyObjectRef::from_borrowed(item).unwrap())
            }
        }
    }

    /// Set a value in the builtins module (accessible from all Python code).
    pub fn set_builtin(&self, name: &str, value: PyObjectRef) -> Result<(), PyError> {
        let builtins = self.import_module("builtins")?;
        builtins.set_attr(name, &value)
    }

    /// Add a frozen module source (for bundled Python modules).
    ///
    /// Adds the source code as a module that can be imported.
    pub fn add_frozen_source(&self, module_name: &str, source: &str) -> Result<(), PyError> {
        // Use importlib to add the source as a module
        let code = format!(
            "
import importlib
import importlib.util
import types
_mod = types.ModuleType(\"{name}\")
_mod.__file__ = \"<frozen {name}>\"
exec(compile({source_repr}, \"<frozen {name}>\", \"exec\"), _mod.__dict__)
import sys
sys.modules[\"{name}\"] = _mod
del _mod
",
            name = module_name,
            source_repr = python_repr(source),
        );
        self.run_code_string(&code)?;
        Ok(())
    }
}

impl Drop for Interpreter {
    fn drop(&mut self) {
        if self.owned && !self.globals.is_null() {
            unsafe {
                ffi::Py_DecRef(self.globals);
                // Note: We don't call Py_Finalize() here because on the IC,
                // the canister process lives for the entire canister lifetime.
                // Finalization would be called on canister uninstall.
            }
        }
    }
}

impl Scope {
    /// Get a global variable from this scope.
    pub fn get_global(&self, name: &str) -> Result<PyObjectRef, PyError> {
        self.globals.get_item_str(name)
    }

    /// Set a global variable in this scope.
    pub fn set_global(&self, name: &str, value: PyObjectRef) -> Result<(), PyError> {
        let key = PyObjectRef::from_str(name)?;
        self.globals.set_item(&key, &value)
    }
}
