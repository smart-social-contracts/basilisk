"""Tests for the `json` module that frozen_stdlib_preamble.py registers in a canister.

The preamble holds a pure-Python `json` and, on top of it, a fast path on the
`_json` module that is built into the canister. The fast path must return
exactly what the pure-Python code returns. These tests build the module twice
from the preamble's `_register_json`: once with `_json` blocked, which gives
the pure-Python code alone, and once with `_json`, and compare the two.
"""

import ast
import collections
import json as cpython_json
import os
import random
import sys
import types

import _json
import pytest

PREAMBLE = os.path.join(os.path.dirname(__file__), "..", "basilisk", "frozen_stdlib_preamble.py")


def build_json(monkeypatch, native):
    """Run the preamble's `_register_json` against a private `sys`; return the module it registers."""
    with open(PREAMBLE) as f:
        source = f.read()
    node = next(
        n for n in ast.parse(source).body
        if isinstance(n, ast.FunctionDef) and n.name == "_register_json"
    )
    private_sys = types.ModuleType("private_sys")
    private_sys.modules = {}
    namespace = {"_sys": private_sys}
    exec(compile(ast.Module([node], []), PREAMBLE, "exec"), namespace)
    monkeypatch.setitem(sys.modules, "_json", _json if native else None)
    namespace["_register_json"]()
    return private_sys.modules["json"]


@pytest.fixture
def stub(monkeypatch):
    return build_json(monkeypatch, native=False)


@pytest.fixture
def fast(monkeypatch):
    return build_json(monkeypatch, native=True)


def outcome(function, *args, **kwargs):
    """What a call returns or raises, as something comparable."""
    try:
        value = function(*args, **kwargs)
    except RecursionError as e:
        return ("raises", "RecursionError")  # the message differs: it names the code that overflowed
    except Exception as e:
        return ("raises", type(e).__name__, str(e))
    return ("returns", type(value).__name__, repr(value))


def assert_same(fast, stub, name, *args, **kwargs):
    expected = outcome(getattr(stub, name), *args, **kwargs)
    assert outcome(getattr(fast, name), *args, **kwargs) == expected, (name, args, kwargs)
    return expected


ROW = {
    "_type": "Listing", "_id": "12", "name": "item12", "owner": "owner2", "category": "cat2",
    "installs": 84, "likes": 12, "price": 12, "description": "d" * 200, "status": "live", "__version__": 1,
}


class Text(str):
    pass


class Number(int):
    pass


class Ratio(float):
    pass


class Table(dict):
    pass


class Seq(list):
    pass


class Pair(collections.namedtuple("Pair", "x y")):
    pass


def circular_list():
    a = []
    a.append(a)
    return a


DUMPS_VALUES = [
    None, True, False, 0, -1, 7, 2**64, -(2**100), 10**30,
    0.0, -0.0, 1.5, -2.25, 1e22, 1e-7, 1e100, 123456789.123456789, 5e-324,
    float("inf"), float("-inf"), float("nan"),
    "", "abc", "é€😀", "  ", "\x00\x01\x1f\x7f\x80", '"\\/', "\b\f\n\r\t", "\ud800", "a\udc00b",
    [], {}, [[]], [{}], {"a": []}, (), (1, 2), [1, [2, [3, [4]]]],
    {"a": 1, "b": [1, 2, {"c": None}], "d": "é"},
    {"b": 1, "a": 2, "c": {"z": 1, "y": 2}},
    ROW, [ROW, ROW], {"rows": [ROW] * 3, "n": 3},
    {1: "int key", 2.5: "float key", "s": "str key"},
    {True: 1}, {False: 1}, {None: 1}, {"x": {None: [1, {True: 2}]}},
    {float("inf"): 1}, {float("-inf"): 1}, {float("nan"): 1},
    {(1, 2): "tuple key"}, {object: "type key"}, {b"x": 1},
    {"true": 1, "false": 2, "null": 3},
    {1: 1, "1": 2},
    {"k": float("nan")}, [float("inf")], {"k": [float("-inf")]},
    {"set": {1, 2}}, [object()], [b"bytes"], [bytearray(b"x")], {"d": {1: {2}}},
    Text("subclass"), {Text("key"): Text("value")},
    Number(5), Ratio(1.5), Table(a=1, b=Table(c=2)), Seq([1, Seq([2])]), Pair(1, 2),
    collections.OrderedDict([("z", 1), ("a", 2)]), collections.defaultdict(list, {"k": [1]}),
    {"big": 10**5000},
    {str(i): [i, str(i), {"n": i}] for i in range(30)},
]


