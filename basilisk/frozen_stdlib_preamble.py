import sys as _sys

# --- Bootstrap import system for WASI CPython ---
# When _Py_InitializeMain is skipped, sys.meta_path may not be consulted
# and many stdlib modules aren't available (no filesystem).
# Strategy: wrap builtins.__import__ to catch ModuleNotFoundError and
# auto-create empty stub modules.  This is more reliable than sys.meta_path
# which may not be fully functional without _Py_InitializeMain.

# Also try to install BuiltinImporter/FrozenImporter if missing
_frozen = _sys.modules.get('_frozen_importlib')
if _frozen:
    if not _sys.meta_path:
        _sys.meta_path.append(_frozen.BuiltinImporter)
        _sys.meta_path.append(_frozen.FrozenImporter)
try:
    del _frozen
except NameError:
    pass

import builtins as _builtins
_orig_import = _builtins.__import__
_ModuleType = type(_sys)

def _wasi_safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    try:
        return _orig_import(name, globals, locals, fromlist, level)
    except (ModuleNotFoundError, ImportError):
        # For relative imports (level > 0), don't stub - let it fail normally
        if level > 0:
            raise
        # Only stub truly missing modules.
        # If the module is already in sys.modules, the error came from INSIDE
        # module loading (e.g. a sub-import failed) - let it propagate.
        if name in _sys.modules:
            raise
        # Create a stub module so the import doesn't crash
        mod = _ModuleType(name)
        mod.__file__ = "<wasi-stub>"
        mod.__path__ = []
        mod.__package__ = name
        _sys.modules[name] = mod
        return mod

# NOTE: _wasi_safe_import is installed AFTER all rich stdlib stubs below.
# This ensures try/except import blocks use _orig_import and our rich stubs
# get registered, not empty wasi-stubs.

# --- Patch basilisk module with missing/broken classes ---
_bmod = _sys.modules.get('basilisk')
if _bmod:
    try:
        import _basilisk_ic as _bic
    except (ImportError, ModuleNotFoundError):
        _bic = None

    # StableBTreeMap: ALWAYS override — the shim version delegates to
    # _basilisk_ic.stable_b_tree_map_*  which don't exist in the pre-built
    # CPython template.  This version falls back to an in-memory dict.
    class _StableBTreeMap:
        _bic = _bic  # capture reference before cleanup
        def __init__(self, memory_id, max_key_size=0, max_value_size=0):
            self.memory_id = memory_id
            self.max_key_size = max_key_size
            self.max_value_size = max_value_size
            self._native = self._bic and hasattr(self._bic, f"stable_b_tree_map_{memory_id}_get")
            if not self._native:
                self._data = {}
        def __class_getitem__(cls, params):
            return cls
        def _fn(self, op):
            return getattr(self._bic, f"stable_b_tree_map_{self.memory_id}_{op}")
        def contains_key(self, key):
            if self._native:
                return self._fn("contains_key")(key)
            return key in self._data
        def get(self, key):
            if self._native:
                return self._fn("get")(key)
            return self._data.get(key)
        def _estimate_size(self, value):
            if isinstance(value, bytes):
                return len(value)
            if isinstance(value, str):
                return len(value.encode('utf-8'))
            if isinstance(value, bool):
                return 1
            if isinstance(value, (int, float)):
                return 8
            try:
                import json as _j
                return len(_j.dumps(value).encode('utf-8'))
            except Exception:
                return 0
        def insert(self, key, value):
            if self._native:
                return self._fn("insert")(key, value)
            if hasattr(self, 'max_key_size') and self.max_key_size > 0:
                ks = self._estimate_size(key)
                if ks > self.max_key_size:
                    raise Exception(f"Key is too large. Expected <= {self.max_key_size} bytes, received {ks} bytes")
            if hasattr(self, 'max_value_size') and self.max_value_size > 0:
                vs = self._estimate_size(value)
                if vs > self.max_value_size:
                    raise Exception(f"Value is too large. Expected <= {self.max_value_size} bytes, received {vs} bytes")
            old = self._data.get(key)
            self._data[key] = value
            return old
        def is_empty(self):
            if self._native:
                return self._fn("is_empty")()
            return len(self._data) == 0
        def items(self):
            if self._native:
                return self._fn("items")()
            return list(self._data.items())
        def keys(self):
            if self._native:
                return self._fn("keys")()
            return list(self._data.keys())
        def len(self):
            if self._native:
                return self._fn("len")()
            return len(self._data)
        def remove(self, key):
            if self._native:
                return self._fn("remove")(key)
            return self._data.pop(key, None)
        def values(self):
            if self._native:
                return self._fn("values")()
            return list(self._data.values())
    _bmod.StableBTreeMap = _StableBTreeMap

    # Service and match: only add if missing
    if not hasattr(_bmod, 'Service'):
        class _Service:
            def __init__(self, canister_id):
                self.canister_id = canister_id
        _bmod.Service = _Service

    if not hasattr(_bmod, 'match'):
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
        _bmod.match = _match

    # Fix Variant/Record: dict.__init_subclass__() doesn't accept keyword
    # arguments like total=False.  Replace with subclasses that do.
    class _Record(dict):
        def __class_getitem__(cls, params):
            return cls
        def __init_subclass__(cls, **kw):
            pass
    class _Variant(dict):
        def __class_getitem__(cls, params):
            return cls
        def __init_subclass__(cls, **kw):
            pass
    _bmod.Record = _Record
    _bmod.Variant = _Variant

    try:
        del _bic, _StableBTreeMap, _Record, _Variant
    except NameError:
        pass
    try:
        del _Service, _match
    except NameError:
        pass

# Fix None-valued type aliases that need to be subscriptable (e.g. Opt[int])
# This MUST be outside the StableBTreeMap check — Opt=None exists in all template versions.
if _bmod:
    class _CandidTypeAlias:
        """Subscriptable stub for Candid type aliases like Opt, Alias, Manual."""
        def __class_getitem__(cls, params):
            return cls
        def __init_subclass__(cls, **kw):
            pass
    _none_attrs = ['Opt', 'Alias', 'Manual', 'CallResult', 'NotifyResult', 'GuardType']
    for _attr in _none_attrs:
        if getattr(_bmod, _attr, None) is None:
            setattr(_bmod, _attr, _CandidTypeAlias)
    try:
        del _CandidTypeAlias, _none_attrs, _attr
    except NameError:
        pass

try:
    del _bmod
except NameError:
    pass

