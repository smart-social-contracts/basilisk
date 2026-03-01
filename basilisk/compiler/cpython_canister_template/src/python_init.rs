//! CPython initialization for the canister template.
//!
//! Initializes the CPython interpreter, creates the _basilisk_ic module,
//! sets up the basilisk Python shim, and loads the user's Python code.

/// Full CPython initialization: interpreter + IC module + basilisk shim + user code.
pub fn cpython_full_init(python_code: &str) {
    let interpreter = basilisk_cpython::Interpreter::initialize().unwrap_or_else(|e| {
        panic!(
            "Failed to create CPython interpreter: {}",
            e.to_rust_err_string()
        )
    });
    let scope = interpreter.new_scope();

    // Create and register the _basilisk_ic native module
    let _ic_module = crate::ic_api::basilisk_ic_create_module().unwrap_or_else(|e| {
        panic!(
            "Failed to create _basilisk_ic module: {}",
            e.to_rust_err_string()
        )
    });
    interpreter
        .set_global("_basilisk_ic", _ic_module)
        .unwrap_or_else(|e| {
            panic!(
                "Failed to register _basilisk_ic: {}",
                e.to_rust_err_string()
            )
        });

    // Set up the basilisk Python shim (type aliases, decorators, Principal class)
    interpreter
        .run_code_string(BASILISK_PYTHON_SHIM)
        .unwrap_or_else(|e| {
            panic!("Failed to run basilisk shim: {}", e.to_rust_err_string())
        });

    // Cache the Principal class for Rust→Python conversions
    let principal_class = interpreter
        .eval_expression("Principal")
        .unwrap_or_else(|e| {
            panic!(
                "Failed to get Principal class: {}",
                e.to_rust_err_string()
            )
        });
    unsafe {
        crate::PRINCIPAL_CLASS_OPTION = Some(principal_class);
    }

    // Execute the user's Python code
    if !python_code.is_empty() {
        interpreter
            .run_code_string(python_code)
            .unwrap_or_else(|e| {
                panic!("Failed to execute Python code: {}", e.to_rust_err_string())
            });
    }

    unsafe {
        crate::INTERPRETER_OPTION = Some(interpreter);
        crate::SCOPE_OPTION = Some(scope);
        crate::CPYTHON_INIT_DONE = true;
    }

    // Seed random from IC randomness (async, runs after init completes)
    ic_cdk_timers::set_timer(std::time::Duration::from_secs(0), || {
        ic_cdk::spawn(async move {
            let result: ic_cdk::api::call::CallResult<(Vec<u8>,)> =
                ic_cdk::api::management_canister::main::raw_rand().await;
            match result {
                Ok((randomness,)) => {
                    let interpreter = unsafe { crate::INTERPRETER_OPTION.as_mut() }
                        .expect("SystemError: missing python interpreter");
                    let seed_code = format!(
                        "try:\n    import random\n    random.seed({})\nexcept ImportError:\n    pass",
                        randomness
                            .iter()
                            .map(|b| b.to_string())
                            .collect::<Vec<_>>()
                            .join(",")
                    );
                    if let Err(e) = interpreter.run_code_string(&seed_code) {
                        ic_cdk::println!("Warning: failed to seed random: {}", e.to_rust_err_string());
                    }
                }
                Err(err) => panic!("{:?}", err),
            };
        });
    });
}

/// The basilisk Python shim — sets up type aliases, decorators, and Principal class.
/// This is identical for every canister and matches the code currently generated
/// inline in each canister's lib.rs.
const BASILISK_PYTHON_SHIM: &str = r#"
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
        return True
    def __eq__(self, other):
        if isinstance(other, Principal):
            return self._text == other._text
        return NotImplemented
    def __hash__(self):
        return hash(self._text)
    def __repr__(self):
        return f"Principal({self._text!r})"
    def __str__(self):
        return self._text

_mod.Principal = Principal

# === CallResult class ===
class CallResult:
    def __init__(self, ok=None, err=None):
        self.Ok = ok
        self.Err = err
_mod.CallResult = CallResult