class TestDumps:
    OPTIONS = [
        {},
        {"sort_keys": True},
        {"ensure_ascii": False},
        {"ensure_ascii": True},
        {"separators": (",", ": ")},
        {"separators": (", ", ": ")},
        {"indent": 2},
        {"indent": 0},
        {"indent": 2, "sort_keys": True},
        {"indent": "\t"},
        {"default": str},
        {"default": repr, "sort_keys": True},
        {"default": lambda o: None},
        {"default": lambda o: 1 / 0},
        {"default": 0},
        {"cls": object},
        {"allow_nan": False},
        {"skipkeys": True},
        {"check_circular": False},
    ]

    @pytest.mark.parametrize("options", OPTIONS, ids=repr)
    def test_same_text_as_the_stub(self, fast, stub, options):
        for value in DUMPS_VALUES:
            try:
                assert_same(fast, stub, "dumps", value, **options)
            except AssertionError as e:
                raise AssertionError(f"{value!r:.80} with {options!r}") from e

    def test_positional_arguments(self, fast, stub):
        assert_same(fast, stub, "dumps", ROW, False, True, None, (",", ":"), None)
        assert_same(fast, stub, "dumps", ROW, True, False, 3, None, str)

    def test_unsortable_keys(self, fast, stub):
        assert_same(fast, stub, "dumps", {1: 1, "a": 2}, sort_keys=True)
        assert_same(fast, stub, "dumps", {None: 1, "a": 2}, sort_keys=True)

    def test_circular_reference_is_a_recursion_error(self, fast, stub):
        assert_same(fast, stub, "dumps", circular_list())
        assert_same(fast, stub, "dumps", circular_list(), sort_keys=True)

    def test_every_code_point_is_written_as_before(self, fast, stub):
        # `default` sends the call to the stub's own writer, which now escapes with `_json`.
        for start in range(0, 0x110000, 4096):
            text = "".join(map(chr, range(start, min(start + 4096, 0x110000))))
            assert fast.dumps(text, default=str) == stub.dumps(text)
            assert fast.dumps({text: text}) == stub.dumps({text: text})

    def test_keys_true_false_none_are_written_as_python_names(self, fast):
        assert fast.dumps({True: 1, None: 2, False: 3}) == '{"True":1,"None":2,"False":3}'
        assert fast.dumps({"k": float("nan"), "j": float("inf")}) == '{"k":NaN,"j":Infinity}'

    def test_fuzz(self, fast, stub):
        rng = random.Random(20261118)
        for _ in range(1500):
            value = random_value(rng, 4)
            options = rng.choice(self.OPTIONS[:8])
            assert_same(fast, stub, "dumps", value, **options)


JSON_ROW = cpython_json.dumps(ROW)

LOADS_TEXTS = [
    JSON_ROW,
    "null", "true", "false", "0", "-0", "7", "-7", "123456789012345678901234567890", "1.5", "-2.5e-3", "1E5", "1e+5", "0.0", "-0.0",
    "1e999", "-1e999", '""', '"abc"', '"é€😀"', '"\\u00e9\\u20ac"', '"\\n\\t\\"\\\\\\/\\b\\f\\r"', '"\\u0000"',
    "[]", "{}", "[[]]", "[{}]", '{"a":{}}', "[1,2,3]", '{"a":1,"b":[true,false,null]}',
    ' \t\n\r[ 1 , 2 ]\n', '{ "a" : 1 , "b" : 2 }', " 5 ", "\n\n7",
    '{"a":1,"a":2}', '{"b":1,"a":2}', '{"":1}', '["a","a","a"]',
    '"raw\nnewline\ttab\x01control"', '{"k\nk":1}',
    cpython_json.dumps(ROW, indent=2),
    cpython_json.dumps({"s": "é€😀 ", "t": "\x00\x1f"}),
    cpython_json.dumps({"s": "é€😀"}, ensure_ascii=False),
    cpython_json.dumps([ROW] * 5),
    "[" * 50 + "]" * 50,
    # what only the stub accepts, or reads differently
    "[1] trailing", "1 2", "true false", "nullx", "{}{}", "[1]]", '{"a":1} garbage',
    "01", "-01", "1.", "1.e5", "1e", "1e+", ".5", "-.5", "-", "+1", "1.5.5", "00", "0x10",
    "NaN", "Infinity", "-Infinity", "[NaN]", '{"a": Infinity}',
    "{1:2}", "{true:1}", "{null:1}", "{1.5:2}", "[1,]", '{"a":1,}', "[,1]", "[1 2]", '{"a" 1}', '{"a":}', "{,}",
    '"\\q"', '"\\x41"', '"\\u12"', '"\\uzzzz"', '"\\u+0e9"', '"\\', '"abc', '"\\ud83d\\ude00"', '"\\uD83D\\uDE00"',
    '"\\ud83d"', '"\\ude00"', '"\\ud83dx"', '["\\ud83d\\ude00", "\\ud7ff"]', '"\\ud7ff\\ue000"', '"\\u0d00"',
    "tru", "nul", "fals", "True", "None", "'a'", "{'a':1}", "[1,2", '{"a":1', "{", "[", "", " ", "\n\t", "﻿[1]", "\x0b1",
    "9" * 5000, "[" + "9" * 5000 + "]", "1" + "0" * 400 + "e-300",
]