# --- Stub: basilisk.canisters.management ---
# Many examples import types from this subpackage.  In the CPython template
# these are just dict subclasses (Record/Variant).  Provide stubs so the
# imports succeed.
def _register_management_canister_stubs():
    _bmod = _sys.modules.get('basilisk')
    if not _bmod:
        return
    _M = type(_sys)
    # All type names are simply dict (Record/Variant stand-ins)
    _type_names = [
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
    # Create the module hierarchy
    _canisters = _M('basilisk.canisters')
    _canisters.__file__ = '<frozen basilisk.canisters>'
    _canisters.__path__ = []
    _canisters.__package__ = 'basilisk.canisters'
    _mgmt = _M('basilisk.canisters.management')
    _mgmt.__file__ = '<frozen basilisk.canisters.management>'
    _mgmt.__path__ = []
    _mgmt.__package__ = 'basilisk.canisters.management'
    for _n in _type_names:
        setattr(_mgmt, _n, dict)
    # management_canister singleton — use real Service class so methods
    # return _ServiceMethodProxy → _ServiceCall with .with_cycles() etc.
    _ServiceCls = getattr(_bmod, 'Service', None)
    _P = getattr(_bmod, 'Principal', None)
    if _ServiceCls and _P:
        _mgmt.management_canister = _ServiceCls(_P.from_str('aaaaa-aa'))
        _mgmt.ManagementCanister = _ServiceCls
    elif _P:
        # Fallback if Service not yet available
        class _MgmtService:
            def __init__(self, principal):
                self._principal = principal
            def __getattr__(self, name):
                if name.startswith('_'):
                    raise AttributeError(name)
                async def _stub(*a, **kw):
                    raise RuntimeError(f"management_canister.{name}() not available in CPython template")
                return _stub
        _mgmt.management_canister = _MgmtService(_P.from_str('aaaaa-aa'))
        _mgmt.ManagementCanister = _MgmtService
    else:
        class _MgmtService:
            def __init__(self, principal):
                self._principal = principal
            def __getattr__(self, name):
                if name.startswith('_'):
                    raise AttributeError(name)
                async def _stub(*a, **kw):
                    raise RuntimeError(f"management_canister.{name}() not available in CPython template")
                return _stub
        _mgmt.management_canister = _MgmtService('aaaaa-aa')
        _mgmt.ManagementCanister = _MgmtService
    _canisters.management = _mgmt
    if not hasattr(_bmod, 'canisters'):
        _bmod.canisters = _canisters
    _sys.modules['basilisk.canisters'] = _canisters
    _sys.modules['basilisk.canisters.management'] = _mgmt
    # Also register sub-modules so `from basilisk.canisters.management.http import ...` works
    for _sub in ('basic', 'tecdsa', 'http', 'bitcoin'):
        _submod = _M(f'basilisk.canisters.management.{_sub}')
        _submod.__file__ = f'<frozen basilisk.canisters.management.{_sub}>'
        # Copy all type names into each submodule
        for _n in _type_names:
            setattr(_submod, _n, dict)
        _sys.modules[f'basilisk.canisters.management.{_sub}'] = _submod

if 'basilisk.canisters.management' not in _sys.modules:
    _register_management_canister_stubs()
del _register_management_canister_stubs

# --- Stub: basilisk.canisters.ledger ---
def _register_ledger_canister_stubs():
    _bmod = _sys.modules.get('basilisk')
    if not _bmod:
        return
    _M = type(_sys)
    _type_names = [
        'Address', 'Archives', 'DecimalsResult', 'GetBlocksArgs',
        'NameResult', 'QueryBlocksResponse', 'SymbolResult',
        'Tokens', 'TransferFee', 'TransferResult',
    ]
    _ledger_mod = _M('basilisk.canisters.ledger')
    _ledger_mod.__file__ = '<frozen basilisk.canisters.ledger>'
    _ledger_mod.__path__ = []
    _ledger_mod.__package__ = 'basilisk.canisters.ledger'
    for _n in _type_names:
        setattr(_ledger_mod, _n, dict)
    # Ledger service — use real Service class so methods work properly
    _ServiceCls = getattr(_bmod, 'Service', None)
    if _ServiceCls:
        _ledger_mod.Ledger = _ServiceCls
    else:
        class _LedgerService:
            def __init__(self, principal):
                self._principal = principal
            def __getattr__(self, name):
                if name.startswith('_'):
                    raise AttributeError(name)
                async def _stub(*a, **kw):
                    raise RuntimeError(f"Ledger.{name}() not available in CPython template")
                return _stub
        _ledger_mod.Ledger = _LedgerService
    # Ensure basilisk.canisters exists
    if 'basilisk.canisters' not in _sys.modules:
        _canisters = _M('basilisk.canisters')
        _canisters.__file__ = '<frozen basilisk.canisters>'
        _canisters.__path__ = []
        _canisters.__package__ = 'basilisk.canisters'
        _sys.modules['basilisk.canisters'] = _canisters
    _sys.modules['basilisk.canisters'].ledger = _ledger_mod
    _sys.modules['basilisk.canisters.ledger'] = _ledger_mod

if 'basilisk.canisters.ledger' not in _sys.modules:
    _register_ledger_canister_stubs()
del _register_ledger_canister_stubs

# --- builtins.open: not available in WASI (no filesystem) ---
if not hasattr(_builtins, 'open'):
    def _stub_open(*a, **kw):
        raise OSError("open() not available in WASI (no filesystem)")
    _builtins.open = _stub_open
    try:
        del _stub_open
    except NameError:
        pass

# --- frozen stdlib: json module (pure Python, no C extensions) ---
# On WASI/IC there is no filesystem, so stdlib packages like `json`
# aren't importable. This registers a minimal pure-Python json module
# in sys.modules so that `import json` works out of the box.

def _register_json():
    _ESCAPE = {'"': '\\"', '\\': '\\\\', '\b': '\\b', '\f': '\\f',
               '\n': '\\n', '\r': '\\r', '\t': '\\t'}

    def _enc(s):
        parts = ['"']
        for c in s:
            if c in _ESCAPE:
                parts.append(_ESCAPE[c])
            elif ord(c) < 0x20:
                parts.append(f'\\u{ord(c):04x}')
            else:
                parts.append(c)
        parts.append('"')
        return ''.join(parts)

    class JSONDecodeError(ValueError):
        pass

    def dumps(obj, ensure_ascii=True, sort_keys=False, indent=None,
              separators=None, default=None, **kw):
        def _e(o):
            if o is None: return "null"
            if o is True: return "true"
            if o is False: return "false"
            if isinstance(o, str): return _enc(o)
            if isinstance(o, int): return str(o)
            if isinstance(o, float):
                if o != o: return "NaN"
                if o == float("inf"): return "Infinity"
                if o == float("-inf"): return "-Infinity"
                return repr(o)
            if isinstance(o, (list, tuple)):
                return "[" + ",".join(_e(v) for v in o) + "]"
            if isinstance(o, dict):
                items = sorted(o.items()) if sort_keys else o.items()
                return "{" + ",".join(_enc(str(k)) + ":" + _e(v)
                                      for k, v in items) + "}"
            if default is not None: return _e(default(o))
            raise TypeError(
                f"Object of type {type(o).__name__} is not JSON serializable")
        return _e(obj)

    def _parse_string(s, idx, n):
        parts = []
        while idx < n:
            c = s[idx]
            if c == '"':
                return ''.join(parts), idx + 1
            if c == '\\':
                idx += 1
                if idx >= n:
                    raise JSONDecodeError("Unterminated string escape")
                esc = s[idx]
                if esc == '"': parts.append('"')
                elif esc == '\\': parts.append('\\')
                elif esc == '/': parts.append('/')
                elif esc == 'b': parts.append('\b')
                elif esc == 'f': parts.append('\f')
                elif esc == 'n': parts.append('\n')
                elif esc == 'r': parts.append('\r')
                elif esc == 't': parts.append('\t')
                elif esc == 'u':
                    h = s[idx + 1:idx + 5]
                    if len(h) < 4:
                        raise JSONDecodeError("Truncated \\uXXXX escape")
                    parts.append(chr(int(h, 16)))
                    idx += 4
                else:
                    parts.append(esc)
                idx += 1
            else:
                parts.append(c)
                idx += 1
        raise JSONDecodeError("Unterminated string")

    def loads(s, **kw):
        if isinstance(s, (bytes, bytearray)):
            s = s.decode("utf-8")
        n = len(s)
        idx = [0]

        def _ws():
            while idx[0] < n and s[idx[0]] in " \t\n\r":
                idx[0] += 1

        def _val():
            _ws()
            if idx[0] >= n:
                raise JSONDecodeError("Unexpected end of JSON")
            c = s[idx[0]]
            if c == '"':
                r, new_idx = _parse_string(s, idx[0] + 1, n)
                idx[0] = new_idx
                return r
            if c == '{':
                idx[0] += 1; _ws(); d = {}
                if idx[0] < n and s[idx[0]] == '}':
                    idx[0] += 1; return d
                while True:
                    _ws(); k = _val(); _ws()
                    if idx[0] >= n or s[idx[0]] != ':':
                        raise JSONDecodeError("Expected ':'")
                    idx[0] += 1; v = _val(); d[k] = v; _ws()
                    if idx[0] < n and s[idx[0]] == ',':
                        idx[0] += 1
                    elif idx[0] < n and s[idx[0]] == '}':
                        idx[0] += 1; return d
                    else:
                        raise JSONDecodeError("Expected ',' or '}'")
            if c == '[':
                idx[0] += 1; _ws(); a = []
                if idx[0] < n and s[idx[0]] == ']':
                    idx[0] += 1; return a
                while True:
                    a.append(_val()); _ws()
                    if idx[0] < n and s[idx[0]] == ',':
                        idx[0] += 1
                    elif idx[0] < n and s[idx[0]] == ']':
                        idx[0] += 1; return a
                    else:
                        raise JSONDecodeError("Expected ',' or ']'")
            if s[idx[0]:idx[0] + 4] == "true":
                idx[0] += 4; return True
            if s[idx[0]:idx[0] + 5] == "false":
                idx[0] += 5; return False
            if s[idx[0]:idx[0] + 4] == "null":
                idx[0] += 4; return None
            # Number
            st = idx[0]
            if idx[0] < n and s[idx[0]] == '-':
                idx[0] += 1
            while idx[0] < n and s[idx[0]].isdigit():
                idx[0] += 1
            flt = False
            if idx[0] < n and s[idx[0]] == '.':
                flt = True; idx[0] += 1
                while idx[0] < n and s[idx[0]].isdigit():
                    idx[0] += 1
            if idx[0] < n and s[idx[0]] in "eE":
                flt = True; idx[0] += 1
                if idx[0] < n and s[idx[0]] in "+-":
                    idx[0] += 1
                while idx[0] < n and s[idx[0]].isdigit():
                    idx[0] += 1
            ns = s[st:idx[0]]
            if not ns:
                raise JSONDecodeError(f"Unexpected char at {idx[0]}")
            return float(ns) if flt else int(ns)

        return _val()

    m = type(_sys)("json")
    m.__file__ = "<frozen json>"
    m.dumps = dumps
    m.loads = loads
    m.JSONDecodeError = JSONDecodeError
    _sys.modules["json"] = m

try:
    import json
except ImportError:
    _register_json()
del _register_json


# --- In-memory filesystem (memfs) ---
# Provides builtins.open, os, os.path, tempfile, pathlib, and io backed by a
# dict so that user code and stdlib modules that rely on file I/O work without
# requiring an actual WASI filesystem.

def _install_memfs():
    _MEMFS = {}          # absolute path (str) -> bytes content
    _MEMFS_DIRS = {"/"}  # set of directory paths

    # ---- helpers ----
    def _normpath(path):
        """Normalize a path to an absolute POSIX string."""
        if not isinstance(path, str):
            path = str(path)
        # Collapse consecutive slashes and resolve '.' / '..'
        parts = []
        for part in path.replace("\\", "/").split("/"):
            if part == "" or part == ".":
                continue
            if part == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(part)
        result = "/" + "/".join(parts)
        return result

    def _dirname(path):
        path = _normpath(path)
        idx = path.rfind("/")
        if idx == 0:
            return "/"
        return path[:idx] if idx > 0 else "/"

    def _basename(path):
        path = _normpath(path)
        idx = path.rfind("/")
        return path[idx + 1:] if idx >= 0 else path

    def _join(*args):
        result = ""
        for part in args:
            if not isinstance(part, str):
                part = str(part)
            if part.startswith("/"):
                result = part
            else:
                result = (result.rstrip("/") + "/" + part) if result else part
        return _normpath(result) if result else "/"

    def _makedirs(path, exist_ok=False):
        path = _normpath(path)
        if path in _MEMFS_DIRS:
            if not exist_ok:
                raise FileExistsError(f"[Errno 17] File exists: '{path}'")
            return
        parts = path.lstrip("/").split("/")
        current = ""
        for part in parts:
            current += "/" + part
            if current in _MEMFS_DIRS:
                continue
            if current in _MEMFS:
                raise OSError(f"[Errno 20] Not a directory: '{current}'")
            _MEMFS_DIRS.add(current)

    # ---- file-like objects ----
    class _MemFile:
        """In-memory file-like object backed by _MEMFS."""
        def __init__(self, path, mode, binary):
            self._path = path
            self._mode = mode
            self._binary = binary
            self.closed = False
            # Read existing content into buffer
            if "r" in mode:
                raw = _MEMFS.get(path)
                if raw is None:
                    raise FileNotFoundError(f"[Errno 2] No such file or directory: '{path}'")
                self._data = bytearray(raw)
            elif "a" in mode:
                self._data = bytearray(_MEMFS.get(path, b""))
            else:  # w
                self._data = bytearray()
            self._pos = len(self._data) if "a" in mode else 0

        def read(self, size=-1):
            if self.closed:
                raise ValueError("I/O operation on closed file")
            if size == -1:
                chunk = self._data[self._pos:]
                self._pos = len(self._data)
            else:
                chunk = self._data[self._pos:self._pos + size]
                self._pos += len(chunk)
            if self._binary:
                return bytes(chunk)
            return chunk.decode("utf-8", errors="replace")

        def readline(self, size=-1):
            if self.closed:
                raise ValueError("I/O operation on closed file")
            end = len(self._data)
            start = self._pos
            i = start
            while i < end:
                if self._data[i] == ord('\n'):
                    i += 1
                    break
                i += 1
            chunk = self._data[start:i]
            self._pos = i
            if self._binary:
                return bytes(chunk)
            return chunk.decode("utf-8", errors="replace")

        def readlines(self):
            lines = []
            while True:
                line = self.readline()
                if not line:
                    break
                lines.append(line)
            return lines

        def write(self, data):
            if self.closed:
                raise ValueError("I/O operation on closed file")
            if isinstance(data, str):
                data = data.encode("utf-8")
            elif not isinstance(data, (bytes, bytearray, memoryview)):
                raise TypeError("write() argument must be str or bytes-like")
            # Replace or extend at current position
            data = bytes(data)
            end = self._pos + len(data)
            if end > len(self._data):
                self._data.extend(b'\x00' * (end - len(self._data)))
            self._data[self._pos:end] = data
            self._pos = end
            return len(data)

        def writelines(self, lines):
            for line in lines:
                self.write(line)

        def tell(self):
            return self._pos

        def seek(self, pos, whence=0):
            if whence == 0:
                self._pos = pos
            elif whence == 1:
                self._pos += pos
            elif whence == 2:
                self._pos = len(self._data) + pos
            self._pos = max(0, min(self._pos, len(self._data)))
            return self._pos

        def truncate(self, size=None):
            if size is None:
                size = self._pos
            del self._data[size:]
            return size

        def flush(self):
            pass

        def close(self):
            if not self.closed:
                _MEMFS[self._path] = bytes(self._data)
                self.closed = True

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

        def __iter__(self):
            return iter(self.readlines())

        @property
        def name(self):
            return self._path

        def fileno(self):
            raise OSError("memfs files have no real file descriptor")

        def isatty(self):
            return False

        def readable(self):
            return "r" in self._mode

        def writable(self):
            return "w" in self._mode or "a" in self._mode

        def seekable(self):
            return True

    # ---- builtins.open ----
    def _memfs_open(file, mode="r", buffering=-1, encoding=None,
                    errors=None, newline=None, closefd=True, opener=None):
        path = _normpath(str(file))
        binary = "b" in mode
        # Ensure parent directory exists (auto-create if writing)
        parent = _dirname(path)
        if parent not in _MEMFS_DIRS:
            if "r" in mode:
                raise FileNotFoundError(
                    f"[Errno 2] No such file or directory: '{file}'")
            _makedirs(parent, exist_ok=True)
        if "r" in mode and path not in _MEMFS:
            raise FileNotFoundError(
                f"[Errno 2] No such file or directory: '{file}'")
        if "x" in mode and path in _MEMFS:
            raise FileExistsError(f"[Errno 17] File exists: '{file}'")
        return _MemFile(path, mode, binary)

    _builtins.open = _memfs_open

    # ---- io module ----
    def _register_io():
        import sys as _s
        m = type(_s)("io")
        m.__file__ = "<frozen io>"

        class StringIO:
            def __init__(self, initial_value="", newline="\n"):
                self._data = initial_value
                self._pos = 0
                self.closed = False
            def read(self, size=-1):
                if size == -1:
                    chunk = self._data[self._pos:]
                    self._pos = len(self._data)
                else:
                    chunk = self._data[self._pos:self._pos + size]
                    self._pos += len(chunk)
                return chunk
            def readline(self, size=-1):
                i = self._data.find('\n', self._pos)
                if i == -1:
                    chunk = self._data[self._pos:]
                    self._pos = len(self._data)
                else:
                    chunk = self._data[self._pos:i + 1]
                    self._pos = i + 1
                return chunk
            def readlines(self):
                lines = []
                while True:
                    line = self.readline()
                    if not line:
                        break
                    lines.append(line)
                return lines
            def write(self, s):
                end = self._pos + len(s)
                self._data = self._data[:self._pos] + s + self._data[end:]
                self._pos = end
                return len(s)
            def writelines(self, lines):
                for l in lines:
                    self.write(l)
            def getvalue(self):
                return self._data
            def tell(self):
                return self._pos
            def seek(self, pos, whence=0):
                if whence == 0:
                    self._pos = pos
                elif whence == 1:
                    self._pos += pos
                elif whence == 2:
                    self._pos = len(self._data) + pos
                self._pos = max(0, min(self._pos, len(self._data)))
                return self._pos
            def truncate(self, size=None):
                if size is None:
                    size = self._pos
                self._data = self._data[:size]
                return size
            def flush(self):
                pass
            def close(self):
                self.closed = True
            def __enter__(self):
                return self
            def __exit__(self, *a):
                self.close()
            def __iter__(self):
                return iter(self.readlines())
            def readable(self):
                return True
            def writable(self):
                return True
            def seekable(self):
                return True

        class BytesIO:
            def __init__(self, initial_bytes=b""):
                self._data = bytearray(initial_bytes)
                self._pos = 0
                self.closed = False
            def read(self, size=-1):
                if size == -1:
                    chunk = bytes(self._data[self._pos:])
                    self._pos = len(self._data)
                else:
                    chunk = bytes(self._data[self._pos:self._pos + size])
                    self._pos += len(chunk)
                return chunk
            def readline(self, size=-1):
                try:
                    i = self._data.index(ord('\n'), self._pos)
                    chunk = bytes(self._data[self._pos:i + 1])
                    self._pos = i + 1
                except ValueError:
                    chunk = bytes(self._data[self._pos:])
                    self._pos = len(self._data)
                return chunk
            def readlines(self):
                lines = []
                while True:
                    line = self.readline()
                    if not line:
                        break
                    lines.append(line)
                return lines
            def write(self, b):
                if isinstance(b, memoryview):
                    b = bytes(b)
                end = self._pos + len(b)
                if end > len(self._data):
                    self._data.extend(b'\x00' * (end - len(self._data)))
                self._data[self._pos:end] = b
                self._pos = end
                return len(b)
            def writelines(self, lines):
                for l in lines:
                    self.write(l)
            def getvalue(self):
                return bytes(self._data)
            def tell(self):
                return self._pos
            def seek(self, pos, whence=0):
                if whence == 0:
                    self._pos = pos
                elif whence == 1:
                    self._pos += pos
                elif whence == 2:
                    self._pos = len(self._data) + pos
                self._pos = max(0, min(self._pos, len(self._data)))
                return self._pos
            def truncate(self, size=None):
                if size is None:
                    size = self._pos
                del self._data[size:]
                return size
            def flush(self):
                pass
            def close(self):
                self.closed = True
            def __enter__(self):
                return self
            def __exit__(self, *a):
                self.close()
            def __iter__(self):
                return iter(self.readlines())
            def readable(self):
                return True
            def writable(self):
                return True
            def seekable(self):
                return True

        m.StringIO = StringIO
        m.BytesIO = BytesIO
        m.IOBase = object
        m.RawIOBase = object
        m.BufferedIOBase = object
        m.TextIOBase = object
        m.TextIOWrapper = StringIO
        m.BufferedReader = BytesIO
        m.BufferedWriter = BytesIO
        m.DEFAULT_BUFFER_SIZE = 8192
        m.SEEK_SET = 0
        m.SEEK_CUR = 1
        m.SEEK_END = 2
        _s.modules["io"] = m

    try:
        import io
        io.StringIO  # verify it's real
    except (ImportError, AttributeError):
        _register_io()

    # ---- os module ----
    def _register_os():
        import sys as _s
        m = type(_s)("os")
        m.__file__ = "<frozen os>"
        m.sep = "/"
        m.linesep = "\n"
        m.curdir = "."
        m.pardir = ".."
        m.devnull = "/dev/null"
        m.environ = {}
        m.name = "posix"

        m.getcwd = lambda: "/"
        m.getpid = lambda: 1
        m.getenv = lambda key, default=None: None
        m.cpu_count = lambda: 1
        m.urandom = lambda n: bytes(n)

        def _listdir(path="."):
            path = _normpath(path)
            if path not in _MEMFS_DIRS:
                if path in _MEMFS:
                    raise NotADirectoryError(
                        f"[Errno 20] Not a directory: '{path}'")
                raise FileNotFoundError(
                    f"[Errno 2] No such file or directory: '{path}'")
            prefix = path.rstrip("/") + "/"
            seen = set()
            for k in list(_MEMFS.keys()):
                if k.startswith(prefix):
                    rest = k[len(prefix):]
                    name = rest.split("/")[0]
                    seen.add(name)
            for d in list(_MEMFS_DIRS):
                if d.startswith(prefix) and d != path:
                    rest = d[len(prefix):]
                    name = rest.split("/")[0]
                    if name:
                        seen.add(name)
            return list(seen)

        def _remove(path):
            path = _normpath(path)
            if path not in _MEMFS:
                raise FileNotFoundError(
                    f"[Errno 2] No such file or directory: '{path}'")
            del _MEMFS[path]

        def _rmdir(path):
            path = _normpath(path)
            if path not in _MEMFS_DIRS:
                raise FileNotFoundError(
                    f"[Errno 2] No such file or directory: '{path}'")
            prefix = path.rstrip("/") + "/"
            for k in _MEMFS:
                if k.startswith(prefix):
                    raise OSError(
                        f"[Errno 39] Directory not empty: '{path}'")
            for d in _MEMFS_DIRS:
                if d.startswith(prefix):
                    raise OSError(
                        f"[Errno 39] Directory not empty: '{path}'")
            _MEMFS_DIRS.discard(path)

        def _rename(src, dst):
            src = _normpath(src)
            dst = _normpath(dst)
            if src not in _MEMFS:
                raise FileNotFoundError(
                    f"[Errno 2] No such file or directory: '{src}'")
            _MEMFS[dst] = _MEMFS.pop(src)

        def _stat(path):
            path = _normpath(path)
            if path in _MEMFS:
                class _stat_result:
                    st_mode = 0o100644
                    st_size = len(_MEMFS[path])
                    st_mtime = 0.0
                    st_atime = 0.0
                    st_ctime = 0.0
                return _stat_result()
            if path in _MEMFS_DIRS:
                class _stat_result:
                    st_mode = 0o040755
                    st_size = 0
                    st_mtime = 0.0
                    st_atime = 0.0
                    st_ctime = 0.0
                return _stat_result()
            raise FileNotFoundError(
                f"[Errno 2] No such file or directory: '{path}'")

        m.listdir = _listdir
        m.remove = _remove
        m.unlink = _remove
        m.rmdir = _rmdir
        m.rename = _rename
        m.stat = _stat
        m.makedirs = _makedirs

        def _mkdir(path, mode=0o777):
            path = _normpath(path)
            if path in _MEMFS_DIRS or path in _MEMFS:
                raise FileExistsError(
                    f"[Errno 17] File exists: '{path}'")
            parent = _dirname(path)
            if parent != "/" and parent not in _MEMFS_DIRS:
                raise FileNotFoundError(
                    f"[Errno 2] No such file or directory: '{path}'")
            _MEMFS_DIRS.add(path)

        m.mkdir = _mkdir

        # os.path submodule
        _ospath = type(_s)("os.path")
        _ospath.__file__ = "<frozen os.path>"

        def _exists(path):
            path = _normpath(path)
            return path in _MEMFS or path in _MEMFS_DIRS

        def _isfile(path):
            return _normpath(path) in _MEMFS

        def _isdir(path):
            return _normpath(path) in _MEMFS_DIRS

        def _splitext(path):
            base = _basename(path)
            idx = base.rfind(".")
            if idx <= 0:
                return (path, "")
            return (path[:-(len(base) - idx)], base[idx:])

        def _abspath(path):
            return _normpath(path)

        def _realpath(path, **kw):
            return _normpath(path)

        def _expanduser(path):
            if isinstance(path, str) and path.startswith("~"):
                return "/home" + path[1:]
            return path

        def _expandvars(path):
            return path

        def _relpath(path, start=None):
            return _normpath(path)

        _ospath.exists = _exists
        _ospath.isfile = _isfile
        _ospath.isdir = _isdir
        _ospath.join = _join
        _ospath.dirname = _dirname
        _ospath.basename = _basename
        _ospath.splitext = _splitext
        _ospath.abspath = _abspath
        _ospath.realpath = _realpath
        _ospath.expanduser = _expanduser
        _ospath.expandvars = _expandvars
        _ospath.relpath = _relpath
        _ospath.normpath = _normpath
        _ospath.normcase = lambda p: p  # POSIX: case-sensitive, no transformation
        _ospath.sep = "/"
        _ospath.curdir = "."
        _ospath.pardir = ".."
        _ospath.split = lambda p: (_dirname(p), _basename(p))
        _ospath.splitdrive = lambda p: ("", p)
        _ospath.getsize = lambda p: len(_MEMFS.get(_normpath(p), b""))

        m.path = _ospath
        _s.modules["os"] = m
        _s.modules["os.path"] = _ospath
        return m

    try:
        import os
        os.path.join  # verify it's real
    except (ImportError, AttributeError, NameError):
        _register_os()
    else:
        # os exists (real or prior stub) but may lack path operations;
        # always install the memfs-backed os.path so open/exists work
        _register_os()

    # ---- tempfile module ----
    def _register_tempfile():
        import sys as _s
        _counter = [0]

        def _mktemp(suffix="", prefix="tmp", dir="/tmp"):
            _makedirs(_normpath(dir), exist_ok=True)
            _counter[0] += 1
            name = _normpath(dir) + "/" + prefix + str(_counter[0]) + suffix
            return name

        class NamedTemporaryFile:
            def __init__(self, mode="w+b", buffering=-1, encoding=None,
                         suffix=None, prefix=None, dir=None, delete=True,
                         **kw):
                _dir = dir or "/tmp"
                _suffix = suffix or ""
                _prefix = prefix or "tmp"
                self.name = _mktemp(suffix=_suffix, prefix=_prefix, dir=_dir)
                binary = "b" in mode
                _makedirs(_normpath(_dir), exist_ok=True)
                self._file = _MemFile(self.name, mode, binary)
                self._delete = delete
            def read(self, *a):
                return self._file.read(*a)
            def write(self, *a):
                return self._file.write(*a)
            def seek(self, *a):
                return self._file.seek(*a)
            def tell(self):
                return self._file.tell()
            def flush(self):
                self._file.flush()
            def close(self):
                self._file.close()
                if self._delete and self.name in _MEMFS:
                    del _MEMFS[self.name]
            def __enter__(self):
                return self
            def __exit__(self, *a):
                self.close()

        def mkdtemp(suffix=None, prefix=None, dir=None):
            _dir = dir or "/tmp"
            _suffix = suffix or ""
            _prefix = prefix or "tmp"
            name = _mktemp(suffix=_suffix, prefix=_prefix, dir=_dir)
            _MEMFS_DIRS.add(name)
            return name

        def mkstemp(suffix=None, prefix=None, dir=None, text=False):
            _dir = dir or "/tmp"
            _suffix = suffix or ""
            _prefix = prefix or "tmp"
            name = _mktemp(suffix=_suffix, prefix=_prefix, dir=_dir)
            mode = "w+" if text else "w+b"
            _MEMFS[name] = b""
            return (None, name)

        def gettempdir():
            _makedirs("/tmp", exist_ok=True)
            return "/tmp"

        m = type(_s)("tempfile")
        m.__file__ = "<frozen tempfile>"
        m.NamedTemporaryFile = NamedTemporaryFile
        m.mkdtemp = mkdtemp
        m.mkstemp = mkstemp
        m.gettempdir = gettempdir
        m.tempdir = None
        _s.modules["tempfile"] = m

    try:
        import tempfile
        tempfile.gettempdir  # verify it's real
    except (ImportError, AttributeError):
        _register_tempfile()

    # ---- pathlib module ----
    def _register_pathlib():
        import sys as _s
        m = type(_s)("pathlib")
        m.__file__ = "<frozen pathlib>"

        class Path:
            def __init__(self, *parts):
                if not parts:
                    self._path = "/"
                else:
                    self._path = _join(*[str(p) for p in parts])

            def __str__(self):
                return self._path

            def __repr__(self):
                return f"Path('{self._path}')"

            def __eq__(self, other):
                return str(self) == str(other)

            def __hash__(self):
                return hash(self._path)

            def __truediv__(self, other):
                return Path(_join(self._path, str(other)))

            def __fspath__(self):
                return self._path

            @property
            def name(self):
                return _basename(self._path)

            @property
            def stem(self):
                n = self.name
                idx = n.rfind(".")
                return n[:idx] if idx > 0 else n

            @property
            def suffix(self):
                n = self.name
                idx = n.rfind(".")
                return n[idx:] if idx > 0 else ""

            @property
            def suffixes(self):
                n = self.name
                parts = n.split(".")
                return ["." + p for p in parts[1:]] if len(parts) > 1 else []

            @property
            def parent(self):
                return Path(_dirname(self._path))

            @property
            def parts(self):
                return tuple(["/"] + [p for p in self._path.lstrip("/").split("/") if p])

            def exists(self):
                return _normpath(self._path) in _MEMFS or _normpath(self._path) in _MEMFS_DIRS

            def is_file(self):
                return _normpath(self._path) in _MEMFS

            def is_dir(self):
                return _normpath(self._path) in _MEMFS_DIRS

            def read_text(self, encoding="utf-8", errors="strict"):
                with _memfs_open(self._path, "r") as f:
                    return f.read()

            def read_bytes(self):
                with _memfs_open(self._path, "rb") as f:
                    return f.read()

            def write_text(self, data, encoding="utf-8", errors="strict"):
                with _memfs_open(self._path, "w") as f:
                    f.write(data)
                return len(data)

            def write_bytes(self, data):
                with _memfs_open(self._path, "wb") as f:
                    f.write(data)
                return len(data)

            def mkdir(self, mode=0o777, parents=False, exist_ok=False):
                path = _normpath(self._path)
                if path in _MEMFS_DIRS:
                    if not exist_ok:
                        raise FileExistsError(
                            f"[Errno 17] File exists: '{path}'")
                    return
                if parents:
                    _makedirs(path, exist_ok=exist_ok)
                else:
                    # Verify parent exists before creating
                    parent = _dirname(path)
                    if parent != "/" and parent not in _MEMFS_DIRS:
                        raise FileNotFoundError(
                            f"[Errno 2] No such file or directory: '{path}'")
                    if path in _MEMFS:
                        raise FileExistsError(
                            f"[Errno 17] File exists: '{path}'")
                    _MEMFS_DIRS.add(path)

            def unlink(self, missing_ok=False):
                path = _normpath(self._path)
                if path not in _MEMFS:
                    if not missing_ok:
                        raise FileNotFoundError(
                            f"[Errno 2] No such file or directory: '{path}'")
                    return
                del _MEMFS[path]

            def rmdir(self):
                path = _normpath(self._path)
                if path not in _MEMFS_DIRS:
                    raise FileNotFoundError(
                        f"[Errno 2] No such file or directory: '{path}'")
                prefix = path.rstrip("/") + "/"
                for k in _MEMFS:
                    if k.startswith(prefix):
                        raise OSError(
                            f"[Errno 39] Directory not empty: '{path}'")
                for d in _MEMFS_DIRS:
                    if d.startswith(prefix):
                        raise OSError(
                            f"[Errno 39] Directory not empty: '{path}'")
                _MEMFS_DIRS.discard(path)

            def iterdir(self):
                path = _normpath(self._path)
                if path not in _MEMFS_DIRS:
                    raise NotADirectoryError(
                        f"[Errno 20] Not a directory: '{path}'")
                prefix = path.rstrip("/") + "/"
                seen = set()
                for k in list(_MEMFS.keys()):
                    if k.startswith(prefix):
                        rest = k[len(prefix):]
                        name = rest.split("/")[0]
                        seen.add(name)
                for d in list(_MEMFS_DIRS):
                    if d.startswith(prefix) and d != path:
                        rest = d[len(prefix):]
                        name = rest.split("/")[0]
                        if name:
                            seen.add(name)
                return iter([Path(_join(path, name)) for name in seen])

            def open(self, mode="r", buffering=-1, encoding=None,
                     errors=None, newline=None):
                return _memfs_open(self._path, mode)

            def stat(self):
                import os as _o
                return _o.stat(self._path)

            def rename(self, target):
                src = _normpath(self._path)
                dst = _normpath(str(target))
                if src in _MEMFS:
                    _MEMFS[dst] = _MEMFS.pop(src)
                elif src in _MEMFS_DIRS:
                    _MEMFS_DIRS.discard(src)
                    _MEMFS_DIRS.add(dst)
                else:
                    raise FileNotFoundError(
                        f"[Errno 2] No such file or directory: '{src}'")
                return Path(dst)

            def with_name(self, name):
                return Path(_join(_dirname(self._path), name))

            def with_suffix(self, suffix):
                stem = self.stem
                return self.parent / (stem + suffix)

            def resolve(self):
                return Path(_normpath(self._path))

            def absolute(self):
                return self.resolve()

            def relative_to(self, other):
                other_str = _normpath(str(other))
                self_str = _normpath(self._path)
                if not self_str.startswith(other_str):
                    raise ValueError(
                        f"'{self_str}' is not relative to '{other_str}'")
                rel = self_str[len(other_str):].lstrip("/")
                return Path(rel) if rel else Path(".")

            def glob(self, pattern):
                import fnmatch as _fnmatch
                path = _normpath(self._path)
                prefix = path.rstrip("/") + "/"
                results = []
                full_pattern = prefix + pattern
                for k in list(_MEMFS.keys()) + [d for d in _MEMFS_DIRS if d != "/"]:
                    if k.startswith(prefix) and _fnmatch.fnmatch(k, full_pattern):
                        results.append(Path(k))
                return iter(results)

        class PurePosixPath(Path):
            pass

        class PureWindowsPath(Path):
            pass

        class PosixPath(Path):
            pass

        class WindowsPath(Path):
            pass

        m.Path = Path
        m.PurePosixPath = PurePosixPath
        m.PureWindowsPath = PureWindowsPath
        m.PosixPath = PosixPath
        m.WindowsPath = WindowsPath
        _s.modules["pathlib"] = m

    try:
        import pathlib
        pathlib.Path  # verify it's real
    except (ImportError, AttributeError):
        _register_pathlib()

_install_memfs()
del _install_memfs


# --- frozen stdlib: random module (pure Python, no C extensions) ---
# The CPython canister template seeds Python's random module with IC consensus
# randomness (raw_rand) at init. On WASI there is no filesystem so stdlib
# `random` isn't importable. This provides a minimal pure-Python implementation.

def _register_random():
    # Mersenne Twister constants
    _N = 624
    _M = 397
    _MATRIX_A = 0x9908b0df
    _UPPER_MASK = 0x80000000
    _LOWER_MASK = 0x7fffffff

    class Random:
        def __init__(self, x=None):
            self._mt = [0] * _N
            self._mti = _N + 1
            if x is not None:
                self.seed(x)
            else:
                self.seed(0)

        def seed(self, a=None):
            if a is None:
                a = 0
            if isinstance(a, (bytes, bytearray)):
                # Convert bytes to integer (big-endian)
                a = int.from_bytes(a, 'big')
            if isinstance(a, float):
                a = int(a)
            a = abs(a)
            self._mt[0] = a & 0xffffffff
            for i in range(1, _N):
                self._mt[i] = (1812433253 * (self._mt[i - 1] ^ (self._mt[i - 1] >> 30)) + i) & 0xffffffff
            self._mti = _N

        def _generate(self):
            mag01 = [0, _MATRIX_A]
            for kk in range(_N - _M):
                y = (self._mt[kk] & _UPPER_MASK) | (self._mt[kk + 1] & _LOWER_MASK)
                self._mt[kk] = self._mt[kk + _M] ^ (y >> 1) ^ mag01[y & 1]
            for kk in range(_N - _M, _N - 1):
                y = (self._mt[kk] & _UPPER_MASK) | (self._mt[kk + 1] & _LOWER_MASK)
                self._mt[kk] = self._mt[kk + (_M - _N)] ^ (y >> 1) ^ mag01[y & 1]
            y = (self._mt[_N - 1] & _UPPER_MASK) | (self._mt[0] & _LOWER_MASK)
            self._mt[_N - 1] = self._mt[_M - 1] ^ (y >> 1) ^ mag01[y & 1]
            self._mti = 0

        def _genrand_int32(self):
            if self._mti >= _N:
                self._generate()
            y = self._mt[self._mti]
            self._mti += 1
            y ^= (y >> 11)
            y ^= (y << 7) & 0x9d2c5680
            y ^= (y << 15) & 0xefc60000
            y ^= (y >> 18)
            return y

        def random(self):
            a = self._genrand_int32() >> 5
            b = self._genrand_int32() >> 6
            return (a * 67108864.0 + b) * (1.0 / 9007199254740992.0)

        def randint(self, a, b):
            return a + int(self.random() * (b - a + 1))

        def randrange(self, start, stop=None, step=1):
            if stop is None:
                return int(self.random() * start)
            return start + step * int(self.random() * ((stop - start + step - 1) // step))

        def choice(self, seq):
            return seq[int(self.random() * len(seq))]

        def shuffle(self, x):
            for i in range(len(x) - 1, 0, -1):
                j = int(self.random() * (i + 1))
                x[i], x[j] = x[j], x[i]

        def sample(self, population, k):
            pool = list(population)
            n = len(pool)
            result = []
            for i in range(k):
                j = int(self.random() * (n - i))
                result.append(pool[j])
                pool[j] = pool[n - i - 1]
            return result

        def uniform(self, a, b):
            return a + (b - a) * self.random()

        def getrandbits(self, k):
            if k <= 0:
                raise ValueError("number of bits must be greater than zero")
            numbytes = (k + 7) // 8
            x = int.from_bytes(bytes([self._genrand_int32() & 0xff for _ in range(numbytes)]), 'big')
            return x >> (numbytes * 8 - k)

    _inst = Random()

    m = type(_sys)("random")
    m.__file__ = "<frozen random>"
    m.Random = Random
    m.seed = _inst.seed
    m.random = _inst.random
    m.randint = _inst.randint
    m.randrange = _inst.randrange
    m.choice = _inst.choice
    m.shuffle = _inst.shuffle
    m.sample = _inst.sample
    m.uniform = _inst.uniform
    m.getrandbits = _inst.getrandbits
    _sys.modules["random"] = m

try:
    import random
except ImportError:
    _register_random()
del _register_random


# --- frozen stdlib: time module ---
def _register_time():
    def _time():
        return 0.0
    def _sleep(secs):
        pass
    def _monotonic():
        return 0.0
    m = type(_sys)("time")
    m.__file__ = "<frozen time>"
    m.time = _time
    m.sleep = _sleep
    m.monotonic = _monotonic
    m.perf_counter = _monotonic
    m.time_ns = lambda: 0
    _sys.modules["time"] = m

try:
    import time
except ImportError:
    _register_time()
del _register_time


# --- frozen stdlib: datetime module ---
def _register_datetime():
    class timedelta:
        def __init__(self, days=0, seconds=0, microseconds=0,
                     milliseconds=0, minutes=0, hours=0, weeks=0):
            total = (days * 86400 + hours * 3600 + minutes * 60 + seconds
                     + milliseconds / 1000 + microseconds / 1000000 + weeks * 604800)
            self._total_seconds = total
        def total_seconds(self):
            return self._total_seconds
        def __repr__(self):
            return f"timedelta(seconds={self._total_seconds})"

    class datetime:
        def __init__(self, year=1970, month=1, day=1, hour=0, minute=0,
                     second=0, microsecond=0):
            self.year = year; self.month = month; self.day = day
            self.hour = hour; self.minute = minute; self.second = second
            self.microsecond = microsecond
        @staticmethod
        def now():
            return datetime()
        @staticmethod
        def fromtimestamp(ts):
            d = datetime()
            d._ts = ts
            return d
        @staticmethod
        def fromisoformat(s):
            # Parse "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS" (minimal)
            s = s.replace('T', ' ').replace('Z', '')
            parts = s.split(' ')
            date_part = parts[0].split('-')
            yr = int(date_part[0])
            mo = int(date_part[1]) if len(date_part) > 1 else 1
            dy = int(date_part[2]) if len(date_part) > 2 else 1
            hr = mi = se = us = 0
            if len(parts) > 1:
                time_parts = parts[1].split(':')
                hr = int(time_parts[0]) if len(time_parts) > 0 else 0
                mi = int(time_parts[1]) if len(time_parts) > 1 else 0
                if len(time_parts) > 2:
                    sec_parts = time_parts[2].split('.')
                    se = int(sec_parts[0])
                    if len(sec_parts) > 1:
                        frac = sec_parts[1][:6].ljust(6, '0')
                        us = int(frac)
            return datetime(yr, mo, dy, hr, mi, se, us)
        def strftime(self, fmt):
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d} {self.hour:02d}:{self.minute:02d}:{self.second:02d}.{self.microsecond:06d}"
        def isoformat(self, sep='T'):
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}{sep}{self.hour:02d}:{self.minute:02d}:{self.second:02d}"
        def weekday(self):
            # Zeller-like day-of-week (Mon=0 .. Sun=6)
            y, m, d = self.year, self.month, self.day
            if m < 3:
                m += 12; y -= 1
            return (d + (13*(m+1))//5 + y + y//4 - y//100 + y//400 + 5) % 7
        def timestamp(self):
            # Convert to POSIX timestamp (seconds since 1970-01-01 UTC)
            # Days from year 1 to year y
            y, m, d = self.year, self.month, self.day
            # Days in each month (non-leap)
            _mdays = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            def _is_leap(yr):
                return yr % 4 == 0 and (yr % 100 != 0 or yr % 400 == 0)
            # Days from epoch (1970-01-01) to this date
            days = 0
            for yr in range(1970, y):
                days += 366 if _is_leap(yr) else 365
            for mo in range(1, m):
                days += _mdays[mo]
                if mo == 2 and _is_leap(y):
                    days += 1
            days += d - 1
            return days * 86400 + self.hour * 3600 + self.minute * 60 + self.second + self.microsecond / 1e6
        def utcoffset(self):
            return None
        @property
        def tzinfo(self):
            return None
        def date(self):
            return self
        def __repr__(self):
            return self.strftime("%Y-%m-%d %H:%M:%S.%f")
        def __sub__(self, other):
            if isinstance(other, datetime):
                return timedelta(days=0)
            return NotImplemented
        def __add__(self, other):
            if isinstance(other, timedelta):
                return self
            return NotImplemented

    m = type(_sys)("datetime")
    m.__file__ = "<frozen datetime>"
    m.datetime = datetime
    m.timedelta = timedelta
    _sys.modules["datetime"] = m

try:
    import datetime
except ImportError:
    _register_datetime()
del _register_datetime


# --- frozen stdlib: itertools module ---
def _register_itertools():
    def permutations(iterable, r=None):
        pool = tuple(iterable)
        n = len(pool)
        r = n if r is None else r
        if r > n:
            return
        indices = list(range(n))
        cycles = list(range(n, n - r, -1))
        yield tuple(pool[i] for i in indices[:r])
        while n:
            found = False
            for i in reversed(range(r)):
                cycles[i] -= 1
                if cycles[i] == 0:
                    indices[i:] = indices[i+1:] + indices[i:i+1]
                    cycles[i] = n - i
                else:
                    j = cycles[i]
                    indices[i], indices[-j] = indices[-j], indices[i]
                    yield tuple(pool[i] for i in indices[:r])
                    found = True
                    break
            if not found:
                return

    def combinations(iterable, r):
        pool = tuple(iterable)
        n = len(pool)
        if r > n:
            return
        indices = list(range(r))
        yield tuple(pool[i] for i in indices)
        while True:
            found = False
            for i in reversed(range(r)):
                if indices[i] != i + n - r:
                    found = True
                    break
            if not found:
                return
            indices[i] += 1
            for j in range(i + 1, r):
                indices[j] = indices[j - 1] + 1
            yield tuple(pool[i] for i in indices)

    def product(*iterables, repeat=1):
        pools = [tuple(p) for p in iterables] * repeat
        result = [[]]
        for pool in pools:
            result = [x + [y] for x in result for y in pool]
        for prod in result:
            yield tuple(prod)

    def chain(*iterables):
        for it in iterables:
            yield from it

    def chain_from_iterable(iterables):
        for it in iterables:
            yield from it

    def islice(iterable, *args):
        s = slice(*args)
        start = s.start or 0
        stop = s.stop
        step = s.step or 1
        i = 0
        nexti = start
        for element in iterable:
            if i == nexti:
                yield element
                nexti += step
            if stop is not None and nexti >= stop:
                break
            i += 1

    def count(start=0, step=1):
        n = start
        while True:
            yield n
            n += step

    def cycle(iterable):
        saved = []
        for element in iterable:
            yield element
            saved.append(element)
        while saved:
            for element in saved:
                yield element

    def repeat(obj, times=None):
        if times is None:
            while True:
                yield obj
        else:
            for _ in range(times):
                yield obj

    def accumulate(iterable, func=None, initial=None):
        it = iter(iterable)
        total = initial
        if initial is None:
            try:
                total = next(it)
            except StopIteration:
                return
        yield total
        for element in it:
            total = func(total, element) if func else total + element
            yield total

    m = type(_sys)("itertools")
    m.__file__ = "<frozen itertools>"
    m.permutations = permutations
    m.combinations = combinations
    m.product = product
    m.chain = chain
    m.chain.from_iterable = chain_from_iterable
    m.islice = islice
    m.count = count
    m.cycle = cycle
    m.repeat = repeat
    m.accumulate = accumulate
    _sys.modules["itertools"] = m

try:
    import itertools
    if not hasattr(itertools, 'permutations'):
        raise ImportError
except ImportError:
    _register_itertools()
del _register_itertools


# --- frozen stdlib: typing module ---
def _register_typing():
    m = type(_sys)("typing")
    m.__file__ = "<frozen typing>"
    # Subscriptable stub: T[X] returns T, so Optional[str] works etc.
    class _TypingStub:
        def __class_getitem__(cls, params):
            return cls
        def __init_subclass__(cls, **kw):
            pass
    class _CallableStub(_TypingStub):
        pass
    # All typing constructs are no-ops at runtime
    m.Any = _TypingStub
    m.Union = _TypingStub
    m.Optional = _TypingStub
    m.List = list
    m.Dict = dict
    m.Set = set
    m.Tuple = tuple
    m.Type = type
    m.Callable = _CallableStub
    m.Iterator = _TypingStub
    m.Generator = _TypingStub
    m.Iterable = _TypingStub
    m.Sequence = _TypingStub
    m.Mapping = _TypingStub
    m.MutableMapping = _TypingStub
    m.MutableSequence = _TypingStub
    m.MutableSet = _TypingStub
    m.Deque = _TypingStub
    m.FrozenSet = frozenset
    m.Counter = _TypingStub
    m.OrderedDict = _TypingStub
    m.DefaultDict = _TypingStub
    m.NamedTuple = _TypingStub
    m.IO = _TypingStub
    m.TextIO = _TypingStub
    m.BinaryIO = _TypingStub
    m.Pattern = _TypingStub
    m.Match = _TypingStub
    m.AnyStr = _TypingStub
    m.SupportsInt = _TypingStub
    m.SupportsFloat = _TypingStub
    m.SupportsComplex = _TypingStub
    m.SupportsBytes = _TypingStub
    m.SupportsAbs = _TypingStub
    m.SupportsRound = _TypingStub
    m.ClassVar = _TypingStub
    m.Final = _TypingStub
    m.Literal = _TypingStub
    m.Annotated = _TypingStub
    m.TypeAlias = _TypingStub
    m.NoReturn = _TypingStub
    m.TYPE_CHECKING = False
    class _TypeVar(_TypingStub):
        def __init__(self, name, *a, **kw):
            self.__name__ = name
    m.TypeVar = _TypeVar
    m.ParamSpec = _TypeVar
    m.Generic = _TypingStub
    m.Protocol = _TypingStub
    m.TypedDict = type
    m.overload = lambda f: f
    m.cast = lambda t, v: v
    m.no_type_check = lambda f: f
    m.runtime_checkable = lambda cls: cls
    m.get_type_hints = lambda obj, **kw: {}
    m.dataclass_transform = lambda **kw: lambda cls: cls
    _sys.modules["typing"] = m

try:
    import typing
except ImportError:
    _register_typing()
del _register_typing


# --- frozen stdlib: abc module ---
def _register_abc():
    def abstractmethod(f):
        return f
    class ABCMeta(type):
        pass
    class ABC(metaclass=ABCMeta):
        pass
    m = type(_sys)("abc")
    m.__file__ = "<frozen abc>"
    m.ABC = ABC
    m.ABCMeta = ABCMeta
    m.abstractmethod = abstractmethod
    _sys.modules["abc"] = m

try:
    import abc
except ImportError:
    _register_abc()
del _register_abc


# --- frozen stdlib: weakref module ---
def _register_weakref():
    class WeakValueDictionary(dict):
        """Stub: acts as a regular dict (no weak references in WASI)."""
        pass
    class WeakSet(set):
        pass
    def ref(obj, callback=None):
        return lambda: obj
    m = type(_sys)("weakref")
    m.__file__ = "<frozen weakref>"
    m.WeakValueDictionary = WeakValueDictionary
    m.WeakSet = WeakSet
    m.ref = ref
    _sys.modules["weakref"] = m

try:
    import weakref
except ImportError:
    _register_weakref()
del _register_weakref


# --- frozen stdlib: enum module ---
def _register_enum():
    class EnumMeta(type):
        def __new__(mcs, name, bases, namespace):
            cls = super().__new__(mcs, name, bases, namespace)
            return cls
        def __iter__(cls):
            return iter([])
    class Enum(metaclass=EnumMeta):
        pass
    class IntEnum(int, Enum):
        pass
    m = type(_sys)("enum")
    m.__file__ = "<frozen enum>"
    m.Enum = Enum
    m.IntEnum = IntEnum
    m.EnumMeta = EnumMeta
    m.unique = lambda cls: cls
    m.auto = lambda: 0
    _sys.modules["enum"] = m

try:
    import enum
except ImportError:
    _register_enum()
del _register_enum


# --- frozen stdlib: collections module ---
def _register_collections():
    class _deque(list):
        """Stub deque backed by list (no maxlen enforcement in WASI)."""
        def __init__(self, iterable=(), maxlen=None):
            super().__init__(iterable)
            self.maxlen = maxlen
        def appendleft(self, x):
            self.insert(0, x)
        def extendleft(self, iterable):
            for x in iterable:
                self.insert(0, x)
        def popleft(self):
            return self.pop(0)
        def rotate(self, n=1):
            pass
    class _defaultdict(dict):
        def __init__(self, default_factory=None, *a, **kw):
            super().__init__(*a, **kw)
            self.default_factory = default_factory
        def __missing__(self, key):
            if self.default_factory is None:
                raise KeyError(key)
            self[key] = self.default_factory()
            return self[key]
    m = type(_sys)("collections")
    m.__file__ = "<frozen collections>"
    m.deque = _deque
    m.OrderedDict = dict
    m.defaultdict = _defaultdict
    class _Counter(dict):
        """Minimal Counter implementation for WASI."""
        def __init__(self, iterable=None, **kwargs):
            super().__init__()
            if iterable is not None:
                if isinstance(iterable, dict):
                    self.update(iterable)
                else:
                    for item in iterable:
                        self[item] = self.get(item, 0) + 1
            if kwargs:
                self.update(kwargs)
        def most_common(self, n=None):
            items = sorted(self.items(), key=lambda x: x[1], reverse=True)
            if n is not None:
                return items[:n]
            return items
        def elements(self):
            for k, v in self.items():
                for _ in range(v):
                    yield k
        def subtract(self, iterable=None, **kwargs):
            if isinstance(iterable, dict):
                for k, v in iterable.items():
                    self[k] = self.get(k, 0) - v
            elif iterable is not None:
                for item in iterable:
                    self[item] = self.get(item, 0) - 1
            for k, v in kwargs.items():
                self[k] = self.get(k, 0) - v
        def __missing__(self, key):
            return 0
        def __add__(self, other):
            result = _Counter()
            for k in set(self) | set(other):
                val = self[k] + other[k]
                if val > 0:
                    result[k] = val
            return result
    m.Counter = _Counter
    def _namedtuple(name, fields, **kw):
        if isinstance(fields, str):
            fields = fields.replace(',', ' ').split()
        fields = list(fields)
        def _new(cls, *args, **kwargs):
            if kwargs:
                args = list(args)
                for i, f in enumerate(fields):
                    if f in kwargs and i >= len(args):
                        args.append(kwargs[f])
                args = tuple(args)
            return tuple.__new__(cls, args)
        ns = {'__new__': _new, '_fields': tuple(fields), '__slots__': ()}
        for i, f in enumerate(fields):
            ns[f] = property(lambda self, _i=i: self[_i])
        def _repr(self):
            pairs = ', '.join(f'{f}={self[i]!r}' for i, f in enumerate(fields))
            return f'{name}({pairs})'
        ns['__repr__'] = _repr
        ns['_asdict'] = lambda self: dict(zip(fields, self))
        ns['_replace'] = lambda self, **kw: type(self)(*[kw.get(f, self[i]) for i, f in enumerate(fields)])
        return type(name, (tuple,), ns)
    m.namedtuple = _namedtuple
    m.ChainMap = dict
    _sys.modules["collections"] = m

try:
    import collections
    collections.deque  # verify it's real
except (ImportError, AttributeError):
    _register_collections()
del _register_collections


# --- frozen stdlib: dataclasses module ---
def _register_dataclasses():
    _MISSING = object()
    _FIELD_TAG = '__dataclass_fields__'

    class Field:
        __slots__ = ('name', 'type', 'default', 'default_factory', 'repr', 'init', 'compare', 'hash', 'metadata')
        def __init__(self, default=_MISSING, default_factory=_MISSING, repr=True,
                     init=True, compare=True, hash=None, metadata=None):
            self.name = None
            self.type = None
            self.default = default
            self.default_factory = default_factory
            self.repr = repr
            self.init = init
            self.compare = compare
            self.hash = hash
            self.metadata = metadata or {}

    def field(default=_MISSING, default_factory=_MISSING, repr=True,
              init=True, compare=True, hash=None, metadata=None):
        return Field(default=default, default_factory=default_factory, repr=repr,
                     init=init, compare=compare, hash=hash, metadata=metadata)

    def _process_class(cls, init, repr_, eq, order, frozen):
        all_fields = {}
        for base in reversed(cls.__mro__):
            if base is object:
                continue
            ann = base.__dict__.get('__annotations__', {})
            for name, tp in ann.items():
                if name.startswith('_'):
                    continue
                f = cls.__dict__.get(name, _MISSING)
                if isinstance(f, Field):
                    f.name = name
                    f.type = tp
                    all_fields[name] = f
                else:
                    fld = Field()
                    fld.name = name
                    fld.type = tp
                    if f is not _MISSING:
                        fld.default = f
                    all_fields[name] = fld

        setattr(cls, _FIELD_TAG, all_fields)

        if init and '__init__' not in cls.__dict__:
            fields_no_default = []
            fields_with_default = []
            for fld in all_fields.values():
                if not fld.init:
                    continue
                if fld.default is not _MISSING or fld.default_factory is not _MISSING:
                    fields_with_default.append(fld)
                else:
                    fields_no_default.append(fld)
            ordered_fields = fields_no_default + fields_with_default

            args = ['self']
            body_lines = []
            globs = {'_MISSING': _MISSING}
            for fld in ordered_fields:
                if fld.default is not _MISSING:
                    default_name = f'_dflt_{fld.name}'
                    globs[default_name] = fld.default
                    args.append(f'{fld.name}={default_name}')
                elif fld.default_factory is not _MISSING:
                    factory_name = f'_factory_{fld.name}'
                    globs[factory_name] = fld.default_factory
                    args.append(f'{fld.name}=_MISSING')
                    body_lines.append(f'  if {fld.name} is _MISSING: {fld.name} = {factory_name}()')
                else:
                    args.append(fld.name)
                if frozen:
                    body_lines.append(f'  object.__setattr__(self, {fld.name!r}, {fld.name})')
                else:
                    body_lines.append(f'  self.{fld.name} = {fld.name}')

            if not body_lines:
                body_lines.append('  pass')
            func_def = f"def __init__({', '.join(args)}):\n" + '\n'.join(body_lines)
            ns = {}
            exec(func_def, globs, ns)
            cls.__init__ = ns['__init__']

        if repr_ and '__repr__' not in cls.__dict__:
            repr_fields = [fld for fld in all_fields.values() if fld.repr]
            def __repr__(self, _fields=repr_fields, _cls_name=cls.__name__):
                parts = ', '.join(f'{f.name}={getattr(self, f.name)!r}' for f in _fields)
                return f'{_cls_name}({parts})'
            cls.__repr__ = __repr__

        if eq and '__eq__' not in cls.__dict__:
            cmp_fields = [fld for fld in all_fields.values() if fld.compare]
            def __eq__(self, other, _fields=cmp_fields):
                if self.__class__ is not other.__class__:
                    return NotImplemented
                return all(getattr(self, f.name) == getattr(other, f.name) for f in _fields)
            cls.__eq__ = __eq__

        if frozen:
            def __setattr__(self, name, value):
                raise FrozenInstanceError('cannot assign to field ' + name)
            def __delattr__(self, name):
                raise FrozenInstanceError('cannot delete field ' + name)
            cls.__setattr__ = __setattr__
            cls.__delattr__ = __delattr__

        for name in all_fields:
            if name in cls.__dict__ and not isinstance(cls.__dict__[name], (classmethod, staticmethod, property)):
                try:
                    delattr(cls, name)
                except (AttributeError, TypeError):
                    pass

        cls.__dataclass_params__ = {'init': init, 'repr': repr_, 'eq': eq, 'order': order, 'frozen': frozen}
        return cls

    def dataclass(cls=None, /, *, init=True, repr=True, eq=True,
                  order=False, unsafe_hash=False, frozen=False, **kw):
        def wrap(cls):
            return _process_class(cls, init=init, repr_=repr, eq=eq, order=order, frozen=frozen)
        if cls is None:
            return wrap
        return wrap(cls)

    def fields(cls_or_instance):
        f = getattr(cls_or_instance, _FIELD_TAG, None)
        if f is None:
            cls = cls_or_instance if isinstance(cls_or_instance, type) else type(cls_or_instance)
            f = getattr(cls, _FIELD_TAG, {})
        return list(f.values())

    def asdict(obj):
        result = {}
        for fld in fields(obj):
            val = getattr(obj, fld.name)
            if hasattr(val, '__dataclass_fields__'):
                val = asdict(val)
            elif isinstance(val, list):
                val = [asdict(v) if hasattr(v, '__dataclass_fields__') else v for v in val]
            elif isinstance(val, dict):
                val = {k: asdict(v) if hasattr(v, '__dataclass_fields__') else v for k, v in val.items()}
            result[fld.name] = val
        return result

    def astuple(obj):
        return tuple(getattr(obj, fld.name) for fld in fields(obj))

    def _replace(obj, **changes):
        d = {fld.name: getattr(obj, fld.name) for fld in fields(obj)}
        d.update(changes)
        return type(obj)(**d)

    def is_dataclass(obj):
        cls = obj if isinstance(obj, type) else type(obj)
        return hasattr(cls, _FIELD_TAG)

    FrozenInstanceError = type('FrozenInstanceError', (AttributeError,), {})

    m = type(_sys)("dataclasses")
    m.__file__ = "<frozen dataclasses>"
    m.dataclass = dataclass
    m.field = field
    m.Field = Field
    m.fields = fields
    m.asdict = asdict
    m.astuple = astuple
    m.replace = _replace
    m.is_dataclass = is_dataclass
    m.FrozenInstanceError = FrozenInstanceError
    m.MISSING = _MISSING
    _sys.modules["dataclasses"] = m

try:
    import dataclasses
    dataclasses.dataclass  # verify it's real
except (ImportError, AttributeError):
    _register_dataclasses()
del _register_dataclasses


# --- frozen stdlib: functools module ---
def _register_functools():
    def lru_cache(maxsize=128, typed=False):
        def decorator(f):
            return f
        if callable(maxsize):
            return maxsize
        return decorator
    m = type(_sys)("functools")
    m.__file__ = "<frozen functools>"
    m.lru_cache = lru_cache
    m.wraps = lambda f: lambda g: g
    m.partial = lambda f, *a, **kw: lambda *a2, **kw2: f(*a, *a2, **{**kw, **kw2})
    m.reduce = lambda f, it, *init: None
    m.cache = lru_cache
    m.cached_property = property
    m.total_ordering = lambda cls: cls
    m.singledispatch = lambda f: f
    _sys.modules["functools"] = m

try:
    import functools
    functools.wraps  # verify it's real
except (ImportError, AttributeError):
    _register_functools()
del _register_functools


# --- frozen stdlib: os / os.path module ---
# os.py crashes in WASI because it tries to import posix/nt C extensions.
# Register a stub BEFORE _wasi_safe_import so the real os.py never loads.
#
# The enhanced posix C stub (cpython_config.c) provides real filesystem
# operations via ic-wasi-polyfill: stat, mkdir, rmdir, rename, unlink, etc.
# We forward these to the os module and build os.path on top of os.stat.
def _register_os():
    _os = _sys.modules.get('os')
    if _os is None or not hasattr(_os, 'path') or not hasattr(getattr(_os, 'path', None) or _os, 'exists'):
        if _os is None:
            _os = type(_sys)('os')
            _os.__file__ = '<frozen os>'
            _os.__path__ = []
            _os.__package__ = 'os'
            _sys.modules['os'] = _os

        # Forward all public functions from the posix C module to os
        try:
            import posix as _posix
            for _name in dir(_posix):
                if not _name.startswith('_') and not hasattr(_os, _name):
                    setattr(_os, _name, getattr(_posix, _name))
        except ImportError:
            pass

        # Build os.path with real stat-based functions when posix.stat is available
        _has_stat = hasattr(_os, 'stat')

        class _Path:
            sep = '/'
            def join(self, *a): return '/'.join(a)
            def dirname(self, p): return p.rsplit('/', 1)[0] if '/' in p else ''
            def basename(self, p): return p.rsplit('/', 1)[-1]
            def abspath(self, p): return p
            def expanduser(self, p): return p
            def normpath(self, p): return p
            def realpath(self, p): return p
            def splitext(self, p):
                i = p.rfind('.')
                return (p[:i], p[i:]) if i > 0 else (p, '')
            def split(self, p):
                i = p.rfind('/')
                if i < 0:
                    return ('', p)
                return (p[:i] or '/', p[i+1:])

        if _has_stat:
            import stat as _stat_mod
            def _exists(p):
                try:
                    _os.stat(p)
                    return True
                except OSError:
                    return False
            def _isdir(p):
                try:
                    return _stat_mod.S_ISDIR(_os.stat(p).st_mode)
                except OSError:
                    return False
            def _isfile(p):
                try:
                    return _stat_mod.S_ISREG(_os.stat(p).st_mode)
                except OSError:
                    return False
            _Path.exists = staticmethod(_exists)
            _Path.isdir = staticmethod(_isdir)
            _Path.isfile = staticmethod(_isfile)
        else:
            def _exists(p): return False
            def _isdir(p): return False
            def _isfile(p): return False
            _Path.exists = staticmethod(_exists)
            _Path.isdir = staticmethod(_isdir)
            _Path.isfile = staticmethod(_isfile)

        _os.path = _Path()

        if not hasattr(_os, 'sep'):
            _os.sep = '/'
        if not hasattr(_os, 'getcwd'):
            _os.getcwd = lambda: '/'
        if not hasattr(_os, 'environ'):
            _os.environ = {}
        if not hasattr(_os, 'listdir'):
            _os.listdir = lambda p='/': []
        if not hasattr(_os, 'remove'):
            _os.remove = lambda p: None
        if not hasattr(_os, 'urandom'):
            import random as _rnd
            _os.urandom = lambda n: bytes(_rnd.getrandbits(8) for _ in range(n))

        # Real makedirs using os.mkdir + os.path.exists
        if hasattr(_os, 'mkdir'):
            def _makedirs(name, mode=0o777, exist_ok=False):
                head, tail = _os.path.split(name)
                if not tail:
                    head, tail = _os.path.split(head)
                if head and tail and not _os.path.exists(head):
                    try:
                        _makedirs(head, mode, exist_ok)
                    except FileExistsError:
                        pass
                try:
                    _os.mkdir(name, mode)
                except OSError:
                    if not exist_ok or not _os.path.isdir(name):
                        raise
            _os.makedirs = _makedirs
        elif not hasattr(_os, 'makedirs'):
            _os.makedirs = lambda p, mode=0o777, exist_ok=False: None

_register_os()
del _register_os
# Also register os.path as its own module entry
if 'os' in _sys.modules and hasattr(_sys.modules['os'], 'path'):
    _sys.modules['os.path'] = _sys.modules['os'].path


# --- frozen stdlib: traceback module ---
def _register_traceback():
    def _format_exc(limit=None, chain=True):
        ei = _sys.exc_info()
        if ei[1] is None:
            return ''
        parts = [f'{type(ei[1]).__name__}: {ei[1]}']
        tb = ei[2]
        frames = []
        while tb:
            f = tb.tb_frame
            frames.append(f'  File "{f.f_code.co_filename}", line {tb.tb_lineno}, in {f.f_code.co_name}')
            tb = tb.tb_next
        if frames:
            parts.insert(0, 'Traceback (most recent call last):')
            for fr in frames:
                parts.insert(-1, fr)
        return '\n'.join(parts)

    m = type(_sys)("traceback")
    m.__file__ = "<frozen traceback>"
    m.format_exc = _format_exc
    m.format_exception = lambda tp, val, tb, **kw: [_format_exc()]
    m.print_exc = lambda **kw: print(_format_exc())
    _sys.modules["traceback"] = m

try:
    import traceback
    traceback.format_exc  # verify it's real
except (ImportError, AttributeError):
    _register_traceback()
del _register_traceback


# --- frozen stdlib: uuid module ---
def _register_uuid():
    import random as _rnd

    class UUID:
        __slots__ = ('int',)
        def __init__(self, hex=None, int=None):
            if int is not None:
                object.__setattr__(self, 'int', int)
            elif hex is not None:
                object.__setattr__(self, 'int', _builtins.int(hex.replace('-', ''), 16) if isinstance(hex, str) else 0)
            else:
                object.__setattr__(self, 'int', 0)
        @property
        def hex(self):
            return format(self.int, '032x')
        def __str__(self):
            h = self.hex
            return f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}'
        def __repr__(self):
            return f"UUID('{self}')"
        def __eq__(self, other):
            return isinstance(other, UUID) and self.int == other.int
        def __hash__(self):
            return hash(self.int)

    def uuid4():
        bits = _rnd.getrandbits(128)
        bits = (bits & ~(0xf << 76)) | (4 << 76)
        bits = (bits & ~(0x3 << 62)) | (0x2 << 62)
        return UUID(int=bits)

    m = type(_sys)("uuid")
    m.__file__ = "<frozen uuid>"
    m.UUID = UUID
    m.uuid4 = uuid4
    _sys.modules["uuid"] = m

try:
    import uuid
    uuid.uuid4  # verify it's real
except (ImportError, AttributeError):
    _register_uuid()
del _register_uuid


# --- frozen stdlib: hashlib module (pure Python SHA-256) ---
def _register_hashlib():
    _K256 = [
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
    ]
    class _Sha256:
        def __init__(self, data=b''):
            self._h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]
            self._buf = b''
            self._count = 0
            if data:
                self.update(data)
        def _rr(self, x, n):
            return ((x >> n) | (x << (32 - n))) & 0xffffffff
        def _compress(self, block):
            w = [int.from_bytes(block[i:i+4], 'big') for i in range(0, 64, 4)]
            for i in range(16, 64):
                s0 = self._rr(w[i-15], 7) ^ self._rr(w[i-15], 18) ^ (w[i-15] >> 3)
                s1 = self._rr(w[i-2], 17) ^ self._rr(w[i-2], 19) ^ (w[i-2] >> 10)
                w.append((w[i-16] + s0 + w[i-7] + s1) & 0xffffffff)
            a,b,c,d,e,f,g,h = self._h
            for i in range(64):
                S1 = self._rr(e,6) ^ self._rr(e,11) ^ self._rr(e,25)
                ch = (e & f) ^ ((~e) & g)
                t1 = (h + S1 + ch + _K256[i] + w[i]) & 0xffffffff
                S0 = self._rr(a,2) ^ self._rr(a,13) ^ self._rr(a,22)
                mj = (a & b) ^ (a & c) ^ (b & c)
                t2 = (S0 + mj) & 0xffffffff
                h,g,f,e,d,c,b,a = g,f,e,(d+t1)&0xffffffff,c,b,a,(t1+t2)&0xffffffff
            for i,v in enumerate([a,b,c,d,e,f,g,h]):
                self._h[i] = (self._h[i] + v) & 0xffffffff
        def update(self, data):
            if isinstance(data, str):
                data = data.encode('utf-8')
            self._buf += data
            self._count += len(data)
            while len(self._buf) >= 64:
                self._compress(self._buf[:64])
                self._buf = self._buf[64:]
        def digest(self):
            buf = self._buf + b'\x80'
            buf += b'\x00' * ((55 - len(self._buf)) % 64)
            buf += (self._count * 8).to_bytes(8, 'big')
            h = list(self._h)
            _tmp = _Sha256.__new__(_Sha256)
            _tmp._h = h; _tmp._buf = b''; _tmp._count = 0
            for i in range(0, len(buf), 64):
                _tmp._compress(buf[i:i+64])
            return b''.join(v.to_bytes(4, 'big') for v in _tmp._h)
        def hexdigest(self):
            return self.digest().hex()
        def copy(self):
            c = _Sha256.__new__(_Sha256)
            c._h = list(self._h); c._buf = self._buf; c._count = self._count
            return c

    def sha256(data=b''):
        return _Sha256(data)

    class _Sha224:
        """SHA-224: same as SHA-256 but with different IV and truncated output."""
        _IV = [0xc1059ed8,0x367cd507,0x3070dd17,0xf70e5939,0xffc00b31,0x68581511,0x64f98fa7,0xbefa4fa4]
        def __init__(self, data=b''):
            self._inner = _Sha256.__new__(_Sha256)
            self._inner._h = list(self._IV)
            self._inner._buf = b''
            self._inner._count = 0
            if data:
                self.update(data)
        def update(self, data):
            self._inner.update(data)
            return self
        def digest(self):
            return self._inner.digest()[:28]
        def hexdigest(self):
            return self.digest().hex()
        def copy(self):
            c = _Sha224.__new__(_Sha224)
            c._inner = self._inner.copy()
            return c

    def sha224(data=b''):
        return _Sha224(data)

    _algorithms = {'sha256': sha256, 'sha224': sha224}
    m = type(_sys)("hashlib")
    m.__file__ = "<frozen hashlib>"
    m.sha256 = sha256
    m.sha224 = sha224
    m.new = lambda name, data=b'': _algorithms.get(name, lambda d=b'': None)(data)
    _sys.modules["hashlib"] = m

