import sys as _sys

# --- Bootstrap import system ---
# When _Py_InitializeMain is skipped (WASI CPython), sys.meta_path may be
# empty and many stdlib modules aren't available (no filesystem).
# 1. Try to install BuiltinImporter/FrozenImporter from _frozen_importlib
# 2. Install a fallback finder that auto-creates empty stub modules for
#    anything that still can't be found (e.g. pickle, copyreg, logging).
#    This goes LAST so it only triggers when all other finders fail.
_frozen = _sys.modules.get('_frozen_importlib')
if _frozen:
    if not _sys.meta_path:
        _sys.meta_path.append(_frozen.BuiltinImporter)
        _sys.meta_path.append(_frozen.FrozenImporter)
    elif _frozen.BuiltinImporter not in _sys.meta_path:
        _sys.meta_path.insert(0, _frozen.BuiltinImporter)
        _sys.meta_path.insert(1, _frozen.FrozenImporter)
try:
    del _frozen
except NameError:
    pass

class _WasiStubFinder:
    """Fallback import finder for WASI: creates empty stub modules.

    Installed last on sys.meta_path so it only activates when all real
    finders have failed.  Prevents ModuleNotFoundError for stdlib modules
    that aren't frozen/built-in in the WASI CPython build.
    """
    def find_module(self, fullname, path=None):
        return self
    def load_module(self, fullname):
        if fullname in _sys.modules:
            return _sys.modules[fullname]
        mod = type(_sys)(fullname)
        mod.__file__ = "<wasi-stub>"
        mod.__loader__ = self
        mod.__path__ = []
        mod.__package__ = fullname
        _sys.modules[fullname] = mod
        return mod

_sys.meta_path.append(_WasiStubFinder())

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
    # All typing constructs are no-ops at runtime
    m.Any = object
    m.Union = None
    m.Optional = lambda x: x
    m.List = list
    m.Dict = dict
    m.Set = set
    m.Tuple = tuple
    m.Type = type
    m.Callable = object
    m.Iterator = object
    m.Generator = object
    m.Iterable = object
    m.Sequence = object
    m.Mapping = object
    m.MutableMapping = object
    m.ClassVar = None
    m.Final = None
    m.Literal = None
    m.Annotated = None
    m.TypeAlias = None
    m.NoReturn = None
    m.TYPE_CHECKING = False
    def _identity(x=None): return x
    m.TypeVar = lambda name, *a, **kw: object
    m.ParamSpec = lambda name, *a, **kw: object
    m.Generic = object
    m.Protocol = object
    m.TypedDict = type
    m.overload = lambda f: f
    m.cast = lambda t, v: v
    m.no_type_check = lambda f: f
    m.runtime_checkable = lambda cls: cls
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
