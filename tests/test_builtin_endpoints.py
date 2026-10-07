"""The built-in __shell__ / __browse__ that __basilisk_features__ injects."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from basilisk.build_wasm_binary_or_exit import inject_builtin_endpoints

SOURCE = '''
from basilisk import StableBTreeMap, query, text

__basilisk_features__ = ["shell", "browse"]

users = StableBTreeMap[str, int](memory_id=0, max_key_size=100, max_value_size=100)

@query
def hello() -> text:
    return "hi"
'''


def _by_name(methods):
    return {m["name"]: m for m in methods}


def test_both_built_ins_are_controller_only():
    methods = [{"name": "hello", "method_type": "query", "params": [], "returns": "text"}]
    source = inject_builtin_endpoints(SOURCE, methods)
    by_name = _by_name(methods)
    assert by_name["__shell__"]["guard"] == "__basilisk_controller_guard__"
    assert by_name["__browse__"]["method_type"] == "query"
    assert by_name["__browse__"]["guard"] == "guard_against_non_controllers"
    assert "def __shell__" in source and "def __browse__" in source
    assert "guard" not in by_name["hello"]


def test_a_canister_defined_browse_is_left_alone():
    methods = [{"name": "__browse__", "method_type": "query",
                "params": [{"name": "query", "candid_type": "text"}], "returns": "text"}]
    source = inject_builtin_endpoints(SOURCE, methods)
    assert [m["name"] for m in methods].count("__browse__") == 1
    assert "guard" not in _by_name(methods)["__browse__"]
    assert "def __browse__" not in source


def test_nothing_is_injected_without_the_feature():
    methods = []
    source = inject_builtin_endpoints(SOURCE.replace('["shell", "browse"]', "[]"), methods)
    assert methods == [] and "__browse__" not in source