try:
    import hashlib
    hashlib.sha256  # verify it's real
except (ImportError, AttributeError):
    _register_hashlib()
del _register_hashlib


# --- frozen stdlib: base64 module ---
def _register_base64():
    _B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    _B64D = {c: i for i, c in enumerate(_B64)}
    _B64D['='] = 0

    def b64encode(s):
        if isinstance(s, str): s = s.encode('utf-8')
        r = bytearray()
        for i in range(0, len(s), 3):
            chunk = s[i:i+3]
            n = (chunk[0] << 16) | (chunk[1] << 8 if len(chunk) > 1 else 0) | (chunk[2] if len(chunk) > 2 else 0)
            r.append(ord(_B64[(n >> 18) & 63]))
            r.append(ord(_B64[(n >> 12) & 63]))
            r.append(ord(_B64[(n >> 6) & 63]) if len(chunk) > 1 else ord('='))
            r.append(ord(_B64[n & 63]) if len(chunk) > 2 else ord('='))
        return bytes(r)

    def b64decode(s):
        if isinstance(s, (bytes, bytearray)): s = s.decode('ascii')
        s = s.rstrip('=')
        r = bytearray()
        for i in range(0, len(s), 4):
            chunk = s[i:i+4]
            n = 0
            for c in chunk:
                n = (n << 6) | _B64D.get(c, 0)
            n <<= (4 - len(chunk)) * 6
            r.append((n >> 16) & 0xff)
            if len(chunk) > 2: r.append((n >> 8) & 0xff)
            if len(chunk) > 3: r.append(n & 0xff)
        return bytes(r)

    m = type(_sys)("base64")
    m.__file__ = "<frozen base64>"
    m.b64encode = b64encode
    m.b64decode = b64decode
    m.encodebytes = lambda s: b64encode(s) + b'\n'
    m.decodebytes = b64decode
    _sys.modules["base64"] = m

