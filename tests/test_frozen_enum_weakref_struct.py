"""Tests for the `enum`, `weakref` and `struct` modules that frozen_stdlib_preamble.py registers in a canister.

The standard library's Python sources are not in the canister, so the preamble
provides these three (#67). Each test registers the preamble's version into a
private `sys.modules`, runs the same code on it and on CPython's module, and
compares what comes out.
"""

import ast
import enum as real_enum
import gc
import os
import struct as real_struct
import types
import weakref as real_weakref

import pytest

PREAMBLE = os.path.join(os.path.dirname(__file__), "..", "basilisk", "frozen_stdlib_preamble.py")


def register(name):
    """Run the preamble's `_register_<name>` against a private `sys`; return the module it registers."""
    with open(PREAMBLE) as f:
        source = f.read()
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == f"_register_{name}")
    private_sys = types.ModuleType("private_sys")
    private_sys.modules = {}
    namespace = {"_sys": private_sys}
    exec(compile(ast.Module([node], []), PREAMBLE, "exec"), namespace)
    namespace[f"_register_{name}"]()
    return private_sys.modules[name]


def observe(scenario, module):
    """Every (label, outcome) the scenario notes, run on one module."""
    notes = []

    def note(label, make):
        try:
            value = make()
        except Exception as e:
            value = ("raises", type(e).__name__)
        notes.append((label, value if isinstance(value, tuple) and value[:1] == ("raises",) else repr(value)))

    scenario(module, note)
    return notes


def assert_same(scenario, canister_module, real_module):
    for mine, theirs in zip(observe(scenario, canister_module), observe(scenario, real_module), strict=True):
        assert mine == theirs


# --- enum ---------------------------------------------------------------------


def plain_enum(enum, note):
    class Color(enum.Enum):
        RED = 1
        GREEN = 2
        BLUE = 3
        CRIMSON = 1  # an alias of RED

    note("type", lambda: type(Color.RED).__name__)
    note("isinstance", lambda: isinstance(Color.RED, Color))
    note("repr", lambda: repr(Color.RED))
    note("str", lambda: str(Color.RED))
    note("format", lambda: format(Color.RED))
    note("format spec", lambda: f"{Color.RED:>12}")
    note("name and value", lambda: (Color.RED.name, Color.RED.value))
    note("iteration", lambda: [m.name for m in Color])
    note("reversed", lambda: [m.name for m in reversed(Color)])
    note("len", lambda: len(Color))
    note("by value", lambda: Color(2))
    note("by name", lambda: Color["BLUE"])
    note("alias is canonical", lambda: Color.CRIMSON is Color.RED)
    note("alias by value", lambda: Color(1).name)
    note("members", lambda: list(Color.__members__.items()))
    note("bad value", lambda: Color(4))
    note("bad name", lambda: Color["PINK"])
    note("member in", lambda: Color.RED in Color)
    note("value in", lambda: (1 in Color, 5 in Color))
    note("not its value", lambda: Color.RED == 1)
    note("identity", lambda: Color.RED == Color.RED and Color.RED != Color.GREEN)
    note("hashable", lambda: {Color.RED: "x"}[Color.CRIMSON])
    note("no ordering", lambda: Color.RED < Color.BLUE)
    note("class repr", lambda: repr(Color))
    note("reassign", lambda: setattr(Color, "RED", 5))
    note("delete", lambda: delattr(Color, "RED"))
    note("lookup of a member", lambda: Color(Color.BLUE))

    def extend():
        class More(Color):
            PINK = 4
    note("cannot extend", extend)
    note("unique", lambda: enum.unique(Color))


def auto_values(enum, note):
    class Auto(enum.Enum):
        A = enum.auto()
        B = enum.auto()
        C = 10
        D = enum.auto()

    note("auto counts", lambda: [m.value for m in Auto])
    note("auto distinct", lambda: Auto.A == Auto.B)

    class Named(enum.Enum):
        def _generate_next_value_(name, start, count, last_values):
            return name.lower()
        NORTH = enum.auto()
        SOUTH = enum.auto()

    note("own generator", lambda: [m.value for m in Named])

    class Labelled(enum.Enum):
        X = enum.auto(), "label"
        Y = 5
        Z = enum.auto(), "z"

    note("auto inside a tuple", lambda: [m.value for m in Labelled])
    note("unique passes", lambda: list(enum.unique(Named)))


