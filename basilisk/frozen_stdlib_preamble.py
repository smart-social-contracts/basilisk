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
def _register_os():
    _os = _sys.modules.get('os')
    if _os is None or not hasattr(_os, 'path') or not hasattr(getattr(_os, 'path', None) or _os, 'exists'):
        if _os is None:
            _os = type(_sys)('os')
            _os.__file__ = '<frozen os>'
            _os.__path__ = []
            _os.__package__ = 'os'
            _sys.modules['os'] = _os
        class _FakePath:
            sep = '/'
            def exists(self, p): return False
            def join(self, *a): return '/'.join(a)
            def dirname(self, p): return p.rsplit('/', 1)[0] if '/' in p else ''
            def basename(self, p): return p.rsplit('/', 1)[-1]
            def isfile(self, p): return False
            def isdir(self, p): return False
            def abspath(self, p): return p
            def expanduser(self, p): return p
            def normpath(self, p): return p
            def realpath(self, p): return p
            def splitext(self, p):
                i = p.rfind('.')
                return (p[:i], p[i:]) if i > 0 else (p, '')
        _os.path = _FakePath()
        if not hasattr(_os, 'sep'):
            _os.sep = '/'
        if not hasattr(_os, 'getcwd'):
            _os.getcwd = lambda: '/'
        if not hasattr(_os, 'environ'):
            _os.environ = {}
        if not hasattr(_os, 'listdir'):
            _os.listdir = lambda p='/': []
        if not hasattr(_os, 'makedirs'):
            _os.makedirs = lambda p, exist_ok=False: None
        if not hasattr(_os, 'remove'):
            _os.remove = lambda p: None
        if not hasattr(_os, 'urandom'):
            import random as _rnd
            _os.urandom = lambda n: bytes(_rnd.getrandbits(8) for _ in range(n))

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

    m = type(_sys)("hashlib")
    m.__file__ = "<frozen hashlib>"
    m.sha256 = sha256
    m.new = lambda name, data=b'': sha256(data) if name == 'sha256' else None
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


# --- Install the universal fallback import wrapper ---
# This MUST be after all rich stdlib stubs above, so that try/except import
# blocks use _orig_import and the rich stubs get registered properly.
_builtins.__import__ = _wasi_safe_import