try:
    import base64
    base64.b64encode  # verify it's real
except (ImportError, AttributeError):
    _register_base64()
del _register_base64


# --- frozen stdlib: math module ---
def _register_math():
    def _ln(x):
        if x <= 0: raise ValueError("math domain error")
        if x == 1: return 0.0
        r = 0.0
        while x > 2: x /= 2.718281828459045; r += 1.0
        while x < 0.5: x *= 2.718281828459045; r -= 1.0
        x -= 1; t = x; s = x
        for n in range(2, 50):
            t *= -x * (n - 1) / n
            s += t / n if n % 2 else -t / n
        return r + s

    m = type(_sys)("math")
    m.__file__ = "<frozen math>"
    m.ceil = lambda x: int(x) if x == int(x) else int(x) + (1 if x > 0 else 0)
    m.floor = lambda x: int(x) if x >= 0 or x == int(x) else int(x) - 1
    m.fabs = lambda x: x if x >= 0 else -x
    m.sqrt = lambda x: x ** 0.5
    m.pow = lambda x, y: x ** y
    m.log = lambda x, base=2.718281828459045: _ln(x) / _ln(base) if base != 2.718281828459045 else _ln(x)
    m.pi = 3.141592653589793
    m.e = 2.718281828459045
    m.inf = float('inf')
    m.nan = float('nan')
    m._ln = _ln
    _sys.modules["math"] = m