class TestLoads:
    @pytest.mark.parametrize("text", LOADS_TEXTS, ids=lambda t: repr(t)[:40])
    def test_same_value_or_error_as_the_stub(self, fast, stub, text):
        assert_same(fast, stub, "loads", text)
        assert_same(fast, stub, "loads", text.encode("utf-8", "surrogatepass"))
        assert_same(fast, stub, "loads", bytearray(text.encode("utf-8", "surrogatepass")))

    def test_keywords_are_ignored_as_before(self, fast, stub):
        hooks = {
            "object_hook": lambda d: "hooked", "object_pairs_hook": lambda p: "paired",
            "parse_float": lambda s: "float", "parse_int": lambda s: "int",
            "parse_constant": lambda s: "constant", "strict": True, "cls": object,
        }
        for text in ['{"a": [1, 2.5]}', "NaN", '"x\ny"']:
            assert_same(fast, stub, "loads", text, **hooks)

    def test_not_a_string(self, fast, stub):
        for value in [None, 5, 1.5, [1], {"a": 1}, (1,), object(), b"\xff", b'{"a":1}', bytearray(b"[1]"), memoryview(b"[1]")]:
            assert_same(fast, stub, "loads", value)

    def test_str_subclass(self, fast, stub):
        assert_same(fast, stub, "loads", Text('{"a": 1}'))

    def test_result_types(self, fast):
        value = fast.loads('{"a": [1, 1.0, true, null, "s", {}]}')
        assert [type(v) for v in value["a"]] == [int, float, bool, type(None), str, dict]

    def test_fuzz_valid_documents(self, fast, stub):
        rng = random.Random(20261118)
        for _ in range(600):
            text = cpython_json.dumps(
                random_value(rng, 4, odd_keys=False), ensure_ascii=rng.random() < 0.5, indent=rng.choice([None, None, 1, 2]),
                sort_keys=rng.random() < 0.5,
            )
            assert_same(fast, stub, "loads", text)

    def test_fuzz_damaged_documents(self, fast, stub):
        rng = random.Random(20261119)
        for _ in range(1500):
            text = list(cpython_json.dumps(random_value(rng, 3, odd_keys=False), ensure_ascii=rng.random() < 0.5))
            for _ in range(rng.randint(1, 3)):
                spot = rng.randrange(len(text) + 1)
                edit = rng.choice(["delete", "insert", "replace", "cut"])
                junk = rng.choice(list('{}[]:,"\\ \n-+.0123456789eEtfnaulsINx😀é'))
                if edit == "delete" and text:
                    del text[min(spot, len(text) - 1)]
                elif edit == "insert":
                    text.insert(spot, junk)
                elif edit == "replace" and text:
                    text[min(spot, len(text) - 1)] = junk
                elif edit == "cut":
                    del text[spot:]
            assert_same(fast, stub, "loads", "".join(text))


def watch_stub(module):
    """Count the calls that `module.loads` and `module.dumps` give to the pure-Python code."""
    calls = []
    for function, name in ((module.dumps, "_stub_dumps"), (module.loads, "_stub_loads")):
        cell = function.__closure__[function.__code__.co_freevars.index(name)]
        original = cell.cell_contents
        cell.cell_contents = lambda *args, _original=original, _name=name: calls.append(_name) or _original(*args)
    return calls


