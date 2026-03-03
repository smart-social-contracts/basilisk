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
        def insert(self, key, value):
            if self._native:
                return self._fn("insert")(key, value)
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

    try:
        del _bic, _StableBTreeMap
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
    except (ImportError, AttributeError):
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
            # Minimal: just store ts, return stub
            d = datetime()
            d._ts = ts
            return d
        def strftime(self, fmt):
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d} {self.hour:02d}:{self.minute:02d}:{self.second:02d}.{self.microsecond:06d}"
        def __repr__(self):
            return self.strftime("%Y-%m-%d %H:%M:%S.%f")

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
    m.Counter = dict
    m.namedtuple = lambda name, fields: type(name, (tuple,), {})
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
    def dataclass(cls=None, **kw):
        if cls is None:
            return lambda c: c
        return cls
    def field(**kw):
        return kw.get('default', kw.get('default_factory', lambda: None)())
    m = type(_sys)("dataclasses")
    m.__file__ = "<frozen dataclasses>"
    m.dataclass = dataclass
    m.field = field
    m.fields = lambda cls: []
    m.asdict = lambda obj: {}
    m.astuple = lambda obj: ()
    m.replace = lambda obj, **kw: obj
    m.is_dataclass = lambda obj: False
    m.FrozenInstanceError = type('FrozenInstanceError', (AttributeError,), {})
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

# --- Install the universal fallback import wrapper ---
# This MUST be after all rich stdlib stubs above, so that try/except import
# blocks use _orig_import and the rich stubs get registered properly.
_builtins.__import__ = _wasi_safe_import