try:
    import math
    math.ceil  # verify it's real
except (ImportError, AttributeError):
    _register_math()
del _register_math


# --- frozen stdlib: secrets module ---
def _register_secrets():
    import random as _rnd
    def token_bytes(nbytes=32):
        return bytes(_rnd.getrandbits(8) for _ in range(nbytes))
    def token_hex(nbytes=32):
        return token_bytes(nbytes).hex()
    def token_urlsafe(nbytes=32):
        import base64 as _b64
        return _b64.b64encode(token_bytes(nbytes)).rstrip(b'=').decode('ascii')
    m = type(_sys)("secrets")
    m.__file__ = "<frozen secrets>"
    m.token_bytes = token_bytes
    m.token_hex = token_hex
    m.token_urlsafe = token_urlsafe
    _sys.modules["secrets"] = m

try:
    import secrets
    secrets.token_bytes
except (ImportError, AttributeError):
    _register_secrets()
del _register_secrets


# --- frozen stdlib: __future__ module ---
def _register_future():
    m = type(_sys)("__future__")
    m.__file__ = "<frozen __future__>"
    m.division = True
    m.absolute_import = True
    m.print_function = True
    m.unicode_literals = True
    m.annotations = True
    m.generator_stop = True
    m.nested_scopes = True
    m.generators = True
    m.with_statement = True
    m.barry_as_FLUFL = False
    _sys.modules["__future__"] = m