class TestWhatTheFastPathServes:
    """The comparisons above would also pass if the fast path were never used."""

    def test_json_serves_the_usual_calls(self, fast):
        calls = watch_stub(fast)
        for value in [ROW, [ROW] * 3, {"s": "é€😀\x00\n"}, {1: 2, 2.5: 3, 7: [None, True, 1e22]}, "text", 5, None]:
            fast.dumps(value)
            fast.dumps(value, sort_keys=True)
            fast.dumps(value, ensure_ascii=False, separators=(", ", ": "), cls=object)
        for text in [
            JSON_ROW, '  {"a": 1}', "\n\t[1, 2]\n", '{"a": "raw\ttab\ncontrol\x01"}', '"\\u00e9\\u20ac\\n"',
            "-0.5e3", "1" + "0" * 50, '{"é": ["€", "😀", null, true, false]}', "[" * 100 + "]" * 100, "7 ",
        ]:
            fast.loads(text)
            fast.loads(text.encode("utf-8"))
            fast.loads(text, object_hook=dict)
        assert calls == []

    def test_what_overflows_the_stack_in_a_canister_never_reaches_the_stub(self, fast):
        # The stub's `dumps` overflows the wasm stack about 450 levels down, or on a circular list, and
        # traps the canister. `_json` stops with a RecursionError instead; handing that to the stub would
        # bring the trap back.
        calls = watch_stub(fast)
        nested = []
        for _ in range(600):
            nested = [nested]
        assert fast.dumps(nested) == "[" * 601 + "]" * 601
        with pytest.raises(RecursionError):
            fast.dumps(circular_list())
        with pytest.raises(RecursionError):
            fast.dumps(circular_list(), sort_keys=True)
        assert calls == []

    def test_the_stub_serves_what_json_would_read_differently(self, fast):
        calls = watch_stub(fast)
        asked = [
            lambda: fast.dumps(ROW, indent=2),
            lambda: fast.dumps(ROW, default=str),
            lambda: fast.dumps({"k": float("nan")}),
            lambda: fast.dumps([float("inf")]),
            lambda: fast.dumps({True: 1}),
            lambda: fast.dumps({None: 1}),
            lambda: fast.dumps({(1, 2): 1}),
            lambda: fast.dumps({"s": {1, 2}}),
            lambda: fast.dumps({1: 1, "a": 2}, sort_keys=True),
            lambda: fast.loads('"\\ud83d\\ude00"'),
            lambda: fast.loads('"\\ud7ff"'),
            lambda: fast.loads("NaN"),
            lambda: fast.loads("[1] trailing"),
            lambda: fast.loads("01"),
            lambda: fast.loads("{1:2}"),
            lambda: fast.loads('"\\q"'),
            lambda: fast.loads("[1,"),
            lambda: fast.loads(""),
            lambda: fast.loads(None),
            lambda: fast.loads([1]),
        ]
        for ask in asked:
            before = len(calls)
            try:
                ask()
            except Exception:
                pass
            assert len(calls) == before + 1, ask.__code__.co_consts

    def test_without_json_there_is_only_the_stub(self, monkeypatch):
        module = build_json(monkeypatch, native=False)
        assert module.dumps(ROW) == cpython_json.dumps(ROW, separators=(",", ":"), ensure_ascii=False)
        assert module.loads(JSON_ROW) == ROW


def random_value(rng, depth, odd_keys=True):
    kind = rng.randrange(12 if depth else 8)
    if kind == 0:
        return None
    if kind == 1:
        return rng.choice([True, False])
    if kind == 2:
        return rng.choice([0, 1, -1, 255, 2**31, -(2**63), 10**25, rng.randrange(-10**6, 10**6)])
    if kind == 3:
        return rng.choice([0.0, -0.5, 1.5, 1e22, 1e-9, 3.14159, rng.uniform(-1e6, 1e6), float("inf"), float("nan")])
    if kind in (4, 5, 6, 7):
        alphabet = 'ab "\\/\n\t\x00\x1féß€😀  true null'
        return "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 12)))
    if kind in (8, 9):
        return [random_value(rng, depth - 1, odd_keys) for _ in range(rng.randrange(0, 4))]
    names = ["a", "b", "true", "null", "é", "k k", "1"]
    if odd_keys:
        names += [1, 2.5, True, None, (1, 2)]
    return {rng.choice(names): random_value(rng, depth - 1, odd_keys) for _ in range(rng.randrange(0, 4))}
