"""Test canister exercising all stable data structures."""

from basilisk import (
    ic,
    nat64,
    Opt,
    query,
    StableBTreeMap,
    StableBTreeSet,
    StableVec,
    StableLog,
    StableCell,
    StableMinHeap,
    update,
    Vec,
)

# --- StableBTreeMap (memory_id=0) ---
smap = StableBTreeMap[str, str](memory_id=0, max_key_size=200, max_value_size=10_000)

@update
def map_insert(key: str, value: str) -> Opt[str]:
    return smap.insert(key, value)

@query
def map_get(key: str) -> Opt[str]:
    return smap.get(key)

@query
def map_contains_key(key: str) -> bool:
    return smap.contains_key(key)

@update
def map_remove(key: str) -> Opt[str]:
    return smap.remove(key)

@query
def map_len() -> nat64:
    return smap.len()

@query
def map_is_empty() -> bool:
    return smap.is_empty()

@query
def map_keys() -> Vec[str]:
    return smap.keys()

@query
def map_values() -> Vec[str]:
    return smap.values()


# --- StableBTreeSet (memory_id=10) ---
sset = StableBTreeSet(memory_id=10)

@update
def set_insert(key: str) -> bool:
    return sset.insert(key)

@update
def set_remove(key: str) -> bool:
    return sset.remove(key)

@query
def set_contains(key: str) -> bool:
    return sset.contains(key)

@query
def set_len() -> nat64:
    return sset.len()

@query
def set_is_empty() -> bool:
    return sset.is_empty()


# --- StableVec (memory_id=20) ---
svec = StableVec(memory_id=20)

@update
def vec_push(value: str):
    svec.push(value)

@query
def vec_get(index: nat64) -> Opt[str]:
    return svec.get(index)

@update
def vec_pop() -> Opt[str]:
    return svec.pop()

@update
def vec_set(index: nat64, value: str):
    svec.set(index, value)

@query
def vec_len() -> nat64:
    return svec.len()

@query
def vec_is_empty() -> bool:
    return svec.is_empty()


# --- StableLog (memory_id_index=30, memory_id_data=31) ---
slog = StableLog(memory_id_index=30, memory_id_data=31)

@update
def log_append(value: str) -> nat64:
    return slog.append(value)

@query
def log_get(index: nat64) -> Opt[str]:
    return slog.get(index)

@query
def log_len() -> nat64:
    return slog.len()

@query
def log_is_empty() -> bool:
    return slog.is_empty()


# --- StableCell (memory_id=40) ---
scell = StableCell(memory_id=40, default_value="initial")

@query
def cell_get() -> str:
    return scell.get()

@update
def cell_set(value: str):
    scell.set(value)


# --- StableMinHeap (memory_id=50) ---
sheap = StableMinHeap(memory_id=50)

@update
def heap_push(value: str):
    sheap.push(value)

@update
def heap_pop() -> Opt[str]:
    return sheap.pop()

@query
def heap_peek() -> Opt[str]:
    return sheap.peek()

@query
def heap_len() -> nat64:
    return sheap.len()

@query
def heap_is_empty() -> bool:
    return sheap.is_empty()