try:
    import __future__
    __future__.division
except (ImportError, AttributeError):
    _register_future()
del _register_future


# --- frozen stdlib: string module ---
def _register_string():
    import sys as _s
    m = type(_s)("string")
    m.__file__ = "<frozen string>"
    m.ascii_lowercase = "abcdefghijklmnopqrstuvwxyz"
    m.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    m.ascii_letters = m.ascii_lowercase + m.ascii_uppercase
    m.digits = "0123456789"
    m.hexdigits = "0123456789abcdefABCDEF"
    m.octdigits = "01234567"
    m.punctuation = """!"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"""
    m.printable = m.digits + m.ascii_letters + m.punctuation + " \t\n\r\x0b\x0c"
    m.whitespace = " \t\n\r\x0b\x0c"

    class Formatter:
        def format(self, format_string, *args, **kwargs):
            return format_string.format(*args, **kwargs)
        def vformat(self, format_string, args, kwargs):
            return format_string.format(*args, **kwargs)

    class Template:
        def __init__(self, template):
            self.template = template
        def substitute(self, mapping=None, **kws):
            d = mapping or {}
            d.update(kws)
            result = self.template
            for k, v in d.items():
                result = result.replace(f"${k}", str(v)).replace(f"${{{k}}}", str(v))
            return result
        safe_substitute = substitute

    m.Formatter = Formatter
    m.Template = Template
    m.capwords = lambda s, sep=None: (sep or " ").join(
        w.capitalize() for w in s.split(sep)
    )
    _s.modules["string"] = m

