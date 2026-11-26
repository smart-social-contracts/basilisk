"""Unit tests for _generate_post_upgrade_wrapper code generation.

The build points the post_upgrade lifecycle entry at the generated wrapper,
which runs the user's post_upgrade and then ic-python-db's
check_upgrade_compatibility(). The lifecycle entry keeps the user's declared
parameters, so the runtime calls the wrapper with the decoded upgrade
arguments. These tests run the generated source the way the runtime calls it.
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.build_wasm_binary_or_exit import _generate_post_upgrade_wrapper


class Trapped(BaseException):
    pass


class FakeIC:
    @staticmethod
    def trap(message):
        raise Trapped(message)


@pytest.fixture
def calls(monkeypatch):
    """The order in which the user's function and the schema check ran."""
    record = []

    class Database:
        @classmethod
        def get_instance(cls):
            return cls()

        def check_upgrade_compatibility(self):
            record.append("check")

    fake = types.ModuleType("ic_python_db")
    fake.Database = Database
    monkeypatch.setitem(sys.modules, "ic_python_db", fake)
    return record


def wrapper(user_fn_name, user_fn=None):
    namespace = {"_basilisk_ic": FakeIC}
    if user_fn is not None:
        namespace[user_fn_name] = user_fn
    exec(_generate_post_upgrade_wrapper(user_fn_name), namespace)
    return namespace["_basilisk_post_upgrade_wrapper"]


def test_source_is_valid_python():
    compile(_generate_post_upgrade_wrapper(None), "<test>", "exec")
    compile(_generate_post_upgrade_wrapper("my_post_upgrade"), "<test>", "exec")


def test_without_a_user_function_it_only_checks(calls):
    assert wrapper(None)() is None
    assert calls == ["check"]


def test_runs_the_user_function_then_the_check(calls):
    wrapper("my_post_upgrade", lambda: calls.append("user"))()
    assert calls == ["user", "check"]


def test_passes_the_upgrade_arguments_on(calls):
    """#66: the runtime calls the wrapper with the decoded arguments of the user's post_upgrade."""
    received = []

    def post_upgrade_(owner, should_trap):
        received.append((owner, should_trap))

    wrapper("post_upgrade_", post_upgrade_)("bob", False)
    assert received == [("bob", False)]
    assert calls == ["check"]


def test_returns_what_the_user_function_returns(calls):
    """An async post_upgrade returns a generator that the runtime drives."""
    def post_upgrade_():
        yield

    result = wrapper("post_upgrade_", post_upgrade_)()
    assert isinstance(result, types.GeneratorType)


def ic_python_db_whose_check_raises(monkeypatch, error):
    class Database:
        @classmethod
        def get_instance(cls):
            return cls()

        def check_upgrade_compatibility(self):
            raise error

    fake = types.ModuleType("ic_python_db")
    fake.Database = Database
    monkeypatch.setitem(sys.modules, "ic_python_db", fake)


@pytest.mark.parametrize("error", [
    ValueError("schema is incompatible"),
    # #69: these two were swallowed, and the upgrade went through unchecked.
    # ic-python-db (0.14.0, 0.16.0, main) raises the first one on a stored
    # schema that is not a mapping.
    AttributeError("'str' object has no attribute 'keys'"),
    ImportError("cannot import name 'migrate'"),
])
def test_anything_the_check_raises_rejects_the_upgrade(monkeypatch, error):
    ic_python_db_whose_check_raises(monkeypatch, error)
    with pytest.raises(Trapped, match=f"Upgrade rejected: {error}"):
        wrapper(None)()


def test_an_ic_python_db_without_the_check_upgrades(monkeypatch):
    fake = types.ModuleType("ic_python_db")
    fake.Database = type("Database", (), {})
    monkeypatch.setitem(sys.modules, "ic_python_db", fake)
    assert wrapper(None)() is None


def test_without_ic_python_db_it_passes(monkeypatch):
    monkeypatch.setitem(sys.modules, "ic_python_db", None)  # forces ImportError on import
    assert wrapper(None)() is None