def int_enum(enum, note):
    class Num(enum.IntEnum):
        ONE = 1
        TWO = 2

    note("is int", lambda: isinstance(Num.ONE, int))
    note("equals int", lambda: (Num.ONE == 1, Num.ONE + 1, Num.TWO * 3))
    note("str", lambda: str(Num.ONE))
    note("repr", lambda: repr(Num.ONE))
    note("format", lambda: (format(Num.ONE, "03d"), f"{Num.TWO}"))
    note("sorts", lambda: sorted([Num.TWO, Num.ONE]))
    note("int key", lambda: {1: "a"}[Num.ONE])
    note("by value", lambda: Num(2))
    note("auto", lambda: list(enum.IntEnum("N", "A B C")))


def str_enum(enum, note):
    class Size(enum.StrEnum):
        SMALL = enum.auto()
        LARGE = "big"

    note("auto lowercases", lambda: Size.SMALL.value)
    note("str", lambda: (str(Size.LARGE), f"{Size.LARGE}", format(Size.LARGE, ">5")))
    note("is str", lambda: (Size.LARGE == "big", Size.LARGE.upper(), isinstance(Size.LARGE, str)))
    note("repr", lambda: repr(Size.LARGE))

    def not_a_string():
        class Bad(enum.StrEnum):
            ONE = 1
    note("refuses non-str", not_a_string)

    class Mixed(str, enum.Enum):
        RED = "red"

    note("mixin str", lambda: (str(Mixed.RED), format(Mixed.RED), repr(Mixed.RED)))
    note("mixin equality", lambda: Mixed.RED == "red")


def richer_enums(enum, note):
    class Planet(enum.Enum):
        MERCURY = (3.303e23, 2.4397e6)
        EARTH = (5.976e24, 6.37814e6)

        def __init__(self, mass, radius):
            self.mass = mass
            self.radius = radius

        @property
        def surface_gravity(self):
            return 6.673e-11 * self.mass / (self.radius * self.radius)

        def describe(self):
            return f"{self.name} {self.radius}"

    note("init and methods", lambda: (Planet.EARTH.value, Planet.EARTH.mass, Planet.EARTH.describe(),
                                      round(Planet.EARTH.surface_gravity, 3)))
    note("methods are not members", lambda: list(Planet.__members__))

    class Lower(enum.Enum):
        A = "a"

        @classmethod
        def _missing_(cls, value):
            return cls.A if value == "A" else None

    note("missing", lambda: (Lower("A"), Lower("b")))

    class Kept(enum.Enum):
        _ignore_ = ["scratch"]
        scratch = 5
        X = 1

        class Inner:
            pass

    note("ignore and nested class", lambda: (list(Kept.__members__), hasattr(Kept, "scratch")))

    class Coord(bytes, enum.Enum):
        def __new__(cls, value, label):
            member = bytes.__new__(cls, [value])
            member._value_ = value
            member.label = label
            return member
        PX = (0, "P.X")
        PY = (1, "P.Y")

    note("custom new", lambda: (Coord.PY.value, Coord.PY.label, Coord(1) is Coord.PY, bytes(Coord.PY)))

    class Unhashable(enum.Enum):
        A = [1]
        B = [2]

    note("unhashable values", lambda: (Unhashable([2]), [2] in Unhashable))

    Animal = enum.Enum("Animal", "ANT BEE, CAT")
    note("functional", lambda: (repr(Animal.BEE), [m.value for m in Animal], repr(Animal)))
    note("functional pairs", lambda: list(enum.Enum("Pairs", [("X", 5), ("Y", 7)])))
    note("functional dict", lambda: list(enum.Enum("Mapping", {"X": "x"})))


@pytest.mark.parametrize("scenario", [plain_enum, auto_values, int_enum, str_enum, richer_enums])
def test_enum_matches_cpython(scenario):
    assert_same(scenario, register("enum"), real_enum)