try:
    import string
    string.ascii_letters  # verify it's real
except (ImportError, AttributeError):
    _register_string()
del _register_string


# --- frozen stdlib: urllib.parse module ---
def _register_urllib_parse():
    import sys as _s
    # Create urllib package if needed
    if "urllib" not in _s.modules:
        _urllib = type(_s)("urllib")
        _urllib.__file__ = "<frozen urllib>"
        _urllib.__path__ = ["<frozen urllib>"]
        _urllib.__package__ = "urllib"
        _s.modules["urllib"] = _urllib
    else:
        _urllib = _s.modules["urllib"]

    m = type(_s)("urllib.parse")
    m.__file__ = "<frozen urllib.parse>"
    m.__package__ = "urllib"

    _always_safe = frozenset(
        'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        'abcdefghijklmnopqrstuvwxyz'
        '0123456789' '_.-~')

    def unquote(s, encoding='utf-8', errors='replace'):
        if '%' not in s:
            return s
        res = []
        i = 0
        while i < len(s):
            if s[i] == '%' and i + 2 < len(s):
                try:
                    byte_val = int(s[i+1:i+3], 16)
                    res.append(bytes([byte_val]))
                    i += 3
                    continue
                except ValueError:
                    pass
            res.append(s[i].encode(encoding))
            i += 1
        return b''.join(res).decode(encoding, errors)

    def quote(s, safe='/'):
        if isinstance(s, str):
            s = s.encode('utf-8')
        res = []
        safe_set = frozenset(safe.encode('ascii') if isinstance(safe, str) else safe)
        for byte in s:
            if byte in _always_safe or byte in safe_set:
                res.append(chr(byte))
            else:
                res.append('%{:02X}'.format(byte))
        return ''.join(res)

    def quote_plus(s, safe=''):
        return quote(s, safe + ' ').replace(' ', '+')

    def unquote_plus(s, encoding='utf-8', errors='replace'):
        return unquote(s.replace('+', ' '), encoding, errors)

    def urlencode(query, doseq=False):
        if hasattr(query, 'items'):
            query = list(query.items())
        parts = []
        for k, v in query:
            if doseq and isinstance(v, (list, tuple)):
                for item in v:
                    parts.append(f"{quote_plus(str(k))}={quote_plus(str(item))}")
            else:
                parts.append(f"{quote_plus(str(k))}={quote_plus(str(v))}")
        return '&'.join(parts)

    def parse_qs(qs, keep_blank_values=False, strict_parsing=False):
        result = {}
        for part in qs.split('&'):
            if '=' not in part:
                continue
            k, v = part.split('=', 1)
            k, v = unquote_plus(k), unquote_plus(v)
            if v or keep_blank_values:
                result.setdefault(k, []).append(v)
        return result

    def parse_qsl(qs, keep_blank_values=False, strict_parsing=False):
        result = []
        for part in qs.split('&'):
            if '=' not in part:
                continue
            k, v = part.split('=', 1)
            k, v = unquote_plus(k), unquote_plus(v)
            if v or keep_blank_values:
                result.append((k, v))
        return result

    def urlparse(url, scheme='', allow_fragments=True):
        from collections import namedtuple
        ParseResult = namedtuple('ParseResult',
            ['scheme','netloc','path','params','query','fragment'])
        netloc = path = params = query = fragment = ''
        i = url.find(':')
        if i > 0 and url[:i].isalpha():
            scheme = url[:i].lower()
            url = url[i+1:]
        if url[:2] == '//':
            delim = len(url)
            for c in '/?#':
                idx = url.find(c, 2)
                if idx >= 0:
                    delim = min(delim, idx)
            netloc = url[2:delim]
            url = url[delim:]
        if allow_fragments and '#' in url:
            url, fragment = url.rsplit('#', 1)
        if '?' in url:
            url, query = url.split('?', 1)
        path = url
        return ParseResult(scheme, netloc, path, params, query, fragment)

    def urlunparse(components):
        scheme, netloc, path, params, query, fragment = components
        url = ''
        if scheme:
            url = scheme + '://'
        if netloc:
            url += netloc
        url += path
        if params:
            url += ';' + params
        if query:
            url += '?' + query
        if fragment:
            url += '#' + fragment
        return url

    def urljoin(base, url, allow_fragments=True):
        if not base:
            return url
        if not url:
            return base
        if '://' in url:
            return url
        bp = urlparse(base)
        if url.startswith('/'):
            return urlunparse((bp.scheme, bp.netloc, url, '', '', ''))
        path = bp.path.rsplit('/', 1)[0] + '/' + url
        return urlunparse((bp.scheme, bp.netloc, path, '', '', ''))

    m.unquote = unquote
    m.quote = quote
    m.quote_plus = quote_plus
    m.unquote_plus = unquote_plus
    m.urlencode = urlencode
    m.parse_qs = parse_qs
    m.parse_qsl = parse_qsl
    m.urlparse = urlparse
    m.urlunparse = urlunparse
    m.urljoin = urljoin
    _s.modules["urllib.parse"] = m
    _urllib.parse = m

try:
    import urllib.parse
    urllib.parse.unquote  # verify it's real
except (ImportError, AttributeError):
    _register_urllib_parse()
del _register_urllib_parse


# --- Install the universal fallback import wrapper ---
# This MUST be after all rich stdlib stubs above, so that try/except import
# blocks use _orig_import and the rich stubs get registered properly.
_builtins.__import__ = _wasi_safe_import
