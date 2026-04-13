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

    // Now that Service is defined, fix up management_canister / Ledger stubs
    // that were registered by the frozen preamble before Service existed.
    interpreter
        .run_code_string(
            "import sys as _sys\n\
             _bmod = _sys.modules.get('basilisk')\n\
             if _bmod and hasattr(_bmod, 'Service'):\n\
             \x20\x20\x20\x20_S = _bmod.Service\n\
             \x20\x20\x20\x20_P = getattr(_bmod, 'Principal', None)\n\
             \x20\x20\x20\x20_mgmt = _sys.modules.get('basilisk.canisters.management')\n\
             \x20\x20\x20\x20if _mgmt and _P:\n\
             \x20\x20\x20\x20\x20\x20\x20\x20_mc = _S(_P.from_str('aaaaa-aa'))\n\
             \x20\x20\x20\x20\x20\x20\x20\x20_mc._return_types = {\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'create_canister': 'record { canister_id : principal }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'canister_status': 'record { status : variant { running : null; stopping : null; stopped : null }; settings : record { controllers : vec principal; compute_allocation : nat; memory_allocation : nat; freezing_threshold : nat }; module_hash : opt blob; memory_size : nat; cycles : nat }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'raw_rand': 'blob',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'http_request': 'record { status : nat; headers : vec record { name : text; value : text }; body : blob }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'ecdsa_public_key': 'record { public_key : blob; chain_code : blob }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'sign_with_ecdsa': 'record { signature : blob }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'bitcoin_get_balance': 'nat64',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'bitcoin_get_utxos': 'record { next_page : opt blob; tip_block_hash : blob; tip_height : nat32; utxos : vec record { height : nat32; outpoint : record { txid : blob; vout : nat32 }; value : nat64 } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'bitcoin_get_current_fee_percentiles': 'vec nat64',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20}\n\
             \x20\x20\x20\x20\x20\x20\x20\x20_mc._arg_types = {\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'create_canister': 'record { settings : opt record { controllers : opt vec principal; compute_allocation : opt nat; memory_allocation : opt nat; freezing_threshold : opt nat } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'update_settings': 'record { canister_id : principal; settings : record { controllers : opt vec principal; compute_allocation : opt nat; memory_allocation : opt nat; freezing_threshold : opt nat } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'install_code': 'record { mode : variant { install : null; reinstall : null; upgrade : null }; canister_id : principal; wasm_module : blob; arg : blob }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'uninstall_code': 'record { canister_id : principal }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'start_canister': 'record { canister_id : principal }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'stop_canister': 'record { canister_id : principal }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'canister_status': 'record { canister_id : principal }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'delete_canister': 'record { canister_id : principal }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'deposit_cycles': 'record { canister_id : principal }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'provisional_create_canister_with_cycles': 'record { amount : opt nat; settings : opt record { controllers : opt vec principal; compute_allocation : opt nat; memory_allocation : opt nat; freezing_threshold : opt nat } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'provisional_top_up_canister': 'record { canister_id : principal; amount : nat }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'bitcoin_get_balance': 'record { address : text; min_confirmations : opt nat32; network : variant { Mainnet : null; Testnet : null; Regtest : null } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'bitcoin_get_utxos': 'record { address : text; filter : opt variant { min_confirmations : nat32; page : blob }; network : variant { Mainnet : null; Testnet : null; Regtest : null } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'bitcoin_get_current_fee_percentiles': 'record { network : variant { Mainnet : null; Testnet : null; Regtest : null } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'bitcoin_send_transaction': 'record { transaction : blob; network : variant { Mainnet : null; Testnet : null; Regtest : null } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'http_request': 'record { url : text; max_response_bytes : opt nat64; method : variant { get : null; head : null; post : null }; headers : vec record { name : text; value : text }; body : opt blob; transform : opt record { function : func (record { response : record { status : nat; headers : vec record { name : text; value : text }; body : blob }; context : blob }) -> (record { status : nat; headers : vec record { name : text; value : text }; body : blob }) query; context : blob } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'ecdsa_public_key': 'record { canister_id : opt principal; derivation_path : vec blob; key_id : record { curve : variant { secp256k1 : null }; name : text } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'sign_with_ecdsa': 'record { message_hash : blob; derivation_path : vec blob; key_id : record { curve : variant { secp256k1 : null }; name : text } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20}\n\
             \x20\x20\x20\x20\x20\x20\x20\x20_mgmt.management_canister = _mc\n\
             \x20\x20\x20\x20\x20\x20\x20\x20_mgmt.ManagementCanister = _S\n\
             \x20\x20\x20\x20_ledger = _sys.modules.get('basilisk.canisters.ledger')\n\
             \x20\x20\x20\x20if _ledger:\n\
             \x20\x20\x20\x20\x20\x20\x20\x20class _LedgerSvc(_S):\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20_arg_types = {\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'transfer': 'record { memo : nat64; amount : record { e8s : nat64 }; fee : record { e8s : nat64 }; from_subaccount : opt blob; to : blob; created_at_time : opt record { timestamp_nanos : nat64 } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'account_balance': 'record { account : blob }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'query_blocks': 'record { start : nat64; length : nat64 }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20}\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20_return_types = {\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'account_balance': 'record { e8s : nat64 }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'transfer': 'variant { Ok : nat64; Err : variant { BadFee : record { expected_fee : record { e8s : nat64 } }; InsufficientFunds : record { balance : record { e8s : nat64 } }; TxTooOld : record { allowed_window_nanos : nat64 }; TxCreatedInFuture : null; TxDuplicate : record { duplicate_of : nat64 } } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20'transfer_fee': 'record { transfer_fee : record { e8s : nat64 } }',\n\
             \x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20}\n\
             \x20\x20\x20\x20\x20\x20\x20\x20_ledger.Ledger = _LedgerSvc\n",
        )
        .unwrap_or_else(|e| {
            panic!("Failed to fix up service stubs: {}", e.to_rust_err_string())
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
class _Opt(_Sub):
    """Opt wrapper: Opt[T] for type annotations, Opt(value) for runtime opt encoding."""
    __slots__ = ('value',)
    def __init__(self, value=None):
        self.value = value
_mod.Opt = _Opt
_mod.Vec = list
class _Record(dict):
    def __class_getitem__(cls, params): return cls
    def __init_subclass__(cls, **kw): pass
class _Variant(dict):
    def __class_getitem__(cls, params): return cls
    def __init_subclass__(cls, **kw): pass
_mod.Record = _Record
_mod.Variant = _Variant
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
    _CRC_TABLE = None
    _B32 = 'abcdefghijklmnopqrstuvwxyz234567'
    _B32_REV = None

    @staticmethod
    def _crc32(data):
        if Principal._CRC_TABLE is None:
            tbl = []
            for i in range(256):
                c = i
                for _ in range(8):
                    c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
                tbl.append(c)
            Principal._CRC_TABLE = tbl
        crc = 0xFFFFFFFF
        for b in data:
            crc = Principal._CRC_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
        return crc ^ 0xFFFFFFFF

    @staticmethod
    def _b32encode(data):
        a = Principal._B32
        out = []
        buf = 0
        bits = 0
        for byte in data:
            buf = (buf << 8) | byte
            bits += 8
            while bits >= 5:
                bits -= 5
                out.append(a[(buf >> bits) & 0x1F])
        if bits > 0:
            out.append(a[(buf << (5 - bits)) & 0x1F])
        return ''.join(out)

    @staticmethod
    def _b32decode(s):
        if Principal._B32_REV is None:
            Principal._B32_REV = {c: i for i, c in enumerate(Principal._B32)}
        rev = Principal._B32_REV
        buf = 0
        bits = 0
        out = []
        for c in s:
            if c == '=':
                break
            buf = (buf << 5) | rev[c]
            bits += 5
            while bits >= 8:
                bits -= 8
                out.append((buf >> bits) & 0xFF)
        return bytes(out)

    def __init__(self, arg=None):
        self._isPrincipal = True
        if arg is None:
            self._bytes = b""
            self._text = None
        elif isinstance(arg, bytes):
            self._bytes = arg
            self._text = None
        elif isinstance(arg, str):
            self._text = arg
            self._bytes = None
        else:
            self._text = str(arg)
            self._bytes = None

    @staticmethod
    def management_canister():
        return Principal(b"")

    @staticmethod
    def anonymous():
        return Principal(b"\x04")

    @staticmethod
    def from_str(s):
        p = Principal.__new__(Principal)
        p._isPrincipal = True
        p._text = s
        p._bytes = None
        return p

    @staticmethod
    def from_hex(s):
        return Principal(bytes.fromhex(s.lower()))

    @staticmethod
    def self_authenticating(pubkey):
        if isinstance(pubkey, str):
            pubkey = bytes.fromhex(pubkey)
        try:
            import hashlib
            h = hashlib.sha224(pubkey).digest()
        except ImportError:
            import _basilisk_hashlib_sha224
            h = _basilisk_hashlib_sha224.digest(pubkey)
        return Principal(h + b"\x02")

    def _ensure_text(self):
        if self._text is None:
            raw = self._bytes if self._bytes is not None else b""
            cksum = Principal._crc32(raw)
            blob = cksum.to_bytes(4, byteorder='big') + raw
            s = Principal._b32encode(blob)
            parts = []
            while len(s) > 5:
                parts.append(s[:5])
                s = s[5:]
            parts.append(s)
            self._text = '-'.join(parts)

    def _ensure_bytes(self):
        if self._bytes is None:
            s = self._text.replace('-', '')
            raw = Principal._b32decode(s)
            self._bytes = raw[4:]  # skip 4-byte CRC

    def to_str(self):
        self._ensure_text()
        return self._text

    @property
    def isPrincipal(self):
        return True

    @property
    def bytes(self):
        self._ensure_bytes()
        return self._bytes

    @property
    def hex(self):
        self._ensure_bytes()
        return self._bytes.hex().upper()

    def to_account_id(self, subaccount=None):
        self._ensure_bytes()
        if subaccount is None:
            subaccount = b'\x00' * 32
        domain = b'\x0aaccount-id'
        try:
            import hashlib
            h = hashlib.sha224(domain + self._bytes + subaccount).digest()
        except ImportError:
            import _basilisk_hashlib_sha224
            h = _basilisk_hashlib_sha224.digest(domain + self._bytes + subaccount)
        crc = Principal._crc32(h)
        return _AccountIdentifier(crc.to_bytes(4, byteorder='big') + h)

    def __eq__(self, other):
        if isinstance(other, Principal):
            return self.to_str() == other.to_str()
        return NotImplemented

    def __hash__(self):
        return hash(self.to_str())

    def __repr__(self):
        return f"Principal({self.to_str()!r})"

    def __str__(self):
        return self.to_str()

class _AccountIdentifier:
    def __init__(self, raw_bytes):
        self._bytes = raw_bytes
    def to_str(self):
        return '0x' + self._bytes.hex()
    def __repr__(self):
        return f'AccountIdentifier({self.to_str()!r})'

_mod.Principal = Principal

# === CallResult class ===
class CallResult(dict):
    """CallResult wraps cross-canister call results.
    Supports both dict-style (result['Ok']) and attribute-style (result.Ok) access.
    Async yield returns a plain dict; this subclass makes both patterns work."""
    def __init__(self, ok=None, err=None, **kwargs):
        super().__init__(**kwargs)
        if ok is not None:
            self['Ok'] = ok
        if err is not None:
            self['Err'] = err
    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError:
            return None
    def __setattr__(self, name, value):
        self[name] = value
    @staticmethod
    def from_dict(d):
        cr = CallResult()
        cr.update(d)
        return cr
_mod.CallResult = CallResult

# === Stable structures (Rust-backed via _basilisk_ic) ===
# All data structures persist directly in stable memory via ic-stable-structures.
# No pre_upgrade/post_upgrade serialization needed.

import _struct

# --- Explicit stable type hints ---
# These override the simple int/float aliases at module level so that
# StableBTreeMap[nat8, int32](...) can distinguish encoding widths.

class _StableIntHint(int):
    """Marker base for explicit stable integer encoding types."""
    _stable_tag = None
    _stable_fmt = None

class _StableFloatHint(float):
    """Marker base for explicit stable float encoding types."""
    _stable_tag = None
    _stable_fmt = None

class nat8(_StableIntHint):
    _stable_tag = 0x10
    _stable_fmt = '>B'

class nat16(_StableIntHint):
    _stable_tag = 0x11
    _stable_fmt = '>H'

class nat32(_StableIntHint):
    _stable_tag = 0x12
    _stable_fmt = '>I'

class nat64(_StableIntHint):
    _stable_tag = 0x13
    _stable_fmt = '>Q'

class int8(_StableIntHint):
    _stable_tag = 0x14
    _stable_fmt = '>b'

class int16(_StableIntHint):
    _stable_tag = 0x15
    _stable_fmt = '>h'

class int32(_StableIntHint):
    _stable_tag = 0x16
    _stable_fmt = '>i'

class float32(_StableFloatHint):
    _stable_tag = 0x17
    _stable_fmt = '>f'

_mod.nat8 = nat8
_mod.nat16 = nat16
_mod.nat32 = nat32
_mod.nat64 = nat64
_mod.int8 = int8
_mod.int16 = int16
_mod.int32 = int32
_mod.float32 = float32

# --- Tagged binary encoder/decoder ---
# Format: [1-byte type tag] [payload]
# All integers are big-endian for correct byte-level ordering.

def _encode(value, type_hint=None):
    """Encode a Python value to tagged binary bytes."""
    if type_hint is not None and hasattr(type_hint, '_stable_tag') and type_hint._stable_tag is not None:
        return bytes([type_hint._stable_tag]) + _struct.pack(type_hint._stable_fmt, value)
    if value is None:
        return b'\x00'
    if isinstance(value, bool):
        return b'\x01' + (b'\x01' if value else b'\x00')
    if isinstance(value, int):
        return b'\x02' + _struct.pack('>q', value)
    if isinstance(value, float):
        return b'\x03' + _struct.pack('>d', value)
    if isinstance(value, str):
        raw = value.encode('utf-8')
        return b'\x04' + _struct.pack('>I', len(raw)) + raw
    if isinstance(value, (bytes, bytearray)):
        return b'\x05' + _struct.pack('>I', len(value)) + bytes(value)
    if isinstance(value, Principal):
        raw = value.to_str().encode('utf-8')
        return b'\x06' + _struct.pack('>I', len(raw)) + raw
    if isinstance(value, list):
        parts = b''.join(_encode(x) for x in value)
        return b'\x07' + _struct.pack('>I', len(value)) + parts
    if isinstance(value, dict):
        parts = b''.join(_encode(k) + _encode(v) for k, v in value.items())
        return b'\x08' + _struct.pack('>I', len(value)) + parts
    if isinstance(value, tuple):
        parts = b''.join(_encode(x) for x in value)
        return b'\x09' + _struct.pack('>I', len(value)) + parts
    raise ValueError(f"Cannot encode {type(value).__name__} for stable storage")

def _decode(data, offset=0):
    """Decode a tagged binary value, returning (value, new_offset)."""
    tag = data[offset]
    offset += 1
    if tag == 0x00:
        return None, offset
    if tag == 0x01:
        return data[offset] != 0, offset + 1
    if tag == 0x02:
        return _struct.unpack_from('>q', data, offset)[0], offset + 8
    if tag == 0x03:
        return _struct.unpack_from('>d', data, offset)[0], offset + 8
    if tag == 0x04:
        length = _struct.unpack_from('>I', data, offset)[0]
        offset += 4
        return data[offset:offset + length].decode('utf-8'), offset + length
    if tag == 0x05:
        length = _struct.unpack_from('>I', data, offset)[0]
        offset += 4
        return bytes(data[offset:offset + length]), offset + length
    if tag == 0x06:
        length = _struct.unpack_from('>I', data, offset)[0]
        offset += 4
        return Principal(data[offset:offset + length].decode('utf-8')), offset + length
    if tag == 0x07:
        count = _struct.unpack_from('>I', data, offset)[0]
        offset += 4
        items = []
        for _ in range(count):
            item, offset = _decode(data, offset)
            items.append(item)
        return items, offset
    if tag == 0x08:
        count = _struct.unpack_from('>I', data, offset)[0]
        offset += 4
        d = {}
        for _ in range(count):
            k, offset = _decode(data, offset)
            v, offset = _decode(data, offset)
            d[k] = v
        return d, offset
    if tag == 0x09:
        count = _struct.unpack_from('>I', data, offset)[0]
        offset += 4
        items = []
        for _ in range(count):
            item, offset = _decode(data, offset)
            items.append(item)
        return tuple(items), offset
    if tag == 0x10:
        return _struct.unpack_from('>B', data, offset)[0], offset + 1
    if tag == 0x11:
        return _struct.unpack_from('>H', data, offset)[0], offset + 2
    if tag == 0x12:
        return _struct.unpack_from('>I', data, offset)[0], offset + 4
    if tag == 0x13:
        return _struct.unpack_from('>Q', data, offset)[0], offset + 8
    if tag == 0x14:
        return _struct.unpack_from('>b', data, offset)[0], offset + 1
    if tag == 0x15:
        return _struct.unpack_from('>h', data, offset)[0], offset + 2
    if tag == 0x16:
        return _struct.unpack_from('>i', data, offset)[0], offset + 4
    if tag == 0x17:
        return _struct.unpack_from('>f', data, offset)[0], offset + 4
    raise ValueError(f"Unknown stable encoding tag 0x{tag:02x}")

def _decode_val(raw):
    """Decode a complete tagged binary blob, returning the Python value."""
    if raw is None:
        return None
    val, _ = _decode(raw)
    return val

# --- StableBTreeMap ---

def _type_hint_for(t):
    """Return t if it carries stable encoding metadata, else None."""
    if t is not None and hasattr(t, '_stable_tag') and t._stable_tag is not None:
        return t
    return None

class _StableBTreeMapMeta(type):
    def __getitem__(cls, params):
        if isinstance(params, tuple) and len(params) == 2:
            key_type, val_type = params
        else:
            key_type, val_type = params, None
        def factory(memory_id=0, max_key_size=100, max_value_size=100):
            return StableBTreeMap(memory_id=memory_id, max_key_size=max_key_size, max_value_size=max_value_size, _key_type=key_type, _val_type=val_type)
        return factory

class StableBTreeMap(metaclass=_StableBTreeMapMeta):
    def __init__(self, memory_id=0, max_key_size=100, max_value_size=100, _key_type=None, _val_type=None):
        self._memory_id = memory_id
        self._kt = _type_hint_for(_key_type)
        self._vt = _type_hint_for(_val_type)
        _basilisk_ic.smap_init(memory_id)
    def get(self, key):
        return _decode_val(_basilisk_ic.smap_get(self._memory_id, _encode(key, self._kt)))
    def insert(self, key, value):
        prev = _basilisk_ic.smap_insert(self._memory_id, _encode(key, self._kt), _encode(value, self._vt))
        return _decode_val(prev)
    def remove(self, key):
        prev = _basilisk_ic.smap_remove(self._memory_id, _encode(key, self._kt))
        return _decode_val(prev)
    def contains_key(self, key):
        return _basilisk_ic.smap_contains_key(self._memory_id, _encode(key, self._kt))
    def is_empty(self):
        return _basilisk_ic.smap_len(self._memory_id) == 0
    def keys(self):
        return [_decode_val(k) for k in _basilisk_ic.smap_keys(self._memory_id)]
    def values(self):
        return [_decode_val(v) for _, v in _basilisk_ic.smap_items(self._memory_id)]
    def items(self):
        return [(_decode_val(k), _decode_val(v)) for k, v in _basilisk_ic.smap_items(self._memory_id)]
    def len(self):
        return _basilisk_ic.smap_len(self._memory_id)

_mod.StableBTreeMap = StableBTreeMap

# --- StableBTreeSet ---

class StableBTreeSet:
    def __init__(self, memory_id=0, _key_type=None):
        self._memory_id = memory_id
        self._kt = _type_hint_for(_key_type)
        _basilisk_ic.sset_init(memory_id)
    def insert(self, key):
        return _basilisk_ic.sset_insert(self._memory_id, _encode(key, self._kt))
    def remove(self, key):
        return _basilisk_ic.sset_remove(self._memory_id, _encode(key, self._kt))
    def contains(self, key):
        return _basilisk_ic.sset_contains(self._memory_id, _encode(key, self._kt))
    def is_empty(self):
        return _basilisk_ic.sset_len(self._memory_id) == 0
    def items(self):
        return [_decode_val(k) for k in _basilisk_ic.sset_items(self._memory_id)]
    def len(self):
        return _basilisk_ic.sset_len(self._memory_id)

_mod.StableBTreeSet = StableBTreeSet

# --- StableVec ---

class StableVec:
    def __init__(self, memory_id=0, _val_type=None):
        self._memory_id = memory_id
        self._vt = _type_hint_for(_val_type)
        _basilisk_ic.svec_init(memory_id)
    def get(self, index):
        return _decode_val(_basilisk_ic.svec_get(self._memory_id, index))
    def push(self, value):
        _basilisk_ic.svec_push(self._memory_id, _encode(value, self._vt))
    def pop(self):
        return _decode_val(_basilisk_ic.svec_pop(self._memory_id))
    def set(self, index, value):
        _basilisk_ic.svec_set(self._memory_id, index, _encode(value, self._vt))
    def len(self):
        return _basilisk_ic.svec_len(self._memory_id)
    def is_empty(self):
        return self.len() == 0

_mod.StableVec = StableVec

# --- StableLog ---

class StableLog:
    def __init__(self, memory_id_index=0, memory_id_data=1, _val_type=None):
        self._memory_id = memory_id_index
        self._vt = _type_hint_for(_val_type)
        _basilisk_ic.slog_init(memory_id_index, memory_id_data)
    def append(self, value):
        return _basilisk_ic.slog_append(self._memory_id, _encode(value, self._vt))
    def get(self, index):
        return _decode_val(_basilisk_ic.slog_get(self._memory_id, index))
    def len(self):
        return _basilisk_ic.slog_len(self._memory_id)
    def is_empty(self):
        return self.len() == 0

_mod.StableLog = StableLog

# --- StableCell ---

class StableCell:
    def __init__(self, memory_id=0, default_value=None, _val_type=None):
        self._memory_id = memory_id
        self._vt = _type_hint_for(_val_type)
        _basilisk_ic.scell_init(memory_id, _encode(default_value, self._vt))
    def get(self):
        return _decode_val(_basilisk_ic.scell_get(self._memory_id))
    def set(self, value):
        _basilisk_ic.scell_set(self._memory_id, _encode(value, self._vt))

_mod.StableCell = StableCell

# --- StableMinHeap ---

class StableMinHeap:
    def __init__(self, memory_id=0, _val_type=None):
        self._memory_id = memory_id
        self._vt = _type_hint_for(_val_type)
        _basilisk_ic.sheap_init(memory_id)
    def push(self, value):
        _basilisk_ic.sheap_push(self._memory_id, _encode(value, self._vt))
    def pop(self):
        return _decode_val(_basilisk_ic.sheap_pop(self._memory_id))
    def peek(self):
        return _decode_val(_basilisk_ic.sheap_peek(self._memory_id))
    def len(self):
        return _basilisk_ic.sheap_len(self._memory_id)
    def is_empty(self):
        return self.len() == 0

_mod.StableMinHeap = StableMinHeap

# === Persistent file storage ===
# Files on the canister memfs are persistent by default — they survive
# canister upgrades.  Only files under /tmp/ are volatile.
# File contents are stored in a dedicated StableBTreeMap (memory_id=254).

_VOLATILE_PREFIXES = ["/tmp/", "/proc/", "/dev/"]
_BASILISK_FS_MEM_ID = 254
_BASILISK_FS_MAX_FILE_SIZE = 2_000_000      # 2 MB per file (SBytes hard limit)
_BASILISK_FS_MAX_FILE_COUNT = 500           # max files in store
_BASILISK_FS_MAX_TOTAL_SIZE = 50_000_000    # 50 MB total

class FileStoreError(Exception):
    """Base exception for file persistence errors."""

class FileTooLargeError(FileStoreError):
    """Single file exceeds the per-file size limit."""

class FileStoreLimitError(FileStoreError):
    """File count or total size limit reached."""

_mod.FileStoreError = FileStoreError
_mod.FileTooLargeError = FileTooLargeError
_mod.FileStoreLimitError = FileStoreLimitError

_basilisk_ic.smap_init(_BASILISK_FS_MEM_ID)

import builtins as _builtins
_original_open = _builtins.open

def _fs_total_bytes():
    """Calculate total bytes stored in the file store."""
    _total = 0
    for _kb, _vb in _basilisk_ic.smap_items(_BASILISK_FS_MEM_ID):
        _total += len(_vb)
    return _total

def fs_stats():
    """Return file store usage statistics."""
    _count = _basilisk_ic.smap_len(_BASILISK_FS_MEM_ID)
    _total = 0
    _largest_size = 0
    _largest_path = ""
    for _kb, _vb in _basilisk_ic.smap_items(_BASILISK_FS_MEM_ID):
        _sz = len(_vb)
        _total += _sz
        if _sz > _largest_size:
            _largest_size = _sz
            _largest_path = _kb.decode('utf-8')
    return {
        "files": _count,
        "max_files": _BASILISK_FS_MAX_FILE_COUNT,
        "total_bytes": _total,
        "max_total_bytes": _BASILISK_FS_MAX_TOTAL_SIZE,
        "max_file_bytes": _BASILISK_FS_MAX_FILE_SIZE,
        "largest_bytes": _largest_size,
        "largest_path": _largest_path,
    }

_mod.fs_stats = fs_stats

def _persist_file(path):
    """Read file from memfs and store in the Rust-backed file store."""
    with _original_open(path, 'rb') as _f:
        _content = _f.read()
    _key = path.encode('utf-8')
    _sz = len(_content)
    if _sz > _BASILISK_FS_MAX_FILE_SIZE:
        raise FileTooLargeError(
            f"File '{path}' ({_sz} bytes) exceeds {_BASILISK_FS_MAX_FILE_SIZE} byte limit "
            f"- not persisted to stable memory"
        )
    _existing = _basilisk_ic.smap_get(_BASILISK_FS_MEM_ID, _key)
    if _existing is None:
        _count = _basilisk_ic.smap_len(_BASILISK_FS_MEM_ID)
        if _count >= _BASILISK_FS_MAX_FILE_COUNT:
            raise FileStoreLimitError(
                f"File store full ({_count}/{_BASILISK_FS_MAX_FILE_COUNT} files) "
                f"- '{path}' not persisted to stable memory"
            )
        _total = _fs_total_bytes()
        if _total + _sz > _BASILISK_FS_MAX_TOTAL_SIZE:
            raise FileStoreLimitError(
                f"File store size limit ({_BASILISK_FS_MAX_TOTAL_SIZE} bytes) would be exceeded "
                f"- '{path}' not persisted to stable memory"
            )
    else:
        _old_sz = len(_existing)
        if _sz > _old_sz:
            _total = _fs_total_bytes()
            if _total - _old_sz + _sz > _BASILISK_FS_MAX_TOTAL_SIZE:
                raise FileStoreLimitError(
                    f"File store size limit ({_BASILISK_FS_MAX_TOTAL_SIZE} bytes) would be exceeded "
                    f"- '{path}' not persisted to stable memory"
                )
    _basilisk_ic.smap_insert(_BASILISK_FS_MEM_ID, _key, _content)

class _PersistentFile:
    """Wrapper that auto-persists file content to stable memory on close."""
    __slots__ = ('_pf_file', '_pf_path', '_pf_done')
    def __init__(self, file_obj, path):
        self._pf_file = file_obj
        self._pf_path = path
        self._pf_done = False
    def _pf_persist(self):
        if not self._pf_done:
            self._pf_done = True
            _persist_file(self._pf_path)
    def close(self):
        self._pf_file.close()
        self._pf_persist()
    def __enter__(self):
        return self
    def __exit__(self, *a):
        self._pf_file.close()
        self._pf_persist()
        return False
    def __getattr__(self, name):
        return getattr(self._pf_file, name)
    def __iter__(self):
        return iter(self._pf_file)

def _persistent_open(file, mode='r', *args, **kwargs):
    """Wrapper around built-in open() that auto-persists writes."""
    _f = _original_open(file, mode, *args, **kwargs)
    if isinstance(file, (str, bytes)):
        _p = str(file)
        if any(c in mode for c in 'wxa+') and not any(_p.startswith(pfx) for pfx in _VOLATILE_PREFIXES):
            return _PersistentFile(_f, _p)
    return _f

_builtins.open = _persistent_open

import os as _os
_original_os_remove = _os.remove
_original_os_rename = _os.rename

def _persistent_os_remove(path, *args, **kwargs):
    """Remove file from memfs and from the file store."""
    _original_os_remove(path, *args, **kwargs)
    _p = str(path).encode('utf-8')
    _basilisk_ic.smap_remove(_BASILISK_FS_MEM_ID, _p)

def _persistent_os_rename(src, dst, *args, **kwargs):
    """Rename file in memfs and update the file store."""
    _original_os_rename(src, dst, *args, **kwargs)
    _sk = str(src).encode('utf-8')
    _dk = str(dst).encode('utf-8')
    _data = _basilisk_ic.smap_get(_BASILISK_FS_MEM_ID, _sk)
    _basilisk_ic.smap_remove(_BASILISK_FS_MEM_ID, _sk)
    if _data is not None:
        _basilisk_ic.smap_insert(_BASILISK_FS_MEM_ID, _dk, _data)

_os.remove = _persistent_os_remove
_os.unlink = _persistent_os_remove
_os.rename = _persistent_os_rename

def _basilisk_load_files():
    """Restore files from the Rust-backed stable file store to memfs."""
    import os as _ros
    for _kbytes, _content in _basilisk_ic.smap_items(_BASILISK_FS_MEM_ID):
        try:
            _path = _kbytes.decode('utf-8')
            _parent = _ros.path.dirname(_path)
            if _parent and _parent != '/':
                _ros.makedirs(_parent, exist_ok=True)
            with _original_open(_path, 'wb') as _f:
                _f.write(_content)
        except Exception:
            pass

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

def _parse_record_fields(th):
    """Parse a Candid record type hint into {field_name: field_type}."""
    if not th or not th.strip().startswith('record'):
        return {}
    inner = th.strip()[6:].strip()
    if not inner.startswith('{') or not inner.endswith('}'):
        return {}
    inner = inner[1:-1].strip()
    if not inner:
        return {}
    result = {}
    depth = 0
    cur = ''
    for ch in inner:
        if ch == '{':
            depth += 1
            cur += ch
        elif ch == '}':
            depth -= 1
            cur += ch
        elif ch == ';' and depth == 0:
            p = cur.strip()
            if ':' in p:
                i = p.index(':')
                result[p[:i].strip()] = p[i+1:].strip()
            cur = ''
        else:
            cur += ch
    p = cur.strip()
    if p and ':' in p:
        i = p.index(':')
        result[p[:i].strip()] = p[i+1:].strip()
    return result

def _to_candid_text(v, type_hint=None):
    """Convert a Python value to Candid text representation (recursive).
    If type_hint is provided, uses it for correct type annotations."""
    if v is None:
        return 'null'
    # Auto-wrap with opt when type hint says opt but value is concrete
    if type_hint and type_hint.strip().startswith('opt ') and not isinstance(v, _Opt):
        inner_hint = type_hint.strip()[4:].strip()
        return f'opt {_to_candid_text(v, inner_hint)}'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        if type_hint and type_hint.strip() in ('nat64','nat32','nat16','nat8','int64','int32','int16','int8','nat','int'):
            return f'({v} : {type_hint.strip()})'
        if v >= 0:
            return f'({v} : nat)'
        return str(v)
    if isinstance(v, float):
        return str(v)
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, bytes):
        escaped = "".join("\\{:02x}".format(b) for b in v)
        return 'blob "' + escaped + '"'
    if isinstance(v, _Opt):
        if v.value is None:
            return 'null'
        inner_hint = type_hint[3:].strip() if type_hint and type_hint.strip().startswith('opt') else None
        return f'opt {_to_candid_text(v.value, inner_hint)}'
    if isinstance(v, Principal):
        return f'principal "{v.to_str()}"'
    if isinstance(v, dict):
        # Detect variant: single-key dict where key starts with uppercase
        if len(v) == 1:
            k0, v0 = next(iter(v.items()))
            if isinstance(k0, str) and len(k0) > 0 and (k0[0].isupper() or k0 in ('install','reinstall','upgrade','running','stopping','stopped','get','head','post')):
                inner = _to_candid_text(v0)
                return f'variant {{ {k0} = {inner} }}'
        ft = _parse_record_fields(type_hint) if type_hint else {}
        fields = [f'{k} = {_to_candid_text(val, ft.get(k))}' for k, val in v.items()]
        return f'record {{ {"; ".join(fields)} }}'
    if isinstance(v, (list, tuple)):
        # Handle func type: (Principal, method_name_str) — detect by shape
        if len(v) == 2 and isinstance(v[1], str) and isinstance(v[0], Principal):
            ptxt = v[0].to_str()
            return f'func "{ptxt}".{v[1]}'
        elem_hint = type_hint[3:].strip() if type_hint and type_hint.strip().startswith('vec') else None
        items = [_to_candid_text(item, elem_hint) for item in v]
        return f'vec {{ {"; ".join(items)} }}'
    # Fallback: try str()
    return str(v)

class _ServiceCall:
    """Represents a pending cross-canister call to be yielded from a generator.
    Presents itself as a call_raw descriptor for the Rust async handler."""
    def __init__(self, canister_principal, method_name, call_args=None, payment=0, arg_type=None):
        # Store original Python args + type for Rust-side typed Candid encoding
        # (needed for correct func type annotations, e.g. query on HTTP transforms)
        self._python_call_args = call_args if call_args else ()
        self._candid_arg_type = arg_type
        # Also encode via text path as fallback
        if call_args:
            parts = [_to_candid_text(a, arg_type) for a in call_args]
            candid_text = f"({', '.join(parts)})"
            try:
                raw_args = _basilisk_ic.candid_encode(candid_text)
            except Exception:
                # Fallback: empty args
                raw_args = b'DIDL\x00\x00'
        else:
            raw_args = b'DIDL\x00\x00'
        # Keep original attributes for drive_generator / perform_service_call in method_dispatch.rs
        self.canister_principal = canister_principal
        self.method_name = method_name
        self._raw_args = raw_args
        self.payment = payment
        # Also set .name and .args for async_handler.rs call_raw protocol
        principal_text = str(canister_principal) if not isinstance(canister_principal, str) else canister_principal
        self.name = "call_raw"
        self.args = [principal_text, method_name, raw_args, payment]
        self._payment = payment
    def with_cycles(self, cycles):
        self.payment = cycles
        self.args[3] = cycles
        self._payment = cycles
        return self
    def with_cycles128(self, cycles):
        self.name = "call_raw128"
        self.payment = cycles
        self.args[3] = cycles
        self._payment = cycles
        return self
    def notify(self):
        return _basilisk_ic.notify_service_call(self)

class _ServiceMethodProxy:
    """Proxy for a service method that creates _ServiceCall descriptors."""
    def __init__(self, principal, method_name, return_type=None, arg_type=None):
        self._principal = principal
        self._method_name = method_name
        self._return_type = return_type
        self._arg_type = arg_type
    def __call__(self, *args, **kwargs):
        call = _ServiceCall(self._principal, self._method_name, args, arg_type=self._arg_type)
        if self._return_type:
            call._return_candid_type = self._return_type
        return call

class _ServiceMethodDescriptor:
    """Descriptor that returns a _ServiceMethodProxy when accessed on a Service instance."""
    def __init__(self, func):
        self.name = func.__name__
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        rt = None
        at = None
        if hasattr(obj, '_return_types'):
            rt = obj._return_types.get(self.name)
        if hasattr(obj, '_arg_types'):
            at = obj._arg_types.get(self.name)
        return _ServiceMethodProxy(obj._principal, self.name, rt, at)

def service_query(func):
    return _ServiceMethodDescriptor(func)

def service_update(func):
    return _ServiceMethodDescriptor(func)

class Service:
    _return_types = {}
    _arg_types = {}
    def __init__(self, principal=None):
        self._principal = principal
    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        rt = self._return_types.get(name) if self._return_types else None
        at = self._arg_types.get(name) if self._arg_types else None
        return _ServiceMethodProxy(self._principal, name, rt, at)

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
        if "Ok" in cases:
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
    stable_read = staticmethod(_basilisk_ic.stable_read)
    stable_write = staticmethod(_basilisk_ic.stable_write)
    stable64_read = staticmethod(_basilisk_ic.stable64_read)
    stable64_write = staticmethod(_basilisk_ic.stable64_write)
    @staticmethod
    def stable_grow(new_pages):
        result = _basilisk_ic.stable_grow(new_pages)
        if result < 0:
            return {"Err": {"OutOfMemory": None}}
        return {"Ok": result}
    @staticmethod
    def stable64_grow(new_pages):
        result = _basilisk_ic.stable64_grow(new_pages)
        if result < 0:
            return {"Err": {"OutOfMemory": None}}
        return {"Ok": result}
    set_timer = staticmethod(_basilisk_ic.set_timer)
    set_timer_interval = staticmethod(_basilisk_ic.set_timer_interval)
    clear_timer = staticmethod(_basilisk_ic.clear_timer)
    is_controller = staticmethod(_basilisk_ic.is_controller)
    call_raw = staticmethod(_basilisk_ic.call_raw)
    call_raw128 = staticmethod(_basilisk_ic.call_raw128)
# Override call_raw/call_raw128 to return _ServiceCall objects (for generator yield)
@staticmethod
def _ic_call_raw(canister_id, method, args_raw, cycles=0):
    call = _ServiceCall(canister_id, method)
    raw = bytes(args_raw) if not isinstance(args_raw, bytes) else args_raw
    call._raw_args = raw
    call.args[2] = raw
    call.payment = int(cycles)
    call.args[3] = int(cycles)
    call._payment = int(cycles)
    call._return_raw = True
    return call

@staticmethod
def _ic_call_raw128(canister_id, method, args_raw, cycles=0):
    call = _ServiceCall(canister_id, method)
    raw = bytes(args_raw) if not isinstance(args_raw, bytes) else args_raw
    call._raw_args = raw
    call.args[2] = raw
    call.payment = int(cycles)
    call.args[3] = int(cycles)
    call._return_raw = True
    call._payment = int(cycles)
    call.name = "call_raw128"
    return call

ic.call_raw = _ic_call_raw
ic.call_raw128 = _ic_call_raw128

@staticmethod
def _ic_notify_raw(canister_id, method, args_raw, cycles=0):
    return _basilisk_ic.notify_raw(canister_id, method, args_raw, int(cycles))

ic.notify_raw = _ic_notify_raw

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
_sys.modules["bsk"] = _mod  # convenience alias (like np for numpy)

# === Stub: basilisk.canisters.management ===
_M = type(_sys)
_canisters = _M('basilisk.canisters')
_canisters.__file__ = '<frozen basilisk.canisters>'
_canisters.__path__ = []
_canisters.__package__ = 'basilisk.canisters'
_mgmt = _M('basilisk.canisters.management')
_mgmt.__file__ = '<frozen basilisk.canisters.management>'
_mgmt.__path__ = []
_mgmt.__package__ = 'basilisk.canisters.management'
_mgmt_type_names = [
    'CanisterSettings', 'CanisterStatus', 'CanisterStatusArgs',
    'CanisterStatusResult', 'CreateCanisterArgs', 'CreateCanisterResult',
    'DefiniteCanisterSettings', 'DeleteCanisterArgs', 'DepositCyclesArgs',
    'InstallCodeArgs', 'InstallCodeMode',
    'ProvisionalCreateCanisterWithCyclesArgs',
    'ProvisionalCreateCanisterWithCyclesResult',
    'ProvisionalTopUpCanisterArgs', 'StartCanisterArgs',
    'StopCanisterArgs', 'UninstallCodeArgs', 'UpdateSettingsArgs',
    'ChunkHash', 'UploadChunkArgs', 'UploadChunkResult',
    'ClearChunkStoreArgs', 'StoredChunksArgs', 'StoredChunksResult',
    'InstallChunkedCodeArgs',
    'EcdsaCurve', 'EcdsaPublicKeyArgs', 'EcdsaPublicKeyResult',
    'KeyId', 'SignWithEcdsaArgs', 'SignWithEcdsaResult',
    'HttpHeader', 'HttpMethod', 'HttpRequestArgs', 'HttpResponse',
    'HttpTransform', 'HttpTransformArgs', 'HttpTransformFunc',
    'BitcoinAddress', 'BitcoinNetwork', 'BlockHash',
    'GetBalanceArgs', 'GetCurrentFeePercentilesArgs',
    'GetUtxosArgs', 'GetUtxosResult', 'Page',
    'MillisatoshiPerByte', 'Outpoint', 'Satoshi',
    'SendTransactionArgs', 'SendTransactionError', 'Utxo', 'UtxosFilter',
]
for _n in _mgmt_type_names:
    setattr(_mgmt, _n, dict)
class _MgmtService:
    def __init__(self, principal):
        self.canister_id = principal
    def __getattr__(self, name):
        async def _stub(*a, **kw):
            raise RuntimeError(f"management_canister.{name}() not available in CPython template")
        return _stub
_mgmt.management_canister = _MgmtService(Principal.from_str('aaaaa-aa'))
_mgmt.ManagementCanister = _MgmtService
_canisters.management = _mgmt
_mod.canisters = _canisters
_sys.modules['basilisk.canisters'] = _canisters
_sys.modules['basilisk.canisters.management'] = _mgmt
for _sub in ('basic', 'tecdsa', 'http', 'bitcoin'):
    _submod = _M(f'basilisk.canisters.management.{_sub}')
    _submod.__file__ = f'<frozen basilisk.canisters.management.{_sub}>'
    for _n in _mgmt_type_names:
        setattr(_submod, _n, dict)
    _sys.modules[f'basilisk.canisters.management.{_sub}'] = _submod

# === Stub: basilisk.canisters.ledger ===
_ledger_mod = _M('basilisk.canisters.ledger')
_ledger_mod.__file__ = '<frozen basilisk.canisters.ledger>'
_ledger_mod.__path__ = []
_ledger_mod.__package__ = 'basilisk.canisters.ledger'
for _n in ['Address', 'Archives', 'DecimalsResult', 'GetBlocksArgs',
           'NameResult', 'QueryBlocksResponse', 'SymbolResult',
           'Tokens', 'TransferFee', 'TransferResult']:
    setattr(_ledger_mod, _n, dict)
class _LedgerService:
    def __init__(self, principal):
        self.canister_id = principal
    def __getattr__(self, name):
        async def _stub(*a, **kw):
            raise RuntimeError(f"Ledger.{name}() not available in CPython template")
        return _stub
_ledger_mod.Ledger = _LedgerService
_canisters.ledger = _ledger_mod
_sys.modules['basilisk.canisters.ledger'] = _ledger_mod

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
