"""Tests for the `hashlib` module that frozen_stdlib_preamble.py registers in a canister.

The preamble holds a pure-Python SHA-256 and, on top of it, a SHA-256 that
hands the hashing to `_basilisk_sandbox.sha256`, which exists in a canister.
Both must give the digests CPython's hashlib gives, and behave alike. These
tests build the module from the preamble's `_register_hashlib` twice: with
`_basilisk_sandbox` blocked (the pure-Python code alone) and with a stand-in
for it, and compare the two against each other and against hashlib.
"""

import ast
import hashlib as cpython_hashlib
import os
import random
import sys
import types

import pytest

PREAMBLE = os.path.join(os.path.dirname(__file__), "..", "basilisk", "frozen_stdlib_preamble.py")


class Sandbox(types.ModuleType):
    """`_basilisk_sandbox` as far as `sha256` goes: str or bytes in (a PyArg "s#"), hex digest out."""

    def __init__(self):
        super().__init__("_basilisk_sandbox")
        self.calls = []

    def sha256(self, data):
        if not isinstance(data, (str, bytes)):
            raise TypeError("argument 1 must be str or read-only bytes-like object, not " + type(data).__name__)
        self.calls.append(data)
        return cpython_hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def build_hashlib(monkeypatch, sandbox):
    """Run the preamble's `_register_hashlib` against a private `sys`; return the module it registers."""
    with open(PREAMBLE) as f:
        source = f.read()
    node = next(
        n for n in ast.parse(source).body
        if isinstance(n, ast.FunctionDef) and n.name == "_register_hashlib"
    )
    private_sys = types.ModuleType("private_sys")
    private_sys.modules = {}
    namespace = {"_sys": private_sys}
    exec(compile(ast.Module([node], []), PREAMBLE, "exec"), namespace)
    monkeypatch.setitem(sys.modules, "_basilisk_sandbox", sandbox)
    namespace["_register_hashlib"]()
    return private_sys.modules["hashlib"]


@pytest.fixture
def stub(monkeypatch):
    return build_hashlib(monkeypatch, None)


@pytest.fixture
def sandbox():
    return Sandbox()


@pytest.fixture
def fast(monkeypatch, sandbox):
    return build_hashlib(monkeypatch, sandbox)


def outcome(function, *args):
    try:
        value = function(*args)
    except Exception as e:
        return ("raises", type(e).__name__, str(e))
    return ("returns", type(value).__name__, repr(value))


def feed(module, pieces, name="sha256"):
    """Everything a caller can see of a hash fed `pieces` one by one."""
    h = getattr(module, name)()
    seen = [outcome(h.update, piece) for piece in pieces]
    return seen, outcome(h.digest), outcome(h.hexdigest)


# From FIPS 180-4 and RFC 6234.
VECTORS = {
    b"": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    b"abc": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq":
        "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
    b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu":
        "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1",
    b"a" * 1000: "41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3",
}


class TestDigests:
    @pytest.mark.parametrize("message,digest", VECTORS.items(), ids=lambda v: str(v)[:20])
    def test_standard_vectors(self, fast, stub, message, digest):
        assert fast.sha256(message).hexdigest() == stub.sha256(message).hexdigest() == digest
        assert fast.sha256(message).digest() == bytes.fromhex(digest)

    def test_a_million_a(self, fast):
        assert fast.sha256(b"a" * 1_000_000).hexdigest() == (
            "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"
        )

    def test_every_length_up_to_300_and_the_block_boundaries(self, fast, stub):
        rng = random.Random(7)
        for n in list(range(301)) + [511, 512, 513, 1023, 1024, 4095, 4096]:
            message = bytes(rng.randrange(256) for _ in range(n))
            expected = cpython_hashlib.sha256(message)
            assert fast.sha256(message).hexdigest() == expected.hexdigest(), n
            assert fast.sha256(message).digest() == expected.digest(), n
            assert stub.sha256(message).hexdigest() == expected.hexdigest(), n

    def test_str_is_hashed_as_utf8(self, fast, stub):
        for text in ["", "abc", "é€😀", "\x00\x7f\x80", "x" * 200]:
            assert fast.sha256(text).hexdigest() == stub.sha256(text).hexdigest()
            assert fast.sha256(text).hexdigest() == cpython_hashlib.sha256(text.encode()).hexdigest()

    def test_digest_types(self, fast):
        h = fast.sha256(b"abc")
        assert isinstance(h.digest(), bytes) and len(h.digest()) == 32
        assert isinstance(h.hexdigest(), str) and h.hexdigest() == h.digest().hex()