# === ic class (wraps _basilisk_ic as static methods) ===
class ic:
    accept_message = staticmethod(_basilisk_ic.accept_message)
    arg_data_raw = staticmethod(_basilisk_ic.arg_data_raw)
    arg_data_raw_size = staticmethod(_basilisk_ic.arg_data_raw_size)
    caller = staticmethod(_basilisk_ic.caller)
    canister_balance = staticmethod(_basilisk_ic.canister_balance)
    canister_balance128 = staticmethod(_basilisk_ic.canister_balance128)
    candid_decode = staticmethod(_basilisk_ic.candid_decode)
    candid_encode = staticmethod(_basilisk_ic.candid_encode)
    data_certificate = staticmethod(_basilisk_ic.data_certificate)
    id = staticmethod(_basilisk_ic.id)
    method_name = staticmethod(_basilisk_ic.method_name)
    msg_cycles_available = staticmethod(_basilisk_ic.msg_cycles_available)
    msg_cycles_available128 = staticmethod(_basilisk_ic.msg_cycles_available128)
    msg_cycles_refunded = staticmethod(_basilisk_ic.msg_cycles_refunded)
    msg_cycles_refunded128 = staticmethod(_basilisk_ic.msg_cycles_refunded128)
    msg_cycles_accept = staticmethod(_basilisk_ic.msg_cycles_accept)
    msg_cycles_accept128 = staticmethod(_basilisk_ic.msg_cycles_accept128)
    performance_counter = staticmethod(_basilisk_ic.performance_counter)
    print = staticmethod(_basilisk_ic.print)
    reject = staticmethod(_basilisk_ic.reject)
    reject_code = staticmethod(_basilisk_ic.reject_code)
    reject_message = staticmethod(_basilisk_ic.reject_message)
    reply_raw = staticmethod(_basilisk_ic.reply_raw)
    set_certified_data = staticmethod(_basilisk_ic.set_certified_data)
    stable_bytes = staticmethod(_basilisk_ic.stable_bytes)
    stable_size = staticmethod(_basilisk_ic.stable_size)
    stable64_size = staticmethod(_basilisk_ic.stable64_size)
    time = staticmethod(_basilisk_ic.time)
    trap = staticmethod(_basilisk_ic.trap)
_mod.ic = ic

# Also expose IC functions directly on the module for backwards compatibility
_mod.accept_message = _basilisk_ic.accept_message
_mod.arg_data_raw = _basilisk_ic.arg_data_raw
_mod.arg_data_raw_size = _basilisk_ic.arg_data_raw_size
_mod.caller = _basilisk_ic.caller
_mod.canister_balance = _basilisk_ic.canister_balance
_mod.canister_balance128 = _basilisk_ic.canister_balance128
_mod.data_certificate = _basilisk_ic.data_certificate
_mod.id = _basilisk_ic.id
_mod.method_name = _basilisk_ic.method_name
_mod.msg_cycles_available = _basilisk_ic.msg_cycles_available
_mod.msg_cycles_available128 = _basilisk_ic.msg_cycles_available128
_mod.msg_cycles_refunded = _basilisk_ic.msg_cycles_refunded
_mod.msg_cycles_refunded128 = _basilisk_ic.msg_cycles_refunded128
_mod.msg_cycles_accept = _basilisk_ic.msg_cycles_accept
_mod.msg_cycles_accept128 = _basilisk_ic.msg_cycles_accept128
_mod.performance_counter = _basilisk_ic.performance_counter
_mod.print = _basilisk_ic.print
_mod.reject = _basilisk_ic.reject
_mod.reject_code = _basilisk_ic.reject_code
_mod.reject_message = _basilisk_ic.reject_message
_mod.reply_raw = _basilisk_ic.reply_raw
_mod.set_certified_data = _basilisk_ic.set_certified_data
_mod.stable_bytes = _basilisk_ic.stable_bytes
_mod.stable_size = _basilisk_ic.stable_size
_mod.stable64_size = _basilisk_ic.stable64_size
_mod.time = _basilisk_ic.time
_mod.trap = _basilisk_ic.trap
_mod.candid_decode = _basilisk_ic.candid_decode
_mod.candid_encode = _basilisk_ic.candid_encode

# === Service base class ===
class Service:
    def __init__(self, canister_id):
        self.canister_id = canister_id
_mod.Service = Service

# === StableBTreeMap ===
class StableBTreeMap:
    def __init__(self, memory_id, max_key_size=0, max_value_size=0):
        self.memory_id = memory_id
    def __class_getitem__(cls, params):
        return cls
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

_sys.modules["basilisk"] = _mod

# Make key classes available at top level for user code
Principal = _mod.Principal
CallResult = _mod.CallResult
StableBTreeMap = _mod.StableBTreeMap
Service = _mod.Service
ic = _mod.ic
"#;
