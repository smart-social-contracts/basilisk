"""Integration tests for all stable data structures: BTreeMap, BTreeSet, Vec, Log, Cell, MinHeap.

Also covers:
- Typed maps (nat8 keys, int32 values) with explicit stable encoding hints
- Numeric min-heap ordering (big-endian binary ensures correct sort)
"""

import pytest
from .conftest import deploy_example, call_canister, EXAMPLES_DIR
import os

EXAMPLE = "all_stable_structures"
EXAMPLE_DIR = os.path.join(EXAMPLES_DIR, EXAMPLE)


@pytest.fixture(scope="module")
def canister(replica):
    ids = deploy_example(EXAMPLE)
    return ids[list(ids.keys())[0]]


# ===== StableBTreeMap (str, str) =====

def test_map_initially_empty(canister):
    raw = call_canister(canister, "map_is_empty", example_dir=EXAMPLE_DIR)
    assert "true" in raw

def test_map_insert_and_get(canister):
    call_canister(canister, "map_insert", '("alice", "wonderland")', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(canister, "map_get", '("alice")', example_dir=EXAMPLE_DIR)
    assert "wonderland" in raw

def test_map_contains_key(canister):
    raw = call_canister(canister, "map_contains_key", '("alice")', example_dir=EXAMPLE_DIR)
    assert "true" in raw

def test_map_len(canister):
    raw = call_canister(canister, "map_len", example_dir=EXAMPLE_DIR)
    assert "1" in raw

def test_map_keys(canister):
    raw = call_canister(canister, "map_keys", example_dir=EXAMPLE_DIR)
    assert "alice" in raw

def test_map_values(canister):
    raw = call_canister(canister, "map_values", example_dir=EXAMPLE_DIR)
    assert "wonderland" in raw

def test_map_remove(canister):
    raw = call_canister(canister, "map_remove", '("alice")', example_dir=EXAMPLE_DIR, update=True)
    assert "wonderland" in raw
    raw = call_canister(canister, "map_is_empty", example_dir=EXAMPLE_DIR)
    assert "true" in raw


# ===== Typed StableBTreeMap (nat8, int32) =====

def test_typed_map_insert_and_get(canister):
    call_canister(canister, "typed_map_insert", "(10 : nat8, -42 : int32)", example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(canister, "typed_map_get", "(10 : nat8)", example_dir=EXAMPLE_DIR)
    assert "-42" in raw

def test_typed_map_contains_key(canister):
    raw = call_canister(canister, "typed_map_contains_key", "(10 : nat8)", example_dir=EXAMPLE_DIR)
    assert "true" in raw

def test_typed_map_len(canister):
    raw = call_canister(canister, "typed_map_len", example_dir=EXAMPLE_DIR)
    assert "1" in raw

def test_typed_map_multiple_keys(canister):
    """Insert several nat8 keys and verify they all round-trip."""
    call_canister(canister, "typed_map_insert", "(0 : nat8, 100 : int32)", example_dir=EXAMPLE_DIR, update=True)
    call_canister(canister, "typed_map_insert", "(255 : nat8, -1 : int32)", example_dir=EXAMPLE_DIR, update=True)
    raw0 = call_canister(canister, "typed_map_get", "(0 : nat8)", example_dir=EXAMPLE_DIR)
    assert "100" in raw0
    raw255 = call_canister(canister, "typed_map_get", "(255 : nat8)", example_dir=EXAMPLE_DIR)
    assert "-1" in raw255

def test_typed_map_keys_values(canister):
    raw_keys = call_canister(canister, "typed_map_keys", example_dir=EXAMPLE_DIR)
    assert "0" in raw_keys
    assert "10" in raw_keys
    assert "255" in raw_keys
    raw_vals = call_canister(canister, "typed_map_values", example_dir=EXAMPLE_DIR)
    assert "100" in raw_vals
    assert "-42" in raw_vals
    assert "-1" in raw_vals

def test_typed_map_remove(canister):
    raw = call_canister(canister, "typed_map_remove", "(10 : nat8)", example_dir=EXAMPLE_DIR, update=True)
    assert "-42" in raw
    raw = call_canister(canister, "typed_map_contains_key", "(10 : nat8)", example_dir=EXAMPLE_DIR)
    assert "false" in raw


# ===== StableBTreeSet =====

def test_set_initially_empty(canister):
    raw = call_canister(canister, "set_is_empty", example_dir=EXAMPLE_DIR)
    assert "true" in raw

def test_set_insert_and_contains(canister):
    call_canister(canister, "set_insert", '("red")', example_dir=EXAMPLE_DIR, update=True)
    call_canister(canister, "set_insert", '("green")', example_dir=EXAMPLE_DIR, update=True)
    call_canister(canister, "set_insert", '("blue")', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(canister, "set_contains", '("green")', example_dir=EXAMPLE_DIR)
    assert "true" in raw

def test_set_not_contains(canister):
    raw = call_canister(canister, "set_contains", '("yellow")', example_dir=EXAMPLE_DIR)
    assert "false" in raw

def test_set_len(canister):
    raw = call_canister(canister, "set_len", example_dir=EXAMPLE_DIR)
    assert "3" in raw

def test_set_remove(canister):
    call_canister(canister, "set_remove", '("green")', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(canister, "set_contains", '("green")', example_dir=EXAMPLE_DIR)
    assert "false" in raw
    raw = call_canister(canister, "set_len", example_dir=EXAMPLE_DIR)
    assert "2" in raw


# ===== StableVec =====

def test_vec_initially_empty(canister):
    raw = call_canister(canister, "vec_is_empty", example_dir=EXAMPLE_DIR)
    assert "true" in raw

def test_vec_push_and_get(canister):
    call_canister(canister, "vec_push", '("first")', example_dir=EXAMPLE_DIR, update=True)
    call_canister(canister, "vec_push", '("second")', example_dir=EXAMPLE_DIR, update=True)
    call_canister(canister, "vec_push", '("third")', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(canister, "vec_get", "(0 : nat64)", example_dir=EXAMPLE_DIR)
    assert "first" in raw

def test_vec_get_last(canister):
    raw = call_canister(canister, "vec_get", "(2 : nat64)", example_dir=EXAMPLE_DIR)
    assert "third" in raw

def test_vec_len(canister):
    raw = call_canister(canister, "vec_len", example_dir=EXAMPLE_DIR)
    assert "3" in raw

def test_vec_set(canister):
    call_canister(canister, "vec_set", '(1 : nat64, "replaced")', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(canister, "vec_get", "(1 : nat64)", example_dir=EXAMPLE_DIR)
    assert "replaced" in raw

def test_vec_pop(canister):
    raw = call_canister(canister, "vec_pop", example_dir=EXAMPLE_DIR, update=True)
    assert "third" in raw
    raw = call_canister(canister, "vec_len", example_dir=EXAMPLE_DIR)
    assert "2" in raw


# ===== StableLog =====

def test_log_initially_empty(canister):
    raw = call_canister(canister, "log_is_empty", example_dir=EXAMPLE_DIR)
    assert "true" in raw

def test_log_append_and_get(canister):
    call_canister(canister, "log_append", '("entry0")', example_dir=EXAMPLE_DIR, update=True)
    call_canister(canister, "log_append", '("entry1")', example_dir=EXAMPLE_DIR, update=True)
    call_canister(canister, "log_append", '("entry2")', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(canister, "log_get", "(0 : nat64)", example_dir=EXAMPLE_DIR)
    assert "entry0" in raw

def test_log_get_last(canister):
    raw = call_canister(canister, "log_get", "(2 : nat64)", example_dir=EXAMPLE_DIR)
    assert "entry2" in raw

def test_log_len(canister):
    raw = call_canister(canister, "log_len", example_dir=EXAMPLE_DIR)
    assert "3" in raw


# ===== StableCell =====

def test_cell_default_value(canister):
    raw = call_canister(canister, "cell_get", example_dir=EXAMPLE_DIR)
    assert "initial" in raw

def test_cell_set_and_get(canister):
    call_canister(canister, "cell_set", '("updated")', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(canister, "cell_get", example_dir=EXAMPLE_DIR)
    assert "updated" in raw

def test_cell_overwrite(canister):
    call_canister(canister, "cell_set", '("final")', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(canister, "cell_get", example_dir=EXAMPLE_DIR)
    assert "final" in raw


# ===== StableMinHeap (str) =====

def test_heap_initially_empty(canister):
    raw = call_canister(canister, "heap_is_empty", example_dir=EXAMPLE_DIR)
    assert "true" in raw

def test_heap_push_and_peek(canister):
    call_canister(canister, "heap_push", '("cherry")', example_dir=EXAMPLE_DIR, update=True)
    call_canister(canister, "heap_push", '("apple")', example_dir=EXAMPLE_DIR, update=True)
    call_canister(canister, "heap_push", '("banana")', example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(canister, "heap_peek", example_dir=EXAMPLE_DIR)
    assert "apple" in raw  # min-heap: "apple" < "banana" < "cherry"

def test_heap_len(canister):
    raw = call_canister(canister, "heap_len", example_dir=EXAMPLE_DIR)
    assert "3" in raw

def test_heap_pop_order(canister):
    """Pop should return elements in ascending order (min-heap)."""
    raw1 = call_canister(canister, "heap_pop", example_dir=EXAMPLE_DIR, update=True)
    assert "apple" in raw1
    raw2 = call_canister(canister, "heap_pop", example_dir=EXAMPLE_DIR, update=True)
    assert "banana" in raw2
    raw3 = call_canister(canister, "heap_pop", example_dir=EXAMPLE_DIR, update=True)
    assert "cherry" in raw3

def test_heap_empty_after_pops(canister):
    raw = call_canister(canister, "heap_is_empty", example_dir=EXAMPLE_DIR)
    assert "true" in raw


# ===== Numeric StableMinHeap (int64 default encoding) =====

def test_num_heap_numeric_ordering(canister):
    """With big-endian binary encoding, ints sort numerically, not lexicographically.

    If encoding were text/JSON, "9" > "10" lexicographically.
    With big-endian int64 encoding, 9 < 10 correctly.
    """
    call_canister(canister, "num_heap_push", "(100 : int64)", example_dir=EXAMPLE_DIR, update=True)
    call_canister(canister, "num_heap_push", "(9 : int64)", example_dir=EXAMPLE_DIR, update=True)
    call_canister(canister, "num_heap_push", "(42 : int64)", example_dir=EXAMPLE_DIR, update=True)
    raw = call_canister(canister, "num_heap_peek", example_dir=EXAMPLE_DIR)
    assert "9" in raw  # smallest value

def test_num_heap_pop_order(canister):
    """Values should pop in numeric ascending order."""
    raw1 = call_canister(canister, "num_heap_pop", example_dir=EXAMPLE_DIR, update=True)
    assert "9" in raw1
    raw2 = call_canister(canister, "num_heap_pop", example_dir=EXAMPLE_DIR, update=True)
    assert "42" in raw2
    raw3 = call_canister(canister, "num_heap_pop", example_dir=EXAMPLE_DIR, update=True)
    assert "100" in raw3

def test_num_heap_empty_after_pops(canister):
    raw = call_canister(canister, "num_heap_len", example_dir=EXAMPLE_DIR)
    assert "0" in raw