def test_enum_members_are_not_their_values():
    """What #67 saw: members were raw values, iteration empty, auto() always 0."""
    enum = register("enum")

    class Color(enum.Enum):
        RED = 1
        BLUE = 2

    class Auto(enum.Enum):
        A = enum.auto()
        B = enum.auto()

    assert type(Color.RED) is Color
    assert list(Color) == [Color.RED, Color.BLUE]
    assert Color.RED.value == 1 and Color.RED.name == "RED"
    assert Auto.A != Auto.B and (Auto.A.value, Auto.B.value) == (1, 2)


def test_flag_is_not_pretended():
    enum = register("enum")
    assert not hasattr(enum, "Flag") and not hasattr(enum, "IntFlag")


# --- weakref ------------------------------------------------------------------


class Thing:
    def __init__(self, label):
        self.label = label

    def __repr__(self):
        return f"Thing({self.label})"


def references(weakref, note):
    thing = Thing("a")
    ref = weakref.ref(thing)
    note("alive", lambda: ref() is thing)
    proxy = weakref.proxy(thing)
    note("proxy", lambda: proxy.label)
    note("count", lambda: weakref.getweakrefcount(thing))
    del thing
    gc.collect()
    note("dead after del", lambda: ref())
    note("dead proxy", lambda: proxy.label)


def weak_value_dictionary(weakref, note):
    a, b = Thing("a"), Thing("b")
    cache = weakref.WeakValueDictionary({"a": a})
    cache["b"] = b
    note("contains", lambda: ("a" in cache, "b" in cache, len(cache)))
    note("items", lambda: sorted((k, v.label) for k, v in cache.items()))
    note("get", lambda: (cache.get("a").label, cache.get("zz", "default")))
    note("setdefault", lambda: cache.setdefault("a", b).label)
    del a
    gc.collect()
    note("entry gone", lambda: ("a" in cache, len(cache), list(cache), cache.get("a")))
    note("getitem gone", lambda: cache["a"])
    note("pop default", lambda: cache.pop("a", "none"))
    note("pop missing", lambda: cache.pop("a"))
    note("copy", lambda: sorted(cache.copy().keys()))
    note("repr", lambda: repr(cache).startswith("<WeakValueDictionary at 0x"))
    cache["b"] = Thing("replaced")
    gc.collect()
    note("replaced then collected", lambda: (len(cache), b.label))


def weak_set(weakref, note):
    a, b = Thing("a"), Thing("b")
    items = weakref.WeakSet([a])
    items.add(b)
    note("contains", lambda: (a in items, b in items, len(items), 5 in items))
    del a
    gc.collect()
    note("item gone", lambda: (len(items), [t.label for t in items]))
    items.discard(b)
    note("discarded", lambda: len(items))


@pytest.mark.parametrize("scenario", [references, weak_value_dictionary, weak_set])
def test_weakref_matches_cpython(scenario):
    assert_same(scenario, register("weakref"), real_weakref)


# --- struct -------------------------------------------------------------------


def packing(struct, note):
    note("pack", lambda: struct.pack("<IhQ?", 1, -2, 2**63, True))
    note("unpack", lambda: struct.unpack(">d3s", b"@\t!\xfbTD-\x18abc"))
    note("calcsize", lambda: (struct.calcsize("<IhQ"), struct.calcsize("@IhQ")))
    note("Struct", lambda: struct.Struct("<2H").unpack(b"\x01\x00\x02\x00"))
    note("iter_unpack", lambda: list(struct.iter_unpack("<H", b"\x01\x00\x02\x00")))
    buffer = bytearray(6)
    note("pack_into", lambda: (struct.pack_into("<HI", buffer, 0, 7, 9), bytes(buffer)))
    note("unpack_from", lambda: struct.unpack_from("<I", buffer, 2))
    note("error", lambda: struct.pack("<B", 300))
    note("error type", lambda: issubclass(struct.error, Exception))
    note("all", lambda: sorted(struct.__all__))


def test_struct_matches_cpython():
    assert_same(packing, register("struct"), real_struct)
