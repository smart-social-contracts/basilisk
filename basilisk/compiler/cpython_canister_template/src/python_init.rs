//! CPython initialization for the canister template.
//!
//! Initializes the CPython interpreter, creates the _basilisk_ic module,
//! sets up the basilisk Python shim, and loads the user's Python code.

/// Frozen stdlib preamble — registers pure-Python implementations of stdlib
/// modules (json, etc.) that aren't available on WASI without a filesystem.
/// Must run BEFORE the basilisk shim which depends on `import json`.
const FROZEN_STDLIB_PREAMBLE: &str = include_str!("../../../frozen_stdlib_preamble.py");

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

    // Run frozen stdlib preamble first — makes json and other stdlib modules
    // available before the shim (which uses `import json` for StableBTreeMap).
    interpreter
        .run_code_string(FROZEN_STDLIB_PREAMBLE)
        .unwrap_or_else(|e| {
            panic!("Failed to run frozen stdlib preamble: {}", e.to_rust_err_string())
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
                        "import random; random.seed(int.from_bytes(bytes([{}]), 'big'))",
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

# === Subscriptable placeholder for generic type aliases ===
class _Sub:
    """Subscriptable placeholder that ignores type parameters."""
    def __class_getitem__(cls, item):
        return cls

# === Type aliases ===
_mod.int64 = _mod.int32 = _mod.int16 = _mod.int8 = int
_mod.nat = _mod.nat64 = _mod.nat32 = _mod.nat16 = _mod.nat8 = int
_mod.float64 = _mod.float32 = float
_mod.text = str
_mod.blob = bytes
_mod.null = None
_mod.void = None
_mod.Opt = _Sub
_mod.Vec = list
_mod.Record = dict
_mod.Variant = dict
_mod.Tuple = tuple
_mod.reserved = _Sub
_mod.empty = _Sub
_mod.Async = _Sub
_mod.TimerId = int
_mod.Duration = int
_mod.Alias = _Sub
_mod.Manual = _Sub
_mod.CallResult = _Sub
_mod.NotifyResult = _Sub
_mod.GuardResult = dict
_mod.GuardType = _Sub
_mod.Oneway = _Sub
_mod.RejectionCode = int
_mod.FuncTuple = tuple
_mod.StableGrowResult = int
_mod.Stable64GrowResult = int

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
_mod.composite_query = _dec
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

# === StableBTreeMap ===
import json as _json

_stable_btree_maps = {}  # memory_id -> StableBTreeMap instance

class _StableBTreeMapMeta(type):
    def __getitem__(cls, params):
        # StableBTreeMap[K, V] — returns a callable class factory
        if isinstance(params, tuple) and len(params) == 2:
            key_type, val_type = params
        else:
            key_type, val_type = params, None
        def factory(memory_id=0, max_key_size=100, max_value_size=100):
            m = StableBTreeMap.__new__(StableBTreeMap)
            m._data = {}
            m._memory_id = memory_id
            m._max_key_size = max_key_size
            m._max_value_size = max_value_size
            _stable_btree_maps[memory_id] = m
            return m
        return factory

class StableBTreeMap(metaclass=_StableBTreeMapMeta):
    def __init__(self, memory_id=0, max_key_size=100, max_value_size=100):
        self._data = {}
        self._memory_id = memory_id
        self._max_key_size = max_key_size
        self._max_value_size = max_value_size
        _stable_btree_maps[memory_id] = self
    def get(self, key):
        k = self._normalize_key(key)
        return self._data.get(k, None)
    def insert(self, key, value):
        k = self._normalize_key(key)
        prev = self._data.get(k, None)
        self._data[k] = value
        return prev
    def remove(self, key):
        k = self._normalize_key(key)
        return self._data.pop(k, None)
    def contains_key(self, key):
        k = self._normalize_key(key)
        return k in self._data
    def is_empty(self):
        return len(self._data) == 0
    def keys(self):
        return [self._denormalize_key(k) for k in self._data.keys()]
    def values(self):
        return list(self._data.values())
    def items(self):
        return [(self._denormalize_key(k), v) for k, v in self._data.items()]
    def len(self):
        return len(self._data)
    def _normalize_key(self, key):
        # Make keys hashable for dict storage
        if isinstance(key, dict):
            return _json.dumps(key, sort_keys=True)
        if isinstance(key, list):
            return tuple(key)
        return key
    def _denormalize_key(self, key):
        if isinstance(key, str) and key.startswith('{'):
            try:
                return _json.loads(key)
            except Exception:
                pass
        return key

_mod.StableBTreeMap = StableBTreeMap

# Auto-persistence for StableBTreeMap across upgrades
_STABLE_MAP_MAGIC = b"BSLK_MAP"  # 8-byte magic

def _basilisk_save_stable_maps():
    """Serialize all StableBTreeMap instances to stable memory."""
    if not _stable_btree_maps:
        return
    # Build serializable data: { memory_id: { key: value, ... }, ... }
    save_data = {}
    for mem_id, m in _stable_btree_maps.items():
        # Convert internal dict to list of [key, value] pairs for JSON
        pairs = []
        for k, v in m._data.items():
            pairs.append([_to_json_safe(k), _to_json_safe(v)])
        save_data[str(mem_id)] = {
            "pairs": pairs,
            "max_key_size": m._max_key_size,
            "max_value_size": m._max_value_size,
        }
    payload = _json.dumps(save_data).encode("utf-8")
    total_size = 16 + len(payload)  # 8 magic + 8 length + payload
    # Grow stable memory if needed (64KB pages)
    pages_needed = (total_size + 65535) // 65536
    current_pages = _basilisk_ic.stable_size()
    if pages_needed > current_pages:
        _basilisk_ic.stable_grow(pages_needed - current_pages)
    # Write header + payload
    import struct as _struct
    header = _STABLE_MAP_MAGIC + _struct.pack("<Q", len(payload))
    _basilisk_ic.stable_write(0, header + payload)

def _basilisk_load_stable_maps():
    """Restore StableBTreeMap instances from stable memory."""
    current_pages = _basilisk_ic.stable_size()
    if current_pages == 0:
        return
    # Read header
    header = _basilisk_ic.stable_read(0, 16)
    if header[:8] != _STABLE_MAP_MAGIC:
        return  # No saved maps
    import struct as _struct
    payload_len = _struct.unpack("<Q", header[8:16])[0]
    if payload_len == 0:
        return
    payload = _basilisk_ic.stable_read(16, payload_len)
    save_data = _json.loads(payload.decode("utf-8"))
    for mem_id_str, info in save_data.items():
        mem_id = int(mem_id_str)
        if mem_id in _stable_btree_maps:
            m = _stable_btree_maps[mem_id]
        else:
            m = StableBTreeMap.__new__(StableBTreeMap)
            m._data = {}
            m._memory_id = mem_id
            m._max_key_size = info.get("max_key_size", 100)
            m._max_value_size = info.get("max_value_size", 100)
            _stable_btree_maps[mem_id] = m
        for k, v in info["pairs"]:
            m._data[_from_json_safe(k)] = _from_json_safe(v)

def _to_json_safe(obj):
    """Convert Python object to JSON-safe representation."""
    if isinstance(obj, Principal):
        return {"__principal__": obj._text}
    if isinstance(obj, tuple):
        return {"__tuple__": [_to_json_safe(x) for x in obj]}
    if isinstance(obj, dict):
        return {"__dict__": [[_to_json_safe(k), _to_json_safe(v)] for k, v in obj.items()]}
    if isinstance(obj, list):
        return [_to_json_safe(x) for x in obj]
    if isinstance(obj, bytes):
        return {"__bytes__": list(obj)}
    return obj

def _from_json_safe(obj):
    """Restore Python object from JSON-safe representation."""
    if isinstance(obj, dict):
        if "__principal__" in obj:
            return Principal(obj["__principal__"])
        if "__tuple__" in obj:
            return tuple(_from_json_safe(x) for x in obj["__tuple__"])
        if "__dict__" in obj:
            return {_from_json_safe(k): _from_json_safe(v) for k, v in obj["__dict__"]}
        if "__bytes__" in obj:
            return bytes(obj["__bytes__"])
        return {_from_json_safe(k): _from_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_json_safe(x) for x in obj]
    return obj

# === Func/Service/Query/Update type stubs ===
class _FuncType:
    def __init__(self, sig):
        self.sig = sig
    def __class_getitem__(cls, params):
        return cls(params)

class _QueryType:
    def __class_getitem__(cls, params):
        return ("query", params)

class _UpdateType:
    def __class_getitem__(cls, params):
        return ("update", params)

def Func(sig):
    return _FuncType(sig)

class _ServiceCall:
    """Represents a pending cross-canister call to be yielded from a generator."""
    def __init__(self, canister_principal, method_name, args=None, payment=0):
        self.canister_principal = canister_principal
        self.method_name = method_name
        self.args = args or ()
        self.payment = payment
    def with_cycles(self, cycles):
        self.payment = cycles
        return self
    def with_cycles128(self, cycles):
        self.payment = cycles
        return self
    def notify(self):
        return {"Ok": None}

class _ServiceMethodProxy:
    """Proxy for a service method that creates _ServiceCall descriptors."""
    def __init__(self, principal, method_name):
        self._principal = principal
        self._method_name = method_name
    def __call__(self, *args, **kwargs):
        return _ServiceCall(self._principal, self._method_name, args)

class _ServiceMethodDescriptor:
    """Descriptor that returns a _ServiceMethodProxy when accessed on a Service instance."""
    def __init__(self, func):
        self.name = func.__name__
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return _ServiceMethodProxy(obj._principal, self.name)

def service_query(func):
    return _ServiceMethodDescriptor(func)

def service_update(func):
    return _ServiceMethodDescriptor(func)

class Service:
    def __init__(self, principal=None):
        self._principal = principal
    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return _ServiceMethodProxy(self._principal, name)

_mod._ServiceCall = _ServiceCall
_mod.Func = Func
_mod.Service = Service
_mod.Query = _QueryType
_mod.Update = _UpdateType
_mod.service_query = service_query
_mod.service_update = service_update

# NotifyResult is a Variant-like type alias
class NotifyResult:
    pass
_mod.NotifyResult = NotifyResult

# === match helper ===
def match(value, cases):
    if isinstance(value, dict):
        for k, v in value.items():
            if k in cases and v is not None:
                return cases[k](v)
            elif k in cases:
                return cases[k](None)
    if isinstance(value, CallResult):
        if value.Err is not None and "Err" in cases:
            return cases["Err"](value.Err)
        if value.Ok is not None and "Ok" in cases:
            return cases["Ok"](value.Ok)
    return None

_mod.match = match

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
    reply = staticmethod(_basilisk_ic.reply)
    stable_grow = staticmethod(_basilisk_ic.stable_grow)
    stable_read = staticmethod(_basilisk_ic.stable_read)
    stable_write = staticmethod(_basilisk_ic.stable_write)
    stable64_grow = staticmethod(_basilisk_ic.stable64_grow)
    stable64_read = staticmethod(_basilisk_ic.stable64_read)
    stable64_write = staticmethod(_basilisk_ic.stable64_write)
    set_timer = staticmethod(_basilisk_ic.set_timer)
    set_timer_interval = staticmethod(_basilisk_ic.set_timer_interval)
    clear_timer = staticmethod(_basilisk_ic.clear_timer)
    call_raw = staticmethod(_basilisk_ic.call_raw)
    call_raw128 = staticmethod(_basilisk_ic.call_raw128)
# Override call_raw/call_raw128 to return _ServiceCall objects (for generator yield)
@staticmethod
def _ic_call_raw(canister_id, method, args_raw, cycles=0):
    call = _ServiceCall(canister_id, method)
    call._raw_args = bytes(args_raw) if not isinstance(args_raw, bytes) else args_raw
    call.payment = int(cycles)
    return call

@staticmethod
def _ic_call_raw128(canister_id, method, args_raw, cycles=0):
    call = _ServiceCall(canister_id, method)
    call._raw_args = bytes(args_raw) if not isinstance(args_raw, bytes) else args_raw
    call.payment = int(cycles)
    return call

ic.call_raw = _ic_call_raw
ic.call_raw128 = _ic_call_raw128

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

_sys.modules["basilisk"] = _mod

# Make key classes available at top level for user code
Principal = _mod.Principal
CallResult = _mod.CallResult
StableBTreeMap = _mod.StableBTreeMap
Func = _mod.Func
Service = _mod.Service
Query = _mod.Query
Update = _mod.Update
service_query = _mod.service_query
service_update = _mod.service_update
NotifyResult = _mod.NotifyResult
match = _mod.match
ic = _mod.ic
"#;
