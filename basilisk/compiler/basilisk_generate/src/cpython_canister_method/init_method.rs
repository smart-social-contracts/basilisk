//! CPython-specific init method code generation.
//!
//! Replaces `canister_method/init_method/rust.rs` when CPython backend is selected.
//! Generates Rust code that initializes CPython via basilisk_cpython instead of RustPython.

use proc_macro2::TokenStream;
use quote::quote;
use rustpython_parser::ast::{Located, StmtKind};

use crate::{source_map::SourceMapped, Error};

pub fn generate(
    init_function_def_option: Option<&SourceMapped<&Located<StmtKind>>>,
    entry_module_name: &str,
) -> Result<TokenStream, Vec<Error>> {
    let call_to_init_py_function = generate_call_to_py_function(
        &generate_call(&init_function_def_option)?,
    );
    let has_init_function = init_function_def_option.is_some();

    if has_init_function {
        // If there's a user @init function, we must initialize CPython during
        // canister_init. This may be slow but is required for correctness.
        let interpreter_init = generate_interpreter_init();
        let ic_object_init = generate_ic_object_init();
        let code_init = generate_code_init(entry_module_name);
        let save_global_interpreter = generate_save_global_interpreter();
        let randomness = generate_randomness();

        Ok(quote! {
            ic_wasi_polyfill::init(&[], &[]);

            unsafe { ENTRY_MODULE_NAME = #entry_module_name; }

            #interpreter_init
            #ic_object_init
            #code_init
            #save_global_interpreter
            #call_to_init_py_function
            #randomness
        })
    } else {
        // No user @init function: do all CPython init during canister_init.
        // canister_init gets Deterministic Time Slicing (DTS) which allows
        // hundreds of billions of instructions — enough for CPython init.
        // Timer callbacks only get ~40B which is insufficient.
        let interpreter_init = generate_interpreter_init();
        let ic_object_init = generate_ic_object_init();
        let code_init = generate_code_init(entry_module_name);
        let save_global_interpreter = generate_save_global_interpreter();
        let randomness = generate_randomness();

        Ok(quote! {
            ic_wasi_polyfill::init(&[], &[]);

            unsafe { ENTRY_MODULE_NAME = #entry_module_name; }

            #interpreter_init

            #ic_object_init

            #code_init

            #save_global_interpreter
            unsafe { CPYTHON_INIT_DONE = true; }

            #randomness
        })
    }
}

pub fn generate_call(
    function_def_option: &Option<&SourceMapped<&Located<StmtKind>>>,
) -> Result<TokenStream, Vec<Error>> {
    match &function_def_option {
        Some(function_def) => function_def.generate_call_to_py_function(),
        None => Ok(quote!()),
    }
}

pub fn generate_interpreter_init() -> TokenStream {
    quote! {
        // Initialize CPython interpreter (replaces RustPython Interpreter::with_init)
        let interpreter = basilisk_cpython::Interpreter::initialize()
            .unwrap_or_else(|e| panic!("Failed to initialize CPython: {}", e.to_rust_err_string()));
        let scope = interpreter.new_scope();
    }
}

pub fn generate_ic_object_init() -> TokenStream {
    quote! {
        // Create and register the _basilisk_ic CPython extension module.
        // This replaces RustPython's Ic pyclass with a C extension module containing
        // PyCFunction entries for each IC API method.
        let _ic_module = basilisk_ic_create_module()
            .unwrap_or_else(|e| panic!("Failed to create _basilisk_ic module: {}", e.to_rust_err_string()));

        // Also make it accessible as a builtin so Python code can use `_basilisk_ic.method()`
        interpreter.set_global("_basilisk_ic", _ic_module)
            .unwrap_or_else(|e| panic!("Failed to register _basilisk_ic: {}", e.to_rust_err_string()));
    }
}

pub fn generate_code_init(entry_module_name: &str) -> TokenStream {
    // For CPython, user modules aren't registered as frozen modules (no py_freeze!).
    // We register a minimal basilisk shim (no heavy stdlib imports like zlib/hashlib)
    // then execute the user's entry module source directly.
    let source_path = format!("../python_source/{}.py", entry_module_name);
    quote! {
        // Register basilisk runtime shim with full ic class, Principal, StableBTreeMap.
        // Only imports sys (builtin) — avoids 'import types' which hangs on IC.
        interpreter.run_code_string(r#"
import sys as _sys
import _basilisk_ic

_mod = type(_sys)("basilisk")
_mod.__file__ = "<frozen basilisk>"

# === Type aliases ===
_mod.int64 = _mod.int32 = _mod.int16 = _mod.int8 = int
_mod.nat = _mod.nat64 = _mod.nat32 = _mod.nat16 = _mod.nat8 = int
_mod.float64 = _mod.float32 = float
_mod.text = str
_mod.blob = bytes
_mod.null = None
_mod.void = None
_mod.Opt = None
_mod.Vec = list
_mod.Record = dict
_mod.Variant = dict
_mod.Tuple = tuple
_mod.reserved = object
_mod.empty = object
_mod.Async = object
_mod.TimerId = int
_mod.Duration = int
_mod.Alias = None
_mod.Manual = None
_mod.CallResult = None
_mod.NotifyResult = None
_mod.GuardResult = dict
_mod.GuardType = None

# === Decorators ===
def _dec(_func=None, **kw):
    def _w(f): return f
    return _w(_func) if _func else _w
_mod.query = _dec
_mod.update = _dec
_mod.init = lambda f: f
_mod.heartbeat = _dec
_mod.pre_upgrade = _dec
_mod.post_upgrade = lambda f: f
_mod.inspect_message = _dec
_mod.canister = lambda c: c
_mod.service_method = lambda f: f
_mod.service_query = lambda f: f
_mod.service_update = lambda f: f

# === Principal class ===
class Principal:
    def __init__(self, text="aaaaa-aa"):
        self._text = text
        self._isPrincipal = True
    @staticmethod
    def management_canister():
        return Principal("aaaaa-aa")
    @staticmethod
    def anonymous():
        return Principal("2vxsx-fae")
    @staticmethod
    def from_str(s):
        return Principal(s)
    @staticmethod
    def from_hex(s):
        p = Principal.__new__(Principal)
        p._text = s
        p._isPrincipal = True
        return p
    def to_str(self):
        return self._text
    @property
    def isPrincipal(self):
        return self._isPrincipal
    def __repr__(self):
        return "Principal(" + self._text + ")"
    def __str__(self):
        return self._text
    def __eq__(self, other):
        if isinstance(other, Principal):
            return self._text == other._text
        return NotImplemented
    def __hash__(self):
        return hash(self._text)
_mod.Principal = Principal

# === ic class ===
class ic:
    @staticmethod
    def accept_message():
        _basilisk_ic.accept_message()
    @staticmethod
    def arg_data_raw():
        return _basilisk_ic.arg_data_raw()
    @staticmethod
    def arg_data_raw_size():
        return _basilisk_ic.arg_data_raw_size()
    @staticmethod
    def caller():
        return _basilisk_ic.caller()
    @staticmethod
    def candid_encode(s):
        return _basilisk_ic.candid_encode(s)
    @staticmethod
    def candid_decode(b):
        return _basilisk_ic.candid_decode(b)
    @staticmethod
    def canister_balance():
        return _basilisk_ic.canister_balance()
    @staticmethod
    def canister_balance128():
        return _basilisk_ic.canister_balance128()
    @staticmethod
    def clear_timer(id):
        return _basilisk_ic.clear_timer(id)
    @staticmethod
    def data_certificate():
        return _basilisk_ic.data_certificate()
    @staticmethod
    def id():
        return _basilisk_ic.id()
    @staticmethod
    def method_name():
        return _basilisk_ic.method_name()
    @staticmethod
    def msg_cycles_accept(max_amount):
        return _basilisk_ic.msg_cycles_accept(max_amount)
    @staticmethod
    def msg_cycles_accept128(max_amount):
        return _basilisk_ic.msg_cycles_accept128(max_amount)
    @staticmethod
    def msg_cycles_available():
        return _basilisk_ic.msg_cycles_available()
    @staticmethod
    def msg_cycles_available128():
        return _basilisk_ic.msg_cycles_available128()
    @staticmethod
    def msg_cycles_refunded():
        return _basilisk_ic.msg_cycles_refunded()
    @staticmethod
    def msg_cycles_refunded128():
        return _basilisk_ic.msg_cycles_refunded128()
    @staticmethod
    def performance_counter(counter_type):
        return _basilisk_ic.performance_counter(counter_type)
    @staticmethod
    def print(*args):
        _basilisk_ic.print(" ".join(str(a) for a in args))
    @staticmethod
    def reject(x):
        _basilisk_ic.reject(x)
    @staticmethod
    def reject_code():
        return _basilisk_ic.reject_code()
    @staticmethod
    def reject_message():
        return _basilisk_ic.reject_message()
    @staticmethod
    def reply(value):
        _basilisk_ic.reply(value)
    @staticmethod
    def reply_raw(x):
        _basilisk_ic.reply_raw(x)
    @staticmethod
    def set_certified_data(data):
        _basilisk_ic.set_certified_data(data)
    @staticmethod
    def set_timer(delay, func):
        return _basilisk_ic.set_timer(delay, func)
    @staticmethod
    def set_timer_interval(interval, func):
        return _basilisk_ic.set_timer_interval(interval, func)
    @staticmethod
    def stable_bytes():
        return _basilisk_ic.stable_bytes()
    @staticmethod
    def stable_grow(new_pages):
        return _basilisk_ic.stable_grow(new_pages)
    @staticmethod
    def stable_read(offset, length):
        return _basilisk_ic.stable_read(offset, length)
    @staticmethod
    def stable_size():
        return _basilisk_ic.stable_size()
    @staticmethod
    def stable_write(offset, buf):
        _basilisk_ic.stable_write(offset, buf)
    @staticmethod
    def stable64_grow(new_pages):
        return _basilisk_ic.stable64_grow(new_pages)
    @staticmethod
    def stable64_read(offset, length):
        return _basilisk_ic.stable64_read(offset, length)
    @staticmethod
    def stable64_size():
        return _basilisk_ic.stable64_size()
    @staticmethod
    def stable64_write(offset, buf):
        _basilisk_ic.stable64_write(offset, buf)
    @staticmethod
    def time():
        return _basilisk_ic.time()
    @staticmethod
    def trap(message):
        _basilisk_ic.trap(message)
_mod.ic = ic

# === Service base class ===
class Service:
    def __init__(self, canister_id):
        self.canister_id = canister_id
_mod.Service = Service

# === StableBTreeMap ===
class StableBTreeMap:
    def __init__(self, memory_id, max_key_size=0, max_value_size=0):
        self.memory_id = memory_id
    def _fn(self, op):
        return getattr(_basilisk_ic, f"stable_b_tree_map_{self.memory_id}_{op}")
    def contains_key(self, key):
        return self._fn("contains_key")(key)
    def get(self, key):
        return self._fn("get")(key)
    def insert(self, key, value):
        return self._fn("insert")(key, value)
    def is_empty(self):
        return self._fn("is_empty")()
    def items(self):
        return self._fn("items")()
    def keys(self):
        return self._fn("keys")()
    def len(self):
        return self._fn("len")()
    def remove(self, key):
        return self._fn("remove")(key)
    def values(self):
        return self._fn("values")()
_mod.StableBTreeMap = StableBTreeMap

# === match function ===
def _match(variant, matcher):
    if isinstance(variant, dict):
        for key, value in matcher.items():
            if key in variant:
                return value(variant[key])
            if key == "_":
                return value(None)
    else:
        err_value = getattr(variant, "Err", None)
        if err_value is not None:
            return matcher["Err"](err_value)
        return matcher["Ok"](getattr(variant, "Ok"))
    raise Exception("No matching case found")
_mod.match = _match

# Register module
_sys.modules["basilisk"] = _mod
del _mod, _dec, _match
"#)
            .unwrap_or_else(|e| panic!("Failed to register basilisk shim: {}", e.to_rust_err_string()));

        // Execute user's entry module source directly
        const _ENTRY_MODULE_SOURCE: &str = include_str!(#source_path);
        interpreter.run_code_string(_ENTRY_MODULE_SOURCE)
            .unwrap_or_else(|e| panic!("Failed to execute {}: {}", #entry_module_name, e.to_rust_err_string()));
    }
}

pub fn generate_save_global_interpreter() -> TokenStream {
    quote! {
        unsafe {
            INTERPRETER_OPTION = Some(interpreter);
            SCOPE_OPTION = Some(scope);
        };
    }
}

pub fn generate_call_to_py_function(
    call_to_py_function: &TokenStream,
) -> TokenStream {
    quote! {
        {
            let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                .unwrap_or_else(|| panic!("SystemError: missing python interpreter"));

            #call_to_py_function
        }
    }
}

pub fn generate_randomness() -> TokenStream {
    quote! {
        ic_cdk_timers::set_timer(std::time::Duration::from_secs(0), || {
            ic_cdk::spawn(async move {
                let result: ic_cdk::api::call::CallResult<(Vec<u8>,)> = ic_cdk::api::management_canister::main::raw_rand().await;

                match result {
                    Ok((randomness,)) => {
                        let interpreter = unsafe { INTERPRETER_OPTION.as_mut() }
                            .ok_or_else(|| "SystemError: missing python interpreter".to_string()).unwrap();

                        // Seed Python's random module with IC randomness
                        let seed_code = format!(
                            "import random; random.seed({})",
                            randomness.iter().map(|b| b.to_string()).collect::<Vec<_>>().join(",")
                        );
                        interpreter.run_code_string(&seed_code)
                            .unwrap_or_else(|e| panic!("Failed to seed random: {}", e.to_rust_err_string()));
                    },
                    Err(err) => panic!("{:?}", err)
                };
            });
        });
    }
}
