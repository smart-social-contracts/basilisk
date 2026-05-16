from basilisk import query, update, text, nat, StableBTreeMap, StableBTreeSet, StableVec, void, init

__basilisk_features__ = ["shell", "browse"]

users = StableBTreeMap[text, nat](memory_id=0, max_key_size=64, max_value_size=128)
tags = StableBTreeSet[text](memory_id=1, max_key_size=64)
logs = StableVec[text](memory_id=2, max_value_size=256)


@init
def init_() -> void:
    users.insert("alice", 30)
    users.insert("bob", 25)
    tags.insert("python")
    tags.insert("icp")
    logs.push("canister initialized")


@update
def add_user(name: text, age: nat) -> text:
    users.insert(name, age)
    return f"added {name}"


@query
def get_user(name: text) -> nat:
    return users.get(name) or 0