class TestUpdates:
    PIECES = [
        [b"abc"], [b"a", b"b", b"c"], [b"", b"abc", b""], ["abc"], [b"ab", "c"], [bytearray(b"abc")], [memoryview(b"abc")],
        [b"x" * 64, b"y" * 64, b"z"], [b"x" * 63, b"y", b"z" * 65], [bytes([i]) for i in range(150)],
        ["é"], ["é€😀", b"tail"], [], [b"a" * 200] * 5,
    ]

    @pytest.mark.parametrize("pieces", PIECES, ids=lambda p: repr(p)[:30])
    def test_same_as_the_stub_and_as_hashlib(self, fast, stub, pieces):
        assert feed(fast, pieces) == feed(stub, pieces)
        h = cpython_hashlib.sha256()
        for piece in pieces:
            h.update(piece.encode() if isinstance(piece, str) else piece)
        got = fast.sha256()
        for piece in pieces:
            got.update(piece)
        assert got.hexdigest() == h.hexdigest()

    def test_split_a_message_at_every_position(self, fast):
        message = bytes(range(256)) * 2
        for cut in range(0, len(message) + 1, 7):
            h = fast.sha256(message[:cut])
            h.update(message[cut:])
            assert h.hexdigest() == cpython_hashlib.sha256(message).hexdigest(), cut

    def test_digest_does_not_end_the_hash(self, fast, stub):
        for module in (fast, stub):
            h = module.sha256(b"abc")
            first = h.hexdigest()
            assert h.hexdigest() == first
            h.update(b"def")
            assert h.hexdigest() == cpython_hashlib.sha256(b"abcdef").hexdigest()
            assert first == cpython_hashlib.sha256(b"abc").hexdigest()

    def test_copy_is_independent(self, fast, stub):
        for module in (fast, stub):
            h = module.sha256(b"abc")
            c = h.copy()
            c.update(b"def")
            h.update(b"xyz")
            assert c.hexdigest() == cpython_hashlib.sha256(b"abcdef").hexdigest()
            assert h.hexdigest() == cpython_hashlib.sha256(b"abcxyz").hexdigest()
            assert c.copy().hexdigest() == c.hexdigest()

    def test_a_bytearray_is_copied_when_given(self, fast):
        data = bytearray(b"abc")
        h = fast.sha256(data)
        data[0] = ord("z")
        assert h.hexdigest() == cpython_hashlib.sha256(b"abc").hexdigest()

    def test_what_update_refuses(self, fast, stub):
        for bad in [5, None, 1.5, [1, 2], {"a": 1}, object(), "\ud800"]:
            assert feed(fast, [bad]) == feed(stub, [bad]), bad
            assert outcome(lambda: fast.sha256(bad).hexdigest()) == outcome(lambda: stub.sha256(bad).hexdigest()), bad
        for falsy in [None, 0, "", b"", [], ()]:
            assert fast.sha256(falsy).hexdigest() == stub.sha256(falsy).hexdigest()

    def test_update_returns_none(self, fast, stub):
        assert fast.sha256().update(b"x") is stub.sha256().update(b"x") is None

    def test_fuzz(self, fast, stub):
        rng = random.Random(20261118)
        for _ in range(60):
            pieces = [
                bytes(rng.randrange(256) for _ in range(rng.choice([0, 1, 5, 63, 64, 65, 130])))
                for _ in range(rng.randrange(0, 6))
            ]
            fast_hash, stub_hash = fast.sha256(), stub.sha256()
            for piece in pieces:
                fast_hash.update(piece)
                stub_hash.update(piece)
                if rng.random() < 0.3:
                    assert fast_hash.hexdigest() == stub_hash.hexdigest()
                if rng.random() < 0.2:
                    fast_hash, stub_hash = fast_hash.copy(), stub_hash.copy()
            assert fast_hash.digest() == stub_hash.digest()


class TestModule:
    def test_same_names_as_the_stub(self, fast, stub):
        assert sorted(vars(fast)) == sorted(vars(stub))
        assert fast.__file__ == stub.__file__ == "<frozen hashlib>"

    def test_new(self, fast, stub):
        for name in ["sha256", "sha224", "md5", "SHA256", ""]:
            for data in [b"", b"abc"]:
                assert outcome(lambda: fast.new(name, data).hexdigest()) == outcome(lambda: stub.new(name, data).hexdigest())
        assert fast.new("sha256", b"abc").hexdigest() == VECTORS[b"abc"]

    def test_sha224_is_untouched(self, fast, stub):
        for message in [b"", b"abc", b"x" * 100]:
            expected = cpython_hashlib.sha224(message)
            assert fast.sha224(message).hexdigest() == stub.sha224(message).hexdigest() == expected.hexdigest()
            assert fast.sha224(message).digest() == expected.digest()

    def test_public_methods(self, fast, stub):
        h, s = fast.sha256(), stub.sha256()
        public = lambda o: sorted(a for a in dir(o) if not a.startswith("_"))
        assert public(h) == public(s) == ["copy", "digest", "hexdigest", "update"]


class TestWhatTheNativeFunctionServes:
    """The comparisons above would also pass if the native function were never called."""

    def test_digests_come_from_the_native_function_in_one_call(self, fast, sandbox):
        h = fast.sha256(b"abc")
        h.update(b"def")
        h.update("é")
        assert sandbox.calls == []
        h.hexdigest()
        assert sandbox.calls == [b"abcdef" + "é".encode()]
        h.digest()
        assert len(sandbox.calls) == 2

    def test_it_is_given_bytes(self, fast, sandbox):
        fast.sha256("text").hexdigest()
        fast.sha256(bytearray(b"x")).hexdigest()
        assert all(type(call) is bytes for call in sandbox.calls)

    def test_without_the_native_function_the_pure_code_serves(self, monkeypatch):
        module = build_hashlib(monkeypatch, None)
        assert type(module.sha256()).__name__ == "_Sha256"
        assert module.sha256(b"abc").hexdigest() == VECTORS[b"abc"]

    def test_a_sandbox_without_sha256_is_the_pure_code_too(self, monkeypatch):
        module = build_hashlib(monkeypatch, types.ModuleType("_basilisk_sandbox"))
        assert type(module.sha256()).__name__ == "_Sha256"
