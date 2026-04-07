"""
Target Canister v2 - the upgraded version.
Same StableBTreeMap instances (same memory_ids) — data from v1 must persist.
"""

from basilisk import nat64, Opt, query, StableBTreeMap, update

db = StableBTreeMap[str, str](memory_id=0, max_key_size=100, max_value_size=100)
counter = StableBTreeMap[str, nat64](memory_id=1, max_key_size=100, max_value_size=100)


@query
def get_version() -> str:
    return "v2"


@query
def greet(name: str) -> str:
    return f"Greetings, {name}! (upgraded)"


@update
def set_value(key: str, value: str) -> Opt[str]:
    return db.insert(key, value)


@query
def get_value(key: str) -> Opt[str]:
    return db.get(key)


@query
def has_key(key: str) -> bool:
    return db.contains_key(key)


@update
def increment(key: str) -> nat64:
    current = counter.get(key)
    new_val = (current if current is not None else 0) + 1
    counter.insert(key, new_val)
    return new_val


@query
def get_counter(key: str) -> Opt[nat64]:
    return counter.get(key)


@query
def db_len() -> nat64:
    return db.len()
